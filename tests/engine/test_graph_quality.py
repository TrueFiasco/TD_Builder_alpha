"""Round-4 graph-quality trio (#5/#6/#7), all in enhanced_graph_query.py.

KB-independent: builds a tiny synthetic enhanced graph (the test_family_query.py pattern)
so the query logic is tested without the fetched 37k-node graph.

#6  EnhancedGraphQuery.get_operator_info must resolve a DISPLAY name ("Feedback TOP") to a
    suffixed node name ("feedbackTOP") — hybrid_search uses this for 'relationships', and
    the old substring match returned None ("not found in enhanced graph").
#5  find_similar_patterns must not return [] for the ~87% of examples with no
    IMPLEMENTS_PATTERN edge — fall back to shared-operator overlap.
#7  get_network_patterns must dedup repeated pattern signatures and filter universal-only
    (null/in/out/select) noise patterns.
"""
import pickle
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from enhanced_graph_query import EnhancedGraphQuery  # noqa: E402
import kb_integrity  # noqa: E402


def _graph(tmp_path, nodes, edges=None):
    p = tmp_path / "g.gpickle"
    with open(p, "wb") as f:
        pickle.dump({"nodes": nodes, "edges": edges or []}, f)
    # W2d trust boundary: unreceipted pickles are refused at load time
    kb_integrity.write_receipt(tmp_path, source="test-fixture", artifacts=[p.name])
    return EnhancedGraphQuery(str(p))


def _ex(eid, ops):
    return {"id": f"ex:{eid}", "type": "ExampleNetwork", "example_id": eid,
            "operator_type": "demo", "is_useful": True, "connections": [],
            "operators": [{"name": n, "type": t} for n, t in ops]}


# ---- #6: display-name resolution -------------------------------------------------

def test_get_operator_info_resolves_display_name(tmp_path):
    nodes = {"op:feedbackTOP": {"id": "op:feedbackTOP", "type": "Operator",
                                "name": "feedbackTOP", "family": "TOP"}}
    g = _graph(tmp_path, nodes)
    info = g.get_operator_info("Feedback TOP")
    assert info is not None, "display name 'Feedback TOP' did not resolve to node 'feedbackTOP'"
    assert info["operator_name"] == "feedbackTOP"


# ---- #5: shared-operator similarity fallback -------------------------------------

def test_find_similar_uses_shared_operators_without_pattern(tmp_path):
    nodes = {
        "ex:a": _ex("a", [("n1", "TOP:noise"), ("l1", "TOP:level")]),
        "ex:b": _ex("b", [("n2", "TOP:noise"), ("l2", "TOP:level")]),  # shares noise+level
        "ex:c": _ex("c", [("b1", "SOP:box")]),                          # unrelated
    }
    g = _graph(tmp_path, nodes)  # no IMPLEMENTS_PATTERN edges at all
    ids = [e["example_id"] for e in g.find_similar_patterns("a", limit=5)]
    assert "b" in ids, f"shared-operator fallback missing: {ids}"
    assert "a" not in ids, "query example must not match itself"
    assert "c" not in ids, f"unrelated example should not match: {ids}"


# ---- #7: dedup + universal-pattern noise filter ----------------------------------

def _pat(pid, sig, ops, freq):
    return {"id": pid, "type": "NetworkPattern", "pattern_signature": sig,
            "operator_types": ops, "frequency": freq, "canonical_example": "ex:x"}


def test_get_network_patterns_dedup_and_noise_filter(tmp_path):
    nodes = {
        "p1": _pat("p1", "sig-A", ["TOP:noise", "TOP:level"], 10),
        "p2": _pat("p2", "sig-A", ["TOP:noise", "TOP:level"], 9),    # duplicate signature
        "p3": _pat("p3", "univ", ["CHOP:null", "TOP:null"], 8),      # universal-only -> noise
        "p4": _pat("p4", "sig-B", ["SOP:box", "SOP:transform"], 6),
        "p5": _pat("p5", "sig-C", ["TOP:blur"], 3),                  # below min_frequency
    }
    g = _graph(tmp_path, nodes)
    pats = g.get_network_patterns(min_frequency=5)
    sigs = [p["pattern_signature"] for p in pats]
    assert sigs.count("sig-A") == 1, f"duplicate signature not deduped: {sigs}"
    assert "univ" not in sigs, f"universal-only noise pattern not filtered: {sigs}"
    assert "sig-B" in sigs
    assert "sig-C" not in sigs  # below threshold
