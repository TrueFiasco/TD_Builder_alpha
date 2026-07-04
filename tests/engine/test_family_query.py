"""Unit test for EnhancedGraphQuery.get_operators_by_family (audit #13).

KB-independent: builds a tiny synthetic graph so the filter/dedup/case logic is
tested without the fetched 37k-node graph. (The real-graph end-to-end is
exercised by the acceptance gate's query_graph(family=...) test.)
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


def _build(tmp_path):
    data = {
        "nodes": {
            "op1": {"id": "op1", "type": "Operator", "name": "noisePOP", "family": "POP"},
            "op2": {"id": "op2", "type": "Operator", "name": "noiseTOP", "family": "TOP"},
            "op3": {"id": "op3", "type": "Operator", "name": "noisePOP", "family": "POP"},   # dup name
            "op4": {"id": "op4", "type": "Operator", "name": "feedbackPOP", "family": "pop"},  # lower fam
            "ex1": {"id": "ex1", "type": "ExampleNetwork", "name": "demo"},                   # non-operator
        },
        "edges": [],
    }
    p = tmp_path / "tiny.gpickle"
    with open(p, "wb") as f:
        pickle.dump(data, f)
    # W2d trust boundary: unreceipted pickles are refused at load time
    kb_integrity.write_receipt(tmp_path, source="test-fixture", artifacts=[p.name])
    return EnhancedGraphQuery(str(p))


def test_family_filter_dedup_and_case(tmp_path):
    eq = _build(tmp_path)
    pops = eq.get_operators_by_family("POP")
    names = sorted(p["name"] for p in pops)
    # deduped (noisePOP x2 -> 1), case-insensitive family (pop -> POP), TOP + example excluded
    assert names == ["feedbackPOP", "noisePOP"]
    assert all((p.get("family") or "").upper() == "POP" for p in pops)


def test_empty_and_unknown_family(tmp_path):
    eq = _build(tmp_path)
    assert eq.get_operators_by_family("") == []
    assert eq.get_operators_by_family("ZZZ") == []
