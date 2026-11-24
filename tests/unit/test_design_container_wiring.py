"""Offline unit tests: wires INTO components the design itself defines.

A long real-world build found the offline builder answering SUCCESS, with a connection
count that included them, while every wire into a design-defined component was lost:
the wire `A/out1 -> B/in1` was written as an `inputs` block on the In op INSIDE `B`,
pointing at `A/out1` — a path that resolves inside `B`, so TouchDesigner drops it on
open. TouchDesigner's own save stores such a wire as a `compinputs` block in
`<comp>.network` (the format the builder already writes for palette and external_tox
components): one row per wired In op — connector index, the source relative to the
comp's parent, the inner In op's name, its family.

Policy under test (same rule as the external_tox fix):
  - explicit `"to": "B/in1"` binds that In op by name; an unknown In op fails loud;
  - bare `"to": "B"` / `"from": "A"` binds only when that side has exactly one In / Out
    op; otherwise the build fails loud naming the candidates;
  - a wire that would cross a component boundary any other way fails loud;
  - no declared wire is silently dropped: anything the builder could not write fails
    the build, so a SUCCESS receipt only counts wires that are in the file.

Designs here carry no parameter values, so the tests need no knowledge base. The real
toecollapse/toeexpand round trip lives in tests/engine/test_design_container_wiring_roundtrip.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _op(name, typ, x=0, y=0):
    return {"name": name, "type": typ, "position": [x, y]}


def _comp(name, ops, conns=None, x=0, y=0, **extra):
    c = {"name": name, "type": "base", "family": "COMP", "position": [x, y],
         "operators": ops, "connections": conns or []}
    c.update(extra)
    return c


def _probe(conns):
    """The probe shape from the build review: A has two outs, B has two ins."""
    return {
        "containers": [
            _comp("A", [_op("null1", "TOP:null"), _op("out1", "TOP:out", 200),
                        _op("out2", "CHOP:out", 200, -150)],
                  conns=[{"from": "null1", "to": "out1"}]),
            _comp("B", [_op("in1", "TOP:in"), _op("in2", "CHOP:in", 0, -150)], x=300),
        ],
        "operators": [],
        "connections": conns,
    }


def _build_toe(tmp_path: Path, design: dict, name: str = "pw") -> Path:
    """Build via the .toe path; return the expanded project1 dir (collapse may be
    unavailable on CI — the expanded tree is what toecollapse packs verbatim)."""
    ToeBuilderBridge(tmp_path, verbose=False).build_from_design(design, name)
    d = tmp_path / f"{name}.toe.dir" / "project1"
    assert d.exists(), "builder produced no expanded directory"
    return d


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# explicit In-op targets
# ---------------------------------------------------------------------------

def test_explicit_wires_into_component_become_compinputs(tmp_path):
    d = _build_toe(tmp_path, _probe([{"from": "A/out1", "to": "B/in1"},
                                     {"from": "A/out2", "to": "B/in2"}]))
    assert _read(d / "B.network") == (
        "1\ncompinputs\n{\n"
        "0 \tA/out1\n\tin1\n\tTOP\n"
        "1 \tA/out2\n\tin2\n\tCHOP\n"
        "}\nend\n")
    # The In ops themselves carry no inputs block (that was the silent drop).
    assert "inputs" not in _read(d / "B" / "in1.n")
    assert "inputs" not in _read(d / "B" / "in2.n")
    # The wire inside A is untouched.
    assert "0\tnull1\n" in _read(d / "A" / "out1.n")


def test_explicit_target_that_is_not_an_in_op_fails_loud(tmp_path):
    # 'B/null1' is an operator inside B, not one of its inputs: TD cannot wire into it
    # from outside B, so the old build's silent drop becomes a named failure.
    design = _probe([{"from": "A/out1", "to": "B/null1"}])
    design["containers"][1]["operators"].append(_op("null1", "TOP:null", 200))
    with pytest.raises(ValueError) as ei:
        _build_toe(tmp_path, design)
    msg = str(ei.value)
    assert "only through one of its In ops" in msg
    assert "in1" in msg and "in2" in msg


def test_source_inside_a_component_that_is_not_an_out_op_fails_loud(tmp_path):
    with pytest.raises(ValueError) as ei:
        _build_toe(tmp_path, _probe([{"from": "A/null1", "to": "B/in1"}]))
    msg = str(ei.value)
    assert "only through one of its Out ops" in msg
    assert "out1" in msg and "out2" in msg


def test_two_wires_into_one_in_op_fail_loud(tmp_path):
    with pytest.raises(ValueError, match="wired 2 times"):
        _build_toe(tmp_path, _probe([{"from": "A/out1", "to": "B/in1"},
                                     {"from": "A/out2", "to": "B/in1"}]))


# ---------------------------------------------------------------------------
# bare component names (A -> B)
# ---------------------------------------------------------------------------

def _single_io(conns):
    return {
        "containers": [
            _comp("A", [_op("null1", "TOP:null"), _op("out1", "TOP:out", 200)],
                  conns=[{"from": "null1", "to": "out1"}]),
            _comp("B", [_op("in1", "TOP:in"), _op("null1", "TOP:null", 200)],
                  conns=[{"from": "in1", "to": "null1"}], x=300),
        ],
        "connections": conns,
    }


def test_bare_wire_between_single_io_components(tmp_path):
    d = _build_toe(tmp_path, _single_io([{"from": "A", "to": "B"}]))
    assert _read(d / "B.network") == "1\ncompinputs\n{\n0 \tA/out1\n\tin1\n\tTOP\n}\nend\n"
    # B's own inner wire is untouched.
    assert "0\tin1\n" in _read(d / "B" / "null1.n")


def test_bare_target_with_two_in_ops_fails_loud_naming_them(tmp_path):
    with pytest.raises(ValueError) as ei:
        _build_toe(tmp_path, _probe([{"from": "A/out1", "to": "B"}]))
    msg = str(ei.value)
    assert "in1" in msg and "in2" in msg and "explicitly" in msg


def test_bare_source_with_two_out_ops_fails_loud_naming_them(tmp_path):
    with pytest.raises(ValueError) as ei:
        _build_toe(tmp_path, _probe([{"from": "A", "to": "B/in1"}]))
    msg = str(ei.value)
    assert "out1" in msg and "out2" in msg and "never itself a data source" in msg


def test_bare_source_from_a_component_feeds_an_ordinary_operator(tmp_path):
    # Out of a component into a plain sibling: '.n' inputs name the Out op, even when
    # the consumer is listed before the component (the out-op map is primed up front).
    design = _single_io([{"from": "A", "to": "level1"}])
    design["operators"] = [_op("level1", "TOP:level", 600)]
    design["containers"] = list(reversed(design["containers"]))
    d = _build_toe(tmp_path, design)
    assert "0\tA/out1\n" in _read(d / "level1.n")


# ---------------------------------------------------------------------------
# nested components, the .tox path, and the receipt
# ---------------------------------------------------------------------------

def test_nested_component_wired_from_its_parents_in_op(tmp_path):
    # LOOK passes its input straight on to the inner component MUD, declared inside LOOK.
    mud = _comp("MUD", [_op("in1", "TOP:in"), _op("out1", "TOP:out", 200)],
                conns=[{"from": "in1", "to": "out1"}])
    look = _comp("LOOK", [_op("in1", "TOP:in"), _op("out1", "TOP:out", 400)],
                 conns=[{"from": "in1", "to": "MUD/in1"},
                        {"from": "MUD", "to": "out1"}],
                 containers=[mud], x=300)
    src = _comp("SRC", [_op("noise1", "TOP:noise"), _op("out1", "TOP:out", 200)],
                conns=[{"from": "noise1", "to": "out1"}])
    d = _build_toe(tmp_path, {"containers": [src, look],
                              "connections": [{"from": "SRC", "to": "LOOK"}]})
    assert _read(d / "LOOK.network") == "1\ncompinputs\n{\n0 \tSRC/out1\n\tin1\n\tTOP\n}\nend\n"
    assert _read(d / "LOOK" / "MUD.network") == "1\ncompinputs\n{\n0 \tin1\n\tin1\n\tTOP\n}\nend\n"
    assert "0\tMUD/out1\n" in _read(d / "LOOK" / "out1.n")


def test_row_index_is_the_connector_index_when_only_some_inputs_are_wired(tmp_path):
    # TD positions component inputs alphanumerically by In op name: wiring only in2
    # writes connector 1.
    d = _build_toe(tmp_path, _probe([{"from": "A/out2", "to": "B/in2"}]))
    assert _read(d / "B.network") == "1\ncompinputs\n{\n1 \tA/out2\n\tin2\n\tCHOP\n}\nend\n"


def test_tox_build_writes_wires_into_components_too(tmp_path):
    ToxBuilder(tmp_path, verbose=False).build_tox(
        _probe([{"from": "A/out1", "to": "B/in1"}, {"from": "A/out2", "to": "B/in2"}]), "pv")
    d = tmp_path / "pv.tox.dir" / "pv"
    assert _read(d / "B.network").startswith("1\ncompinputs\n{\n0 \tA/out1\n\tin1\n\tTOP\n")
    assert "inputs" not in _read(d / "B" / "in1.n")


def test_wire_to_an_operator_that_does_not_exist_fails_the_build(tmp_path):
    with pytest.raises(ValueError, match="could not be written") as ei:
        _build_toe(tmp_path, _probe([{"from": "A/out1", "to": "nowhere"}]))
    assert "'A/out1' -> 'nowhere'" in str(ei.value)


def test_receipt_count_is_the_wires_written(tmp_path):
    bridge = ToeBuilderBridge(tmp_path, verbose=False)
    bridge.build_from_design(_probe([{"from": "A/out1", "to": "B/in1"},
                                     {"from": "A/out2", "to": "B/in2"}]), "pw")
    assert bridge.wires_written == 3  # null1->out1 inside A, plus the two into B


def test_in_op_keeps_a_wire_from_inside_its_own_component(tmp_path):
    # TouchDesigner saves In ops with a sibling input (a local fallback source) — that
    # wire is the In op's own and stays in its .n, beside any wire into the component.
    design = _probe([{"from": "A/out1", "to": "B/in1"}])
    design["containers"][1]["operators"].append(_op("moviein1", "TOP:moviefilein", -200))
    design["containers"][1]["connections"] = [{"from": "moviein1", "to": "in1"}]
    d = _build_toe(tmp_path, design)
    assert "inputs\n{\n0\tmoviein1\n}\n" in _read(d / "B" / "in1.n")
    assert "0 \tA/out1\n\tin1\n\tTOP\n" in _read(d / "B.network")
