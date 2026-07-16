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
# D3 (W6a): the single WRITE_CHECKPOINT live tool (dialog-proof disk checkpoint;
# writes a file, never mutates the graph, idempotent overwrite).
WRITE_CHECKPOINT_LIVE = {"save_td_project"}


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


# ---------------------------------------------------------------------------
# W-C shed fidelity — a shed envelope degrades toward the COMPACT hit shape,
# never the legacy (pre-#24) one: parameter_names / score_kind /
# parameters_capped survive every shed stage. (Regression for the s18 finding:
# the fields must stay visible in an over-budget envelope, in both modes.)
# ---------------------------------------------------------------------------
def _wc_hit(i: int, content_len: int = 1500, capped: bool = True) -> dict:
    """A full-mode hybrid_search hit shaped like the real post-#24/#26 handler
    output: content snippet + metadata + score(+kind) + W-C param fidelity."""
    hit = {
        "content": f"GLSL Op{i} POP (POP operator) 'GLSL' parameters: " + "x" * content_len,
        "metadata": {"operator_name": f"GLSL Op{i} POP", "family": "POP"},
        "score": 0.9 - i * 0.01,
        "score_kind": "rank_fusion_only",
        "parameter_count": 54,
        "ground_truth_param_count": 54,
        "parameter_names": [f"p{j}" for j in range(22)] + ["vec[0]{name,type,value}"],
        "parameters": {f"p{j}": {"description": "y" * 200} for j in range(12)},
    }
    if capped:
        hit["parameters_capped"] = True
    return hit


def test_hybrid_shed_keeps_wc_fidelity_fields():
    results = {"query": "glsl pop uniforms",
               "semantic_results": [_wc_hit(i) for i in range(5)],
               "relationships": {}}
    before = ob.sized(results)
    out, truncated = ob.budget_hybrid_results(results, max_bytes=8192)
    assert truncated is True
    assert len(out["semantic_results"]) == 5
    for hit in out["semantic_results"]:
        # The W-C contract: even shed, a hit still answers "which params exist",
        # "how was this scored", and "was the hydrated detail capped".
        assert "vec[0]{name,type,value}" in hit["parameter_names"]
        assert hit["score_kind"] == "rank_fusion_only"
        assert hit["parameters_capped"] is True
        assert hit["parameter_count"] == 54          # TRUE count survives
        assert "parameters" not in hit               # only the hydrated flood goes
        assert hit["parameters_omitted"] is True
    assert ob.sized(out) < before
    assert "never shed" in out["_truncation"]["hint"]


def test_hybrid_shed_stage1_sufficient_leaves_content_and_rels_alone():
    # Dropping the parameters dicts alone lands under budget -> later stages
    # must NOT fire: content and relationship enrichment stay intact.
    rels = {"GLSL Op0 POP": {"family": "POP",
                             "sample_examples": [{"label": "ex1"}],
                             "common_parameters": {"active": "on"}}}
    results = {"query": "q",
               "semantic_results": [_wc_hit(i, content_len=300) for i in range(3)],
               "relationships": rels}
    out, truncated = ob.budget_hybrid_results(results, max_bytes=8192)
    assert truncated is True
    for hit in out["semantic_results"]:
        assert "content_chars_omitted" not in hit
        assert len(hit["content"]) > 300
    rel = out["relationships"]["GLSL Op0 POP"]
    assert rel["sample_examples"] and rel["common_parameters"]
    assert ob.sized(out) <= 8192


def test_hybrid_shed_slims_relationships_before_touching_content():
    rels = {f"Op{i}": {"family": "POP",
                       "common_parameters": {f"c{j}": "z" * 300 for j in range(10)},
                       "sample_examples": [{"label": "ex", "blob": "w" * 2000}] * 2}
            for i in range(3)}
    results = {"query": "q",
               "semantic_results": [_wc_hit(0, content_len=100)],
               "relationships": rels}
    out, truncated = ob.budget_hybrid_results(results, max_bytes=4096)
    assert truncated is True
    for rel in out["relationships"].values():
        assert "sample_examples" not in rel
        assert rel["examples_omitted"] == 2                 # non-silent
        assert "common_parameters" not in rel
        assert rel["common_parameter_names"] == [f"c{j}" for j in range(10)]
    # content was small enough to keep once relationships were slimmed
    hit = out["semantic_results"][0]
    assert "content_chars_omitted" not in hit
    assert ob.sized(out) <= 4096


