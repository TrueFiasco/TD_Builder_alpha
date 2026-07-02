"""Round-4 #1b — component manifest in expand_toe_file's summary.

A reusable component .tox has an interface: its `in*`/`out*` operators are its inputs/
outputs. _component_manifest extracts that interface (+ families + a one-line summary) so an
LLM can wire a component via `external_tox` without re-expanding it each time. Surfaced as a
`manifest` field on expand_toe_file(mode='summary'). Unit-tested via the loaded server module.
"""
from types import SimpleNamespace


def _net(project, ops, conns=()):
    return SimpleNamespace(
        metadata=SimpleNamespace(project_name=project, mode="tox"),
        operators=[SimpleNamespace(path=p, op_type=t, parameters={}) for p, t in ops],
        connections=[SimpleNamespace(source=s, target=d, source_output=0, target_input=0)
                     for s, d in conns],
        statistics=None,
    )


def test_component_manifest_extracts_io(server):
    mf = getattr(server, "_component_manifest", None)
    assert callable(mf), "_component_manifest not defined on server module"
    net = _net("comp",
               [("/comp", "COMP:base"), ("/comp/in1", "TOP:in"), ("/comp/level1", "TOP:level"),
                ("/comp/in2", "TOP:in"), ("/comp/out1", "TOP:out")],
               [("/comp/in1", "/comp/level1"), ("/comp/level1", "/comp/out1")])
    m = mf(net)
    assert [i["name"] for i in m["inputs"]] == ["in1", "in2"]
    assert [o["name"] for o in m["outputs"]] == ["out1"]
    assert m["operator_count"] == 5
    assert m["connection_count"] == 2
    assert m["families"].get("TOP") == 4


def test_summary_includes_manifest(server):
    net = _net("c", [("/c/in1", "TOP:in"), ("/c/out1", "TOP:out")])
    summary = server._summarize_td_network(net)
    assert "manifest" in summary
    assert [i["name"] for i in summary["manifest"]["inputs"]] == ["in1"]


# ---------------------------------------------------------------------------
# Component-import defect #1b (2026-07-02): the manifest aggregated in*/out*
# ops from EVERY nesting level, so a Derivative palette wrapper tox (root COMP
# + icon + same-name inner COMP) reported ~14 duplicated inputs instead of the
# inner comp's interface. inputs/outputs are now scoped to the direct children
# of the interface COMP, matched by op-type (:in/:out) only.
# ---------------------------------------------------------------------------

def test_wrapper_manifest_uses_inner_comp(server):
    net = _net("bloom", [
        ("/bloom", "COMP:base"),
        ("/bloom/icon", "COMP:base"),
        ("/bloom/icon/out1", "TOP:out"),            # icon plumbing must not leak
        ("/bloom/bloom", "COMP:base"),
        ("/bloom/bloom/in1", "TOP:in"),
        ("/bloom/bloom/in2", "TOP:in"),
        ("/bloom/bloom/out1", "TOP:out"),
        ("/bloom/bloom/level1", "TOP:level"),
        ("/bloom/bloom/nested", "COMP:base"),
        ("/bloom/bloom/nested/in1", "TOP:in"),      # deeper io must not leak
        ("/bloom/bloom/nested/out1", "TOP:out"),
    ])
    m = server._component_manifest(net)
    assert [i["name"] for i in m["inputs"]] == ["in1", "in2"]
    assert [o["name"] for o in m["outputs"]] == ["out1"]
    assert m["wrapper"] is True
    assert m["interface_path"] == "/bloom/bloom"


def test_root_with_connectors_beats_same_name_child(server):
    # A root that has its own in/out IS the interface, even when a same-name
    # child COMP exists -- the wrapper redirect must not fire.
    net = _net("postfx", [
        ("/postfx", "COMP:base"),
        ("/postfx/in1", "TOP:in"),
        ("/postfx/out1", "TOP:out"),
        ("/postfx/postfx", "COMP:base"),
        ("/postfx/postfx/in1", "TOP:in"),
        ("/postfx/postfx/out1", "TOP:out"),
    ])
    m = server._component_manifest(net)
    assert m["wrapper"] is False
    assert m["interface_path"] == "/postfx"
    assert [i["name"] for i in m["inputs"]] == ["in1"]
    assert [o["name"] for o in m["outputs"]] == ["out1"]
    assert m["inputs"][0]["op_type"] == "TOP:in"


def test_manifest_excludes_nested_io(server):
    net = _net("comp", [
        ("/comp", "COMP:base"),
        ("/comp/in1", "TOP:in"),
        ("/comp/out1", "TOP:out"),
        ("/comp/inner", "COMP:base"),
        ("/comp/inner/in1", "TOP:in"),
        ("/comp/inner/out1", "TOP:out"),
    ])
    m = server._component_manifest(net)
    assert [i["name"] for i in m["inputs"]] == ["in1"]
    assert [o["name"] for o in m["outputs"]] == ["out1"]
    assert m["operator_count"] == 6          # counts stay whole-network


def test_manifest_matches_connectors_by_op_type_not_name(server):
    # Decoys: in-ish/out-ish NAMES with non-connector types are not connectors.
    net = _net("comp", [
        ("/comp", "COMP:base"),
        ("/comp/in1", "TOP:in"),
        ("/comp/in5", "TOP:level"),
        ("/comp/integrate1", "TOP:level"),
        ("/comp/output_settings", "DAT:table"),
        ("/comp/out1", "TOP:out"),
    ])
    m = server._component_manifest(net)
    assert [i["name"] for i in m["inputs"]] == ["in1"]
    assert [o["name"] for o in m["outputs"]] == ["out1"]
