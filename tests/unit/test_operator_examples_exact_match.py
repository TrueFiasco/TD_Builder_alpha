"""find_examples_by_operator matches the operator type exactly before any substring.

HERMETIC: a hand-built five-node graph, no KB artifact. Runs in both CI lanes.
The KB-backed twin (real names: textTOP, inTOP, GLSL POP) is
tests/unit/test_operator_name_lookups.py.

Substring-only matching served Texture 3D TOP for 'textTOP' and Point File In
TOP for 'inTOP' in a long real-world build: 'text' is inside 'texture3d', 'in'
inside 'pointfilein', and the first hit filled the limit.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SERVER_CORE = Path(__file__).resolve().parents[2] / "MCP" / "server_core"
if str(_SERVER_CORE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CORE))

import enhanced_graph_query as egq  # noqa: E402


def _graph(ops):
    """ops: {node_name: family}. Each operator gets one useful example."""
    nodes, edges = {}, []
    for name, fam in ops.items():
        op_id, ex_id = f"op:{fam}/{name}", f"ex:{fam}/{name}/example1"
        nodes[op_id] = {"type": "Operator", "id": op_id, "name": name, "family": fam}
        nodes[ex_id] = {"type": "Example", "id": ex_id, "is_useful": True,
                        "example_id": f"{fam}/{name}/example1",
                        "operator_type": f"{fam}/{name}", "operators": []}
        edges.append({"from": op_id, "to": ex_id, "type": "DEMONSTRATES"})
    q = egq.EnhancedGraphQuery.__new__(egq.EnhancedGraphQuery)
    q.nodes, q.edges = nodes, edges
    q._build_edge_indices()
    return q


def _served_for(examples):
    return [e["operator_type"] for e in examples]


def test_exact_name_beats_a_longer_name_that_contains_it():
    q = _graph({"texture3dTOP": "TOP", "textTOP": "TOP"})
    ex = q.find_examples_by_operator("textTOP")
    assert _served_for(ex) == ["TOP/textTOP"]
    assert "match" not in ex[0]


def test_short_name_does_not_match_inside_other_names():
    q = _graph({"pointfileinTOP": "TOP", "pointtransformTOP": "TOP", "inTOP": "TOP"})
    assert _served_for(q.find_examples_by_operator("inTOP")) == ["TOP/inTOP"]


def test_exact_node_without_examples_does_not_fall_back():
    q = _graph({"texture3dTOP": "TOP"})
    q.nodes["op:TOP/textTOP"] = {"type": "Operator", "id": "op:TOP/textTOP",
                                 "name": "textTOP", "family": "TOP"}
    assert q.find_examples_by_operator("textTOP") == []


def test_no_exact_match_falls_back_to_substring_and_marks_it():
    q = _graph({"texture3dTOP": "TOP"})
    ex = q.find_examples_by_operator("texture", family="TOP")
    assert _served_for(ex) == ["TOP/texture3dTOP"]
    assert ex[0]["match"] == "substring"
    assert ex[0]["matched_operator"] == "texture3dTOP"


def test_substring_fallback_can_be_switched_off():
    q = _graph({"texture3dTOP": "TOP"})
    assert q.find_examples_by_operator("textTOP", allow_substring=False) == []


def test_bare_name_still_buckets_exact_matches_by_family():
    q = _graph({"noiseTOP": "TOP", "noiseCHOP": "CHOP", "noisemaskTOP": "TOP"})
    r = q.find_examples_by_operator("noise")
    assert r["_resolution"] == "multi-family"
    assert _served_for(r["results_by_family"]["TOP"]) == ["TOP/noiseTOP"]
    assert _served_for(r["results_by_family"]["CHOP"]) == ["CHOP/noiseCHOP"]