def test_hybrid_shed_compact_envelope_actually_shrinks():
    # Compact-mode hits carry NO `parameters` dicts; the shed must still be able
    # to reduce an oversized envelope (stage 3 content trim) instead of no-opping,
    # and the W-C fields still survive.
    hits = []
    for i in range(5):
        h = _wc_hit(i, content_len=5000, capped=False)
        h.pop("parameters")
        hits.append(h)
    results = {"query": "q", "semantic_results": hits, "relationships": {}}
    before = ob.sized(results)
    out, truncated = ob.budget_hybrid_results(results, max_bytes=8192)
    assert truncated is True
    assert ob.sized(out) < before
    assert ob.sized(out) <= 8192
    for hit in out["semantic_results"]:
        assert "parameters_omitted" not in hit       # stage 1 had nothing to omit
        assert hit["content_chars_omitted"] > 0      # trim is flagged, not silent
        assert len(hit["content"]) <= ob.SHED_CONTENT_KEEP + 2
        assert "vec[0]{name,type,value}" in hit["parameter_names"]
        assert hit["score_kind"] == "rank_fusion_only"


def test_env_caps_are_positive_ints():
    assert isinstance(ob.EXPAND_FULL_MAX_BYTES, int) and ob.EXPAND_FULL_MAX_BYTES > 0
    assert isinstance(ob.HYBRID_SEARCH_MAX_BYTES, int) and ob.HYBRID_SEARCH_MAX_BYTES > 0


# ---------------------------------------------------------------------------
# F5 (a) — proactive per-hit hydration cap (mcp_server._hydrate_hit_params).
# This is the PROACTIVE cap that keeps a multi-hit envelope small even when it is
# far UNDER HYBRID_SEARCH_MAX_BYTES (the reactive ob.budget_hybrid_results shed only
# fires once the whole envelope is oversized). mcp_server imports KB-free now
# (knowledge_graph loads lazily), so importing it here is cheap and hermetic.
# ---------------------------------------------------------------------------
import mcp_server as srv  # noqa: E402


def _full_info(n_params: int) -> dict:
    return {
        "wiki_parameters": {f"p{i}": {"display_name": f"P{i}"} for i in range(n_params)},
        "ground_truth_param_count": n_params,
    }


def test_hydrate_caps_params_even_under_envelope_budget():
    result = {"name": "Grid SOP", "metadata": {"operator_name": "Grid SOP"}}
    srv._hydrate_hit_params(result, _full_info(30), compact=False)
    # Bounded by the cap even though the envelope is tiny (well under the byte budget).
    assert len(result["parameters"]) == srv.PARAM_HYDRATE_CAP
    # TRUE full counts are preserved (nothing silently hidden).
    assert result["parameter_count"] == 30
    assert result["ground_truth_param_count"] == 30
    assert result["parameters_capped"] is True


def test_hydrate_no_cap_flag_when_within_cap():
    result = {"name": "X", "metadata": {}}
    srv._hydrate_hit_params(result, _full_info(5), compact=False)
    assert len(result["parameters"]) == 5
    assert result["parameter_count"] == 5
    assert "parameters_capped" not in result


def test_hydrate_compact_omits_params_keeps_counts():
    result = {"name": "X", "parameters": {"stale": 1}, "metadata": {}}
    srv._hydrate_hit_params(result, _full_info(30), compact=True)
    assert "parameters" not in result          # dropped entirely in compact mode
    assert result["parameter_count"] == 30      # counts still present
    assert result["ground_truth_param_count"] == 30
    assert "parameters_capped" not in result


# ---------------------------------------------------------------------------
# W-C — param family collapse (mcp_server._collapse_param_families +
# _hydrate_hit_params). Families fold to ONE self-describing entry BEFORE the cap;
# TRUE counts are never touched; parameters_capped reflects POST-collapse length.
# ---------------------------------------------------------------------------

def _wiki(codes_with_pages):
    """Build a wiki_parameters dict {code: {display_name, page?}} in order."""
    wp = {}
    for entry in codes_with_pages:
        if isinstance(entry, tuple):
            code, page = entry
            wp[code] = {"display_name": code.upper(), "page": page}
        else:
            wp[entry] = {"display_name": entry.upper()}
    return {"wiki_parameters": wp, "ground_truth_param_count": len(codes_with_pages)}


def test_collapse_transform_tuplet_to_single_entry():
    # TD ground-truth transform codes: t/r/s/p/scale -> one entry, freeing slots.
    out = srv._collapse_param_families(
        [(c, {"display_name": c}) for c in ["t", "r", "s", "p", "scale", "group", "xord"]]
    )
    labels = [c for c, _ in out]
    assert srv._TRANSFORM_LABEL in labels
    assert "group" in labels and "xord" in labels          # non-members untouched
    # collapsed entry is self-describing (lists member codes)
    desc = dict(out)[srv._TRANSFORM_LABEL]
    assert set(desc["members"]) == {"t", "r", "s", "p", "scale"}
    assert desc["member_count"] == 5


