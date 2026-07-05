"""W4b — MCP risk annotations + tool-output budgets (audit cluster C3).

Two regression surfaces, both hermetic (no KB, no live TD), so this whole module runs
in the KB-free CI lane:

  * output budgets — the pure `output_budget` helpers cap the two flood-prone tools
    (`expand_toe_file` full mode, `hybrid_search`) and, when over budget, replace the
    flood with an explicit non-silent signal that keeps the scorer envelope valid;
  * risk annotations — every tool on both servers carries a `ToolAnnotations` risk
    tier. The live surface is checked by importing the real Tool objects; the offline
    surface is checked by AST-parsing `mcp_server.py` (its full import pulls the KB).

See docs/TOOL_RISK_ANNOTATIONS.md for the owner-approved classification.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP" / "server_core"))   # output_budget (pure)
sys.path.insert(0, str(REPO / "MCP" / "live_client"))   # td_live_client (light deps)

import output_budget as ob            # noqa: E402
import td_live_client as live         # noqa: E402

MCP_SERVER_PY = REPO / "MCP" / "server_core" / "mcp_server.py"

DESTRUCTIVE_LIVE = {
    "create_td_node", "update_td_node_parameters", "delete_td_node",
    "execute_python_script", "exec_node_method",
}


# ---------------------------------------------------------------------------
# Part 2 — output budgets
# ---------------------------------------------------------------------------
def _big_lossless(node_count: int, blob_kb: int) -> dict:
    """A lossless-JSON-shaped dict with a payload we can force over any cap."""
    return {
        "format_version": "1.0",
        "format_layer": "lossless",
        "metadata": {},
        "operators": [{"name": f"op{i}"} for i in range(node_count)],
        "lossless_data": {"blob": "x" * (blob_kb * 1024)},
    }


def test_full_expand_under_budget_is_unchanged():
    data = _big_lossless(3, 1)
    payload, truncated, info = ob.budget_full_expand(data, max_bytes=10 * 1024 * 1024)
    assert payload is data          # same object, untouched
    assert truncated is False
    assert info == {}


def test_full_expand_over_budget_returns_signalled_stub():
    data = _big_lossless(7, 64)
    payload, truncated, info = ob.budget_full_expand(data, max_bytes=2048)
    assert truncated is True
    assert payload["_truncated"] is True
    assert payload["node_count"] == 7           # operators counted
    assert payload["full_bytes"] > 2048
    assert "hint" in payload and "summary" in payload["hint"]
    # The stub is itself small (that is the whole point) ...
    assert ob.sized(payload) <= 2048
    # ... and it is NOT an error envelope — no error/ok:false keys leak in, so the
    # agent-eval scorer keeps treating a truncated-but-valid result as success.
    assert "error" not in payload
    assert payload.get("ok") is not False


def test_full_expand_non_dict_passthrough():
    payload, truncated, info = ob.budget_full_expand("not a dict", max_bytes=1)
    assert payload == "not a dict" and truncated is False


def _hybrid_results(n_hits: int, params_each: int) -> dict:
    return {
        "query": "feedback loop",
        "semantic_results": [
            {
                "name": f"Op{i} TOP",
                "score": 0.9 - i * 0.01,
                "metadata": {"operator_name": f"Op{i} TOP"},
                "parameter_count": params_each,
                "ground_truth_param_count": params_each,
                "parameters": [{"name": f"p{j}", "desc": "y" * 200} for j in range(params_each)],
            }
            for i in range(n_hits)
        ],
        "relationships": [],
    }


def test_hybrid_under_budget_is_unchanged():
    results = _hybrid_results(2, 1)
    out, truncated = ob.budget_hybrid_results(results, max_bytes=10 * 1024 * 1024)
    assert truncated is False
    assert "_truncation" not in out
    assert out["semantic_results"][0]["parameters"]     # enrichment intact


def test_hybrid_over_budget_sheds_params_but_keeps_results():
    results = _hybrid_results(5, 60)
    before = ob.sized(results)
    out, truncated = ob.budget_hybrid_results(results, max_bytes=4096)
    assert truncated is True
    # semantic_results survives, same length, still non-empty (test_p03 contract)
    assert isinstance(out["semantic_results"], list)
    assert len(out["semantic_results"]) == 5
    for hit in out["semantic_results"]:
        assert "parameters" not in hit                  # the flood was shed
        assert "ground_truth_param_count" not in hit
        assert hit["parameters_omitted"] is True
        assert hit["parameter_count"] == 60             # count preserved as a pointer
    # top-level non-error signal, and the envelope genuinely shrank
    assert out["_truncation"]["truncated"] is True
    assert "get_operator_info" in out["_truncation"]["hint"]
    assert ob.sized(out) < before
    assert "error" not in out and out.get("ok") is not False


def test_hybrid_non_dict_passthrough():
    out, truncated = ob.budget_hybrid_results([1, 2, 3], max_bytes=1)
    assert out == [1, 2, 3] and truncated is False


def test_env_caps_are_positive_ints():
    assert isinstance(ob.EXPAND_FULL_MAX_BYTES, int) and ob.EXPAND_FULL_MAX_BYTES > 0
    assert isinstance(ob.HYBRID_SEARCH_MAX_BYTES, int) and ob.HYBRID_SEARCH_MAX_BYTES > 0


# ---------------------------------------------------------------------------
# Part 1 — risk annotations (live surface: real Tool objects)
# ---------------------------------------------------------------------------
def test_live_tools_all_annotated():
    tools = live.TD_LIVE_TOOLS
    assert len(tools) == 19
    assert all(t.annotations is not None for t in tools), \
        [t.name for t in tools if t.annotations is None]


def test_live_destructive_set_is_exactly_the_five_mutators():
    got = {t.name for t in live.TD_LIVE_TOOLS
           if t.annotations.destructiveHint is True}
    assert got == DESTRUCTIVE_LIVE


def test_live_reads_are_readonly_mutators_are_not():
    for t in live.TD_LIVE_TOOLS:
        a = t.annotations
        if t.name in DESTRUCTIVE_LIVE:
            assert a.readOnlyHint is False and a.destructiveHint is True, t.name
            assert a.idempotentHint is False, t.name
        else:
            assert a.readOnlyHint is True, t.name


def test_live_annotations_do_not_touch_names():
    # names still match the handler dispatch map (annotations add fields only)
    assert sorted(t.name for t in live.TD_LIVE_TOOLS) == sorted(live.TD_LIVE_HANDLERS)


# ---------------------------------------------------------------------------
# Part 1 — risk annotations (offline surface: AST, so no KB-heavy import)
# ---------------------------------------------------------------------------
def _offline_tool_annotations() -> dict:
    """Map offline tool name -> the annotations constant name, parsed from source."""
    tree = ast.parse(MCP_SERVER_PY.read_text(encoding="utf-8"))
    out = {}
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "Tool"):
            continue
        kw = {k.arg: k.value for k in call.keywords}
        name_node = kw.get("name")
        ann_node = kw.get("annotations")
        name = name_node.value if isinstance(name_node, ast.Constant) else None
        ann = ann_node.id if isinstance(ann_node, ast.Name) else None
        if name is not None:
            out[name] = ann
    return out


def test_offline_tools_all_annotated_17():
    ann = _offline_tool_annotations()
    assert len(ann) == 17, sorted(ann)
    missing = [n for n, a in ann.items() if a is None]
    assert not missing, f"offline tools missing annotations: {missing}"
    assert set(ann.values()) <= {"READ_ONLY", "WRITE_ADDITIVE"}


def test_offline_build_project_is_write_additive_status_is_readonly():
    ann = _offline_tool_annotations()
    assert ann["td_build_project"] == "WRITE_ADDITIVE"
    assert ann["td_build_status"] == "READ_ONLY"
    # exactly one write-additive tool on the offline surface
    assert sum(v == "WRITE_ADDITIVE" for v in ann.values()) == 1


def test_offline_annotation_constants_are_correct():
    """The two source constants encode the intended hint values."""
    tree = ast.parse(MCP_SERVER_PY.read_text(encoding="utf-8"))
    consts = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "ToolAnnotations"):
            kw = {k.arg: (k.value.value if isinstance(k.value, ast.Constant) else None)
                  for k in node.value.keywords}
            consts[node.targets[0].id] = kw
    assert consts["READ_ONLY"] == {"readOnlyHint": True}
    assert consts["WRITE_ADDITIVE"] == {
        "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
