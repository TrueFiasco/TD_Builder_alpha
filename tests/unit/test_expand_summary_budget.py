"""expand_toe_file(mode='summary') has a real size budget.

On a real project the old "summary" was most of the project (~800 KB on one
line in a long real-world build; 2-9 MB on the large files that ship with
TouchDesigner). Over budget, the summary becomes an overview: counts, the
component tree to a set depth and the interface manifest, plus how to open one
component at a time (`component=`). Under budget it is returned unchanged.

Hermetic: drives the pure summary-view function on synthetic summaries.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP" / "server_core"))

import mcp_server as srv  # noqa: E402

BUDGET = 24 * 1024


def _size(obj) -> int:
    return len(json.dumps(obj, default=str).encode("utf-8"))


def _op(path, op_type, n_params=6):
    return {"path": path, "op_type": op_type,
            "params": [{"name": f"p{i}", "value": "x" * 20, "mode": "constant"}
                       for i in range(n_params)]}


def _summary(ops, conns=()):
    fam = {}
    for o in ops:
        f = o["op_type"].split(":")[0]
        fam[f] = fam.get(f, 0) + 1
    return {
        "project_name": "proj", "mode": "toe",
        "node_count": len(ops), "connection_count": len(conns),
        "by_family": fam, "operators": list(ops), "connections": list(conns),
        "foreign_refs": [], "manifest": {"inputs": [], "outputs": [], "summary": "m"},
    }


def _big():
    """/proj with 3 components, each with 2 sub-components of 150 CHOPs —
    except /proj/b/b2, which is small (20 CHOPs) so it fits the budget."""
    ops, conns = [_op("/proj", "COMP:base")], []
    for a in "abc":
        ops.append(_op(f"/proj/{a}", "COMP:base"))
        for i in (1, 2):
            sub = f"/proj/{a}/{a}{i}"
            ops.append(_op(sub, "COMP:container"))
            for k in range(20 if sub == "/proj/b/b2" else 150):
                ops.append(_op(f"{sub}/noise{k}", "CHOP:noise"))
                if k:
                    conns.append({"from": f"{sub}/noise{k-1}", "to": f"{sub}/noise{k}",
                                  "source_output": 0, "target_input": 0})
    ops.append(_op("/proj/out1", "TOP:out"))
    return _summary(ops, conns)


def test_small_summary_is_returned_unchanged():
    s = _summary([_op("/proj", "COMP:base"), _op("/proj/noise1", "CHOP:noise")])
    assert srv._summary_view(s, max_bytes=BUDGET) == s


def test_big_summary_becomes_an_overview_under_budget():
    s = _big()
    assert _size(s) > 10 * BUDGET  # the case this guards
    v = srv._summary_view(s, max_bytes=BUDGET)
    assert _size(v) <= BUDGET
    assert v["node_count"] == s["node_count"]
    assert v["connection_count"] == s["connection_count"]
    assert v["by_family"] == s["by_family"]
    assert v["manifest"] == s["manifest"]
    assert "operators" not in v and "connections" not in v
    tree = {c["path"]: c for c in v["component_tree"]}
    assert tree["/proj/a/a1"]["operators"] == 150
    assert tree["/proj"]["operators"] == s["node_count"] - 1
    # The top-level ops are listed by name and type, without parameters.
    assert {"path": "/proj/out1", "op_type": "TOP:out"} in v["top_level_operators"]
    t = v["_truncated"]
    assert t["full_bytes"] == _size(s) and t["max_bytes"] == BUDGET
    assert "component=" in t["hint"] and "mode='full'" in t["hint"]


def test_component_opens_one_component_in_full_detail():
    s = _big()
    v = srv._summary_view(s, component="/proj/b/b2", max_bytes=BUDGET)
    assert v["component"] == "/proj/b/b2"
    paths = [o["path"] for o in v["operators"]]
    assert paths[0] == "/proj/b/b2" and len(paths) == 21
    assert all(p == "/proj/b/b2" or p.startswith("/proj/b/b2/") for p in paths)
    assert v["operators"][1]["params"]                      # full detail
    assert v["connection_count"] == len(v["connections"]) == 19
    assert v["node_count"] == 21
    assert _size(v) <= BUDGET


def test_component_accepts_path_without_leading_slash():
    v = srv._summary_view(_big(), component="proj/a/a1", max_bytes=BUDGET)
    assert v["component"] == "/proj/a/a1"


def test_big_component_is_itself_an_overview():
    v = srv._summary_view(_big(), component="/proj/a", max_bytes=BUDGET)
    assert _size(v) <= BUDGET
    assert v["component"] == "/proj/a" and v["node_count"] == 303
    assert {c["path"] for c in v["component_tree"]} >= {"/proj/a", "/proj/a/a1", "/proj/a/a2"}
    assert "_truncated" in v


def test_unknown_component_returns_none():
    assert srv._summary_view(_big(), component="/proj/nope", max_bytes=BUDGET) is None


def test_very_wide_tree_still_fits_and_says_what_was_left_out():
    ops = [_op("/proj", "COMP:base")]
    ops += [_op(f"/proj/c{i:04d}", "COMP:base", n_params=0) for i in range(3000)]
    v = srv._summary_view(_summary(ops), max_bytes=BUDGET)
    assert _size(v) <= BUDGET
    assert v["_truncated"]["component_tree_omitted"] > 0
    assert len(v["component_tree"]) + v["_truncated"]["component_tree_omitted"] == 3001


def test_over_budget_component_lists_operators_until_the_budget():
    v = srv._summary_view(_big(), component="/proj/a/a1", max_bytes=BUDGET)
    assert _size(v) <= BUDGET
    listed = v["operators"]
    assert listed and listed[0]["path"] == "/proj/a/a1"
    assert all(o["params"] for o in listed)                   # full detail
    assert len(listed) + v["_truncated"]["operators_omitted"] == 151
    assert v["_truncated"]["operators_omitted"] > 0


def test_a_single_operator_path_opens_that_operator():
    v = srv._summary_view(_big(), component="/proj/a/a1/noise7", max_bytes=BUDGET)
    assert [o["path"] for o in v["operators"]] == ["/proj/a/a1/noise7"]