def test_collapse_split_xyz_and_rgba_groups():
    # Geometry COMP instance components: instancetx/ty/tz + instancer/g/b/a.
    codes = ["instancetx", "instancety", "instancetz",
             "instancer", "instanceg", "instanceb", "instancea", "instanceop"]
    out = srv._collapse_param_families([(c, {"display_name": c}) for c in codes])
    labels = [c for c, _ in out]
    assert "instancet (xyz)" in labels
    assert "instance (rgba)" in labels
    assert "instanceop" in labels                          # non-grouped stays


def test_collapse_lone_scale_not_swallowed():
    # "scale" with no real t/r/s/p component present -> left as its own param.
    out = srv._collapse_param_families([("scale", {}), ("foo", {})])
    labels = [c for c, _ in out]
    assert "scale" in labels and srv._TRANSFORM_LABEL not in labels


def test_collapse_rgba_requires_rgb_present():
    # base with only r+a (no g,b) is NOT a color group -> not collapsed.
    out = srv._collapse_param_families([("xr", {}), ("xa", {})])
    assert [c for c, _ in out] == ["xr", "xa"]


def test_collapse_common_page_folds():
    items = [("color", {}), ("npasses", {"page": "Common"}),
             ("chanmask", {"page": "Common"}), ("format", {"page": "Common"})]
    out = srv._collapse_param_families(items)
    labels = [c for c, _ in out]
    assert srv._COMMON_LABEL in labels
    assert "color" in labels
    assert dict(out)[srv._COMMON_LABEL]["member_count"] == 3


def test_collapse_noop_returns_unchanged():
    items = [("aaa", {}), ("bbb", {})]
    assert srv._collapse_param_families(items) == items


def test_hydrate_collapse_frees_slots_under_cap():
    # 5 transform tuplet codes + 6 distinct params = 11 raw; collapse -> 7 entries,
    # all fit under the cap, so parameters_capped is NOT set and the distinguishing
    # params are all present alongside the single transform entry.
    full = _wiki(["t", "r", "s", "p", "scale", "group", "xord", "rord", "vlength", "lookat", "upvector"])
    result = {"name": "Transform SOP", "metadata": {}}
    srv._hydrate_hit_params(result, full, compact=False)
    assert result["parameter_count"] == 11               # TRUE count untouched
    assert srv._TRANSFORM_LABEL in result["parameters"]
    assert "parameters_capped" not in result             # 7 <= cap
    assert len(result["parameters"]) == 7
    # a distinguishing param that a naive first-12 would have kept anyway, still here
    assert "lookat" in result["parameters"]


def test_hydrate_collapse_still_caps_when_over_after_collapse():
    # 5 transform codes + 20 unrelated = collapse to 21 entries, still > cap.
    full = _wiki(["t", "r", "s", "p", "scale"] + [f"u{i}" for i in range(20)])
    result = {"name": "X", "metadata": {}}
    srv._hydrate_hit_params(result, full, compact=False)
    assert result["parameter_count"] == 25               # TRUE count untouched
    assert len(result["parameters"]) == srv.PARAM_HYDRATE_CAP
    assert result["parameters_capped"] is True
    # the transform entry survives the cap (it is first in order)
    assert srv._TRANSFORM_LABEL in result["parameters"]


# ---------------------------------------------------------------------------
# Part 1 — risk annotations (live surface: real Tool objects)
# ---------------------------------------------------------------------------
def test_live_tools_all_annotated():
    tools = live.TD_LIVE_TOOLS
    assert len(tools) == 22  # W-A2 added get_glsl_status
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
        elif t.name in WRITE_CHECKPOINT_LIVE:
            # D3 WRITE_CHECKPOINT: writes disk (not read-only), no graph mutation,
            # idempotent overwrite. This also locks the constant's shape on the real
            # Tool object (the live analog of test_offline_annotation_constants).
            assert a.readOnlyHint is False and a.destructiveHint is False, t.name
            assert a.idempotentHint is True, t.name
        else:
            assert a.readOnlyHint is True, t.name


def test_live_write_checkpoint_constant_shape():
    """The WRITE_CHECKPOINT constant encodes the intended hints — a NEW class
    distinct from the offline WRITE_ADDITIVE (which pins idempotentHint=False)."""
    wc = live.WRITE_CHECKPOINT
    assert wc.readOnlyHint is False
    assert wc.destructiveHint is False
    assert wc.idempotentHint is True
    # Exactly one WRITE_CHECKPOINT tool on the live surface.
    got = {t.name for t in live.TD_LIVE_TOOLS
           if t.annotations.readOnlyHint is False
           and t.annotations.destructiveHint is False
           and t.annotations.idempotentHint is True}
    assert got == WRITE_CHECKPOINT_LIVE


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


