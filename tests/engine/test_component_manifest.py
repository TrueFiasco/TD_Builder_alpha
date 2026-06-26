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
