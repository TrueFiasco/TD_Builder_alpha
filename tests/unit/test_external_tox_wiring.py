"""Offline unit tests for BUG-3: external_tox component wiring.

A design that wires a user-supplied external_tox component used to drop BOTH wire
directions silently: the comp got no palette_io_map entry, so a bare `{"from": "comp"}`
source kept the bare comp name (never valid — a component is never itself a data source;
TD drops it at load) and in-wires serialized as a sibling-name inputs block on a
connector-less placeholder (also dropped). The fix manifest-parses the referenced .tox
at build time and routes wires through the palette-v2 machinery (compinputs .network +
inner-out-op source paths — TD-native, load-order-proof serialization, live-verified on
TD 2025.32820 and byte-pinned in test_palette_v2.py).

Resolution policy under test (grounded: the offline manifest NAME-SORTS — outputs[0] of
a multi-out comp is NOT connector 0, e.g. abletonSong's live order out1,out5,out2,...):
  - explicit inner names ('comp/out_bins', 'comp/in2') pass through / bind verbatim;
  - bare 'comp' auto-resolves ONLY a single-connector comp;
  - multiple candidates, zero connectors, unknown explicit names, unresolved wrappers,
    and wired-but-unreadable manifests all FAIL LOUD;
  - unwired external_tox comps build exactly as before, missing file included.

Manifests are injected by monkeypatching bridge._load_external_manifest (the designed
seam); the real toeexpand round trip lives in tests/engine/test_external_tox_manifest.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from meta_agentic.execution import toe_builder_bridge as bridge  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _manifest(ins=(), outs=(), wrapper=False, interface_path="/fx", subcompname=None):
    """Shape returned by core.component_manifest.manifest_from_tox."""
    return {
        "manifest": {
            "inputs": [{"name": n, "op_type": f"{f}:in"} for n, f in ins],
            "outputs": [{"name": n, "op_type": f"{f}:out"} for n, f in outs],
            "families": {}, "operator_count": len(ins) + len(outs) + 1,
            "connection_count": 0, "interface_path": interface_path,
            "wrapper": wrapper, "summary": "",
        },
        "inner_type": "COMP:base",
        "subcompname": subcompname,
    }


def _inject(monkeypatch, result=None, raises=None):
    """Monkeypatch the manifest-loader seam."""
    def fake(resolved_path):
        if raises is not None:
            raise raises
        return result
    monkeypatch.setattr(bridge, "_load_external_manifest", fake)


def _tox(tmp_path: Path, name="fx.tox") -> str:
    """A file that exists so the pre-pass reaches the (mocked) manifest loader."""
    f = tmp_path / name
    f.write_text("stub", encoding="utf-8")
    return str(f).replace("\\", "/")


def _build(tmp_path: Path, design: dict, name: str = "pv") -> Path:
    ToxBuilder(tmp_path, verbose=False).build_tox(design, name)
    d = tmp_path / f"{name}.tox.dir" / name
    assert d.exists(), "builder produced no expanded directory"
    return d


TEST_REGISTRY = {
    "components": {
        # live-harvested (no stamp -> index trust, matches shipped/test fixtures)
        "srcComp": {
            "source": "project", "tox_path": "tox/srcComp.tox", "wrapper": False,
            "inner_type": "COMP:base",
            "inputs": [],
            "outputs": [{"index": 0, "out_op": "out1", "family": "CHOP"}],
        },
        "liveComp": {
            "source": "project", "tox_path": "tox/liveComp.tox", "wrapper": False,
            "inner_type": "COMP:base",
            "inputs": [],
            "outputs": [{"index": 0, "out_op": "out_a", "family": "CHOP"},
                        {"index": 1, "out_op": "out_b", "family": "CHOP"}],
            "harvest": {"method": "offline_manifest+live"},
        },
        # offline registration (rider): NAME authority only -> strict policy
        "offlineComp": {
            "source": "project", "tox_path": "tox/offlineComp.tox", "wrapper": False,
            "inner_type": "COMP:base",
            "inputs": [],
            "outputs": [{"index": 0, "out_op": "out_a", "family": "CHOP"},
                        {"index": 1, "out_op": "out_b", "family": "CHOP"}],
            "harvest": {"method": "offline_manifest"},
        },
    }
}


@pytest.fixture()
def registry():
    saved = bridge._PALETTE_COMPONENTS_CACHE
    bridge._PALETTE_COMPONENTS_CACHE = TEST_REGISTRY
    yield TEST_REGISTRY
    bridge._PALETTE_COMPONENTS_CACHE = saved


def _design(tox_ref, ops=None, conns=None):
    return {
        "operators": [{"name": "src", "type": "noise", "family": "CHOP",
                       "position": [0, 0]},
                      {"name": "fx", "external_tox": tox_ref, "position": [200, 0]},
                      {"name": "null1", "type": "null", "family": "CHOP",
                       "position": [400, 0]}] + (ops or []),
        "connections": conns or [],
    }


# ---------------------------------------------------------------------------
# out-wires (consumer .n input paths)
# ---------------------------------------------------------------------------

def test_u1_bare_out_single_resolves(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(outs=[("valueOut", "CHOP")]))
    d = _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "fx", "to": "null1"}]))
    n = (d / "null1.n").read_text(encoding="utf-8")
    assert "0\tfx/valueOut\n" in n, n


def test_u2_bare_out_multi_fails_loud(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(outs=[("valueOut", "CHOP"), ("chansOut", "CHOP")]))
    with pytest.raises(ValueError) as ei:
        _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "fx", "to": "null1"}]))
    msg = str(ei.value)
    assert "never itself a data source" in msg
    assert "chansOut" in msg and "valueOut" in msg
    assert "fx/" in msg  # actionable explicit-source suggestion


def test_u3_bare_out_zero_fails_loud(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(outs=[]))
    with pytest.raises(ValueError, match="contains no out operators"):
        _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "fx", "to": "null1"}]))


def test_u4_explicit_out_passes_verbatim(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(outs=[("valueOut", "CHOP")]))
    d = _build(tmp_path, _design(_tox(tmp_path),
                                 conns=[{"from": "fx/whatever", "to": "null1"}]))
    n = (d / "null1.n").read_text(encoding="utf-8")
    assert "0\tfx/whatever\n" in n, n


# ---------------------------------------------------------------------------
# in-wires (compinputs .network)
# ---------------------------------------------------------------------------

def test_u5_bare_in_single_compinputs_bytes(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(ins=[("chanIn", "CHOP")]))
    d = _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "src", "to": "fx"}]))
    net = (d / "fx.network").read_text(encoding="utf-8")
    assert net == "1\ncompinputs\n{\n0 \tsrc\n\tchanIn\n\tCHOP\n}\nend\n", net


def test_u6_bare_in_multi_fails_loud(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(ins=[("chanIn", "CHOP"), ("ctrlIn", "CHOP")]))
    with pytest.raises(ValueError) as ei:
        _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "src", "to": "fx"}]))
    msg = str(ei.value)
    assert "chanIn" in msg and "ctrlIn" in msg and "explicitly" in msg


def test_u7_explicit_in_honored_and_typo_trapped(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(ins=[("in1", "CHOP"), ("in2", "CHOP")]))
    d = _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "src", "to": "fx/in2"}]))
    net = (d / "fx.network").read_text(encoding="utf-8")
    assert net == "1\ncompinputs\n{\n0 \tsrc\n\tin2\n\tCHOP\n}\nend\n", net

    _inject(monkeypatch, _manifest(ins=[("in1", "CHOP"), ("in2", "CHOP")]))
    with pytest.raises(ValueError, match="no in op named 'nope'"):
        _build(tmp_path, _design(_tox(tmp_path, "fx2.tox"),
                                 conns=[{"from": "src", "to": "fx/nope"}]), "pv2")


def test_u8_wired_comp_n_has_no_inputs_block(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(ins=[("chanIn", "CHOP")]))
    d = _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "src", "to": "fx"}]))
    n = (d / "fx.n").read_text(encoding="utf-8")
    assert "inputs" not in n, "a .n inputs block on the placeholder is dropped by TD"


# ---------------------------------------------------------------------------
# manifest unavailable / failure taxonomy
# ---------------------------------------------------------------------------

def test_u9_unwired_missing_file_still_builds(tmp_path):
    missing = str(tmp_path / "nope" / "missing.tox").replace("\\", "/")
    d = _build(tmp_path, _design(missing))
    parm = (d / "fx.parm").read_text(encoding="utf-8")
    assert f"externaltox 0 {missing}" in parm
    assert "enableexternaltox 0 on" in parm


def test_u10_wired_missing_file_fails_loud(tmp_path):
    missing = str(tmp_path / "nope" / "missing.tox").replace("\\", "/")
    with pytest.raises(ValueError, match="was not found"):
        _build(tmp_path, _design(missing, conns=[{"from": "fx", "to": "null1"}]))


def test_u11_wired_toeexpand_missing_fails_loud(tmp_path, monkeypatch):
    class FakeErr(Exception):
        kind = "tool_missing"
    _inject(monkeypatch, raises=FakeErr("toeexpand not found."))
    with pytest.raises(ValueError, match="cannot be read"):
        _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "fx", "to": "null1"}]))


def test_u12_wrapper_policy(tmp_path, monkeypatch):
    wrapped = _manifest(ins=[("in1", "TOP")], outs=[("out1", "TOP")],
                        wrapper=True, interface_path="/fx/fx", subcompname="fx")
    _inject(monkeypatch, wrapped)
    with pytest.raises(ValueError, match="wrapper-style"):
        _build(tmp_path, _design(_tox(tmp_path), conns=[{"from": "fx", "to": "null1"}]))

    # With parameters.subcompname TD loads the inner comp directly -> manifest
    # interface names are valid; subcompname is emitted RAW (mode 0).
    _inject(monkeypatch, wrapped)
    design = _design(_tox(tmp_path, "fxw.tox"), conns=[{"from": "src", "to": "fx"}])
    design["operators"][1]["parameters"] = {"subcompname": "fx"}
    d = _build(tmp_path, design, "pvw")
    parm = (d / "fx.parm").read_text(encoding="utf-8")
    assert "subcompname 0 fx" in parm, parm
    net = (d / "fx.network").read_text(encoding="utf-8")
    assert "\tin1\n\tTOP\n" in net, net


# ---------------------------------------------------------------------------
# ordering (pre-pass), provenance, comp-typed sources, containers
# ---------------------------------------------------------------------------

def test_u13_consumer_listed_before_external_comp(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(outs=[("valueOut", "CHOP")]))
    tox = _tox(tmp_path)
    design = {
        "operators": [
            {"name": "null1", "type": "null", "family": "CHOP", "position": [400, 0]},
            {"name": "fx", "external_tox": tox, "position": [200, 0]},
        ],
        "connections": [{"from": "fx", "to": "null1"}],
    }
    d = _build(tmp_path, design)
    n = (d / "null1.n").read_text(encoding="utf-8")
    assert "0\tfx/valueOut\n" in n, n


def test_u14_consumer_listed_before_palette_comp(registry, tmp_path):
    design = {
        "operators": [
            {"name": "nullA", "type": "null", "family": "CHOP", "position": [400, 0]},
            {"name": "gen", "palette": "srcComp", "position": [200, 0]},
        ],
        "connections": [{"from": "gen", "to": "nullA"}],
    }
    d = _build(tmp_path, design)
    n = (d / "nullA.n").read_text(encoding="utf-8")
    assert "0\tgen/out1\n" in n, n


def test_u15_provenance_switch(registry, tmp_path):
    # offline-stamped registry entry: NAME authority -> bare multi-out fails loud...
    design = {
        "operators": [
            {"name": "gen", "palette": "offlineComp", "position": [0, 0]},
            {"name": "nullA", "type": "null", "family": "CHOP", "position": [200, 0]},
        ],
        "connections": [{"from": "gen", "to": "nullA"}],
    }
    with pytest.raises(ValueError, match="out_a"):
        _build(tmp_path, design)

    # ...the identical shape with a live stamp keeps legacy index-0 resolution.
    design["operators"][0]["palette"] = "liveComp"
    d = _build(tmp_path, design, "pv_live")
    n = (d / "nullA.n").read_text(encoding="utf-8")
    assert "0\tgen/out_a\n" in n, n


def test_u16_comp_typed_compinputs_source_resolved(registry, tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(ins=[("in1", "CHOP")]))
    design = {
        "operators": [
            {"name": "gen", "palette": "srcComp", "position": [0, 0]},
            {"name": "fx", "external_tox": _tox(tmp_path), "position": [200, 0]},
        ],
        "connections": [{"from": "gen", "to": "fx"}],
    }
    d = _build(tmp_path, design)
    net = (d / "fx.network").read_text(encoding="utf-8")
    assert net == "1\ncompinputs\n{\n0 \tgen/out1\n\tin1\n\tCHOP\n}\nend\n", net


def test_u17_manifest_unavailable_explicit_out_only_builds(tmp_path):
    missing = str(tmp_path / "nope" / "missing.tox").replace("\\", "/")
    d = _build(tmp_path, _design(missing, conns=[{"from": "fx/customOut", "to": "null1"}]))
    n = (d / "null1.n").read_text(encoding="utf-8")
    assert "0\tfx/customOut\n" in n, n


def test_u18_comp_inside_container(tmp_path, monkeypatch):
    _inject(monkeypatch, _manifest(ins=[("chanIn", "CHOP")], outs=[("valueOut", "CHOP")]))
    tox = _tox(tmp_path)
    design = {
        "containers": [{
            "name": "C",
            "operators": [
                {"name": "src", "type": "noise", "family": "CHOP", "position": [0, 0]},
                {"name": "fx", "external_tox": tox, "position": [200, 0]},
                {"name": "sink", "type": "null", "family": "CHOP", "position": [400, 0]},
            ],
            "connections": [{"from": "src", "to": "fx"},
                            {"from": "fx", "to": "sink"}],
        }],
        "operators": [],
    }
    d = _build(tmp_path, design)
    # out-wire: container-expanded 'C/fx' source resolves via basename (D-X4) and the
    # .n writer re-normalizes it sibling-relative.
    n = (d / "C" / "sink.n").read_text(encoding="utf-8")
    assert "0\tfx/valueOut\n" in n, n
    # in-wire: compinputs source is sibling-relative too.
    net = (d / "C" / "fx.network").read_text(encoding="utf-8")
    assert net == "1\ncompinputs\n{\n0 \tsrc\n\tchanIn\n\tCHOP\n}\nend\n", net