def test_offline_tools_all_annotated_18():
    ann = _offline_tool_annotations()
    assert len(ann) == 18, sorted(ann)
    missing = [n for n, a in ann.items() if a is None]
    assert not missing, f"offline tools missing annotations: {missing}"
    assert set(ann.values()) <= {"READ_ONLY", "WRITE_ADDITIVE",
                                 "WRITE_ADDITIVE_IDEMPOTENT"}


def test_offline_write_class_is_exactly_the_named_two():
    """W4b audit property, W7 rewrite: the write class is a NAMED 2-tool set —
    a deliberate replacement of the old exactly-one-WRITE_ADDITIVE invariant.
    register_component's delete-then-upsert is re-run-safe, so it carries the
    honest idempotent variant (owner decision 1)."""
    ann = _offline_tool_annotations()
    assert ann["td_build_project"] == "WRITE_ADDITIVE"
    assert ann["register_component"] == "WRITE_ADDITIVE_IDEMPOTENT"
    assert ann["td_build_status"] == "READ_ONLY"
    writes = {n for n, v in ann.items() if v != "READ_ONLY"}
    assert writes == {"td_build_project", "register_component"}


def test_offline_annotation_constants_are_correct():
    """The three source constants encode the intended hint values."""
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
    # W7: the honest-True additive-upsert variant (register_component). Same
    # hint triple as the live WRITE_CHECKPOINT but a distinct offline class:
    # idempotent additive registry/index UPSERT vs checkpoint OVERWRITE of a
    # stable target.
    assert consts["WRITE_ADDITIVE_IDEMPOTENT"] == {
        "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}


# ---------------------------------------------------------------------------
# W-C addendum — sequence-block collapse + full pre-hydration name visibility
# ---------------------------------------------------------------------------


def _seq_params(codes):
    return {c: {"code": c, "description": "d", "page": "Uniforms"} for c in codes}


def test_collapse_glsl_uniform_vec_blocks():
    codes = []
    for i in range(2):
        codes += [f"vec{i}name", f"vec{i}type", f"vec{i}valuex", f"vec{i}valuey",
                  f"vec{i}valuez", f"vec{i}valuew"]
    codes.append("active")
    out = srv._collapse_param_families(list(_seq_params(codes).items()))
    labels = [c for c, _ in out]
    # 12 vec-block params -> ONE reconstructible entry; 'active' untouched
    assert len(out) == 2
    assert labels[0].startswith("vec[0-1]{")
    assert "name" in labels[0] and "valuex" in labels[0]
    assert labels[1] == "active"
    desc = out[0][1]
    assert desc["member_count"] == 12
    assert desc["members"][0] == "vec0name"


def test_collapse_single_index_multi_field_block():
    # Attribute POP style: wiki documents only block 0 -> still folds (1 idx, 2 fields)
    out = srv._collapse_param_families(list(_seq_params(["att0name", "att0val", "scope"]).items()))
    labels = [c for c, _ in out]
    assert len(out) == 2
    assert labels[0].startswith("att[0]{")
    assert labels[1] == "scope"


def test_collapse_trailing_index_sequences_separately():
    # Constant CHOP style: name0/value0/name1/value1 -> two block entries
    out = srv._collapse_param_families(
        list(_seq_params(["name0", "value0", "name1", "value1"]).items())
    )
    labels = [c for c, _ in out]
    assert labels == ["name[0-1]", "value[0-1]"]


def test_collapse_input_refs_and_lone_indexed_code():
    out = srv._collapse_param_families(
        list(_seq_params(["input0pop", "input1pop", "custom1"]).items())
    )
    labels = [c for c, _ in out]
    # input refs fold; a lone indexed code ('custom1' - one idx, one field) never does
    assert labels == ["input[0-1]{pop}", "custom1"]


def test_big_sequence_descriptor_is_bounded():
    codes = []
    for i in range(16):
        codes += [f"vec{i}name", f"vec{i}type", f"vec{i}valuex", f"vec{i}valuey",
                  f"vec{i}valuez", f"vec{i}valuew"]
    out = srv._collapse_param_families(list(_seq_params(codes).items()))
    assert len(out) == 1
    desc = out[0][1]
    assert desc["member_count"] == 96
    assert "members" not in desc            # bounded: sample only
    assert len(desc["members_sample"]) == 6


def test_hydrate_parameter_names_visible_in_both_modes():
    codes = ["active", "att0name", "att0val", "tx", "ty", "tz"]
    info = {"wiki_parameters": _seq_params(codes)}
    for compact in (True, False):
        result = {}
        srv._hydrate_hit_params(result, info, compact=compact)
        names = result["parameter_names"]
        assert "active" in names
        assert any(n.startswith("att[0]{") for n in names)
        assert srv._TRANSFORM_LABEL in names
        assert result["parameter_count"] == 6          # TRUE count untouched
        if compact:
            assert "parameters" not in result
        else:
            assert set(result["parameters"].keys()) == set(names)
