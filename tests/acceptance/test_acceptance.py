"""Conventional pass/fail acceptance tests for the td-builder MCP server.

Exercises the key-free tool surface — 18 offline (`td-builder`) +
22 live (`td-builder-live`) tools — across prompts P1-P21. Run it and every
tool/feature shows PASSED or FAILED:

    & $PY -m pytest tests/acceptance -v

See tests/README.md for the gate overview. Scoring rules:
  - An unhandled exception / error envelope where success is expected = FAIL.
  - Live-TD tools with TouchDesigner not running: a clear "not running"
    message is a PASS (graceful fallback); if TD is up they must return real
    data.
  - Known limitations (find_similar_networks may be []; BASIC-mode build
    warnings) count as PASS when they return without error.
"""
from __future__ import annotations

import os
import uuid

import pytest

NET = {
    "meta": {"project_name": "smoke", "mode": "toe"},
    "operators": [
        {"name": "noise1", "family": "CHOP", "type": "noise"},
        {"name": "null1", "family": "CHOP", "type": "null",
         "inputs": [{"index": 0, "src": "noise1"}]},
    ],
}
BUILD_DESIGN = {
    "operators": [
        {"name": "noise1", "type": "noise", "family": "CHOP"},
        {"name": "null1", "type": "null", "family": "CHOP"},
    ],
    "connections": [{"from": "noise1", "to": "null1"}],
}

LIVE_MSG = ("touchdesigner not running", "webserver dat", "9981")


def _is_graceful_live_down(r) -> bool:
    t = r.text.lower()
    return any(k in t for k in LIVE_MSG)


def _route_absent(r) -> bool:
    """True when the running TD returned a route-absent signal for a route that is
    not present in its install-tree modules yet. The D3 routes (save_td_project,
    get_mutation_status) only go live once the OWNER syncs the install tree +
    restarts TD (plan §11 'Live' step) — until then a running TD 404s them, and the
    corresponding acceptance test must SKIP, not FAIL. Matched EXACTLY (R5d): the
    router's literal 404 text ('No route matched for ...', openapi_router.py) and
    the stale-client dispatch miss ('Unknown live tool: ...', live_server.py) — a
    broad 'not found' would mis-skip on real errors that merely contain the phrase
    (e.g. 'Node not found at path')."""
    t = r.text.lower()
    return "no route matched" in t or "unknown live tool" in t


# --------------------------------------------------------------------------
# P1-P9  base knowledge tools (Mode 1, offline)
# --------------------------------------------------------------------------

def test_p01_server_identity(probe):
    r = probe.call("get_server_info", {})
    assert r.ok, f"errored: {r.text[:200]}"
    d = r.json()
    assert d["ok"] is True
    assert "mcp_server.py" in d["data"]["script_path"]
    assert d["data"]["version"] == "0.2.1"


def test_p01b_tool_inventory(probe):
    names = sorted(t.name for t in probe.list_tools())
    assert len(names) == 18, f"expected 18 offline tools, got {len(names)}: {names}"
    for required in ("get_server_info", "td_validate", "td_convert",
                     "td_build_project", "td_build_status", "hybrid_search",
                     "query_graph", "expand_toe_file", "register_component"):
        assert required in names
    # API / agent-spawning tools removed for the key-free release
    for gone in ("spawn_engineer", "spawn_expert", "td_compact_expertise"):
        assert gone not in names, f"{gone} should be removed"


def test_p01c_server_compat(probe):
    """W5: get_server_info surfaces a server<->KB version-compat block. v0.2.1 ships server
    0.2.1 against the unchanged 0.2.0 KB bundle; compat compares at semver-MINOR granularity
    (compat._minor_tuple), so (0,2) == (0,2) -> compatible. WARN-not-fail policy is advertised."""
    r = probe.call("get_server_info", {})
    assert r.ok, f"errored: {r.text[:200]}"
    d = r.json()
    compat = d["data"]["compat"]
    assert isinstance(compat, dict), f"compat missing/malformed: {compat!r}"
    for key in ("compatible", "status", "server_version", "kb_version", "kb_td_build", "policy"):
        assert key in compat, f"compat missing key {key!r}: {compat}"
    assert compat["policy"] == "warn"
    # Shipped release: SERVER_VERSION 0.2.1 vs KB manifest 0.2.0 -> same (major, minor).
    assert compat["compatible"] is True and compat["status"] == "compatible", compat
    assert compat["server_version"] == d["data"]["version"]
    assert compat["kb_version"] == d["data"]["kb_version"]


def test_p02_operator_info_and_param_detail(probe):
    a = probe.call("get_operator_info", {"operator_name": "Noise CHOP",
                                         "compact": True})
    assert a.ok and isinstance(a.json(), dict), a.text[:200]
    b = probe.call("get_parameter_detail", {"operator_name": "Noise CHOP",
                                             "parameter_name": "amp"})
    assert b.ok, b.text[:200]
    assert "not found" not in b.text.lower()


def test_p02b_parameter_detail_compound_leaf_fallback(probe):
    # F7: pt0pos is a compound header on Point POP with no discrete leaf entry in the
    # KB; pt0posx now resolves via the compound-parent fallback instead of 404ing.
    r = probe.call("get_parameter_detail", {"operator_name": "Point POP",
                                            "parameter_name": "pt0posx"})
    assert r.ok, r.text[:200]
    assert "not found" not in r.text.lower()
    d = r.json()
    assert d.get("leaf_of_compound") is True
    assert d.get("code") == "pt0pos"
    assert d.get("requested_parameter") == "pt0posx"


def test_p02c_parameter_detail_exact_match_unaffected(probe):
    # F7 guard: an exact hit is unchanged (no leaf annotation); a genuine miss still
    # says "not found" and is NOT masked by the fallback.
    r1 = probe.call("get_parameter_detail", {"operator_name": "Point POP",
                                             "parameter_name": "pt0pos"})
    assert r1.ok, r1.text[:200]
    d1 = r1.json()
    assert d1.get("code") == "pt0pos"
    assert "leaf_of_compound" not in d1
    r2 = probe.call("get_parameter_detail", {"operator_name": "Point POP",
                                             "parameter_name": "zzznotaparam"})
    assert "not found" in r2.text.lower()


def test_p02d_operator_info_not_found_is_explicit(probe):
    # F6b: a KB miss returns an explicit found:false object (never the literal `null`),
    # in BOTH compact modes, echoing the requested name.
    for compact in (False, True):
        r = probe.call("get_operator_info", {"operator_name": "Not A Real Operator XYZ",
                                             "compact": compact})
        assert r.ok, r.text[:200]
        assert r.text.strip().lower() != "null"
        d = r.json()
        assert isinstance(d, dict) and d.get("found") is False, d
        assert d.get("operator_name") == "Not A Real Operator XYZ"
    # A near-miss populates spelling suggestions.
    r = probe.call("get_operator_info", {"operator_name": "Noise CHP"})
    assert r.json().get("suggestions"), r.text[:200]


def test_p02e_has_examples_invariant_and_multiword_lookup(probe):
    # F6c: has_examples must never contradict example_count.
    for op in ("GLSL POP", "SOP to CHOP", "Composite TOP"):
        r = probe.call("get_operator_info", {"operator_name": op})
        assert r.ok, r.text[:200]
        d = r.json()
        assert bool(d.get("example_count", 0)) == bool(d.get("has_examples")), \
            (op, d.get("example_count"), d.get("has_examples"))
    # F6d: a multi-word wiki name now resolves servable examples (was [] pre-fix).
    ex = probe.call("find_operator_examples", {"operator_name": "SOP to CHOP"})
    assert ex.ok, ex.text[:200]
    assert isinstance(ex.json(), list) and len(ex.json()) > 0, ex.text[:200]


def test_p02f_expand_toe_file_path_alias(probe):
    # F6a: `path` is accepted as an alias for `toe_path` (reaches the handler instead of
    # a schema rejection); neither key yields the friendly _expand_err naming both.
    r = probe.call("expand_toe_file", {"path": "/nonexistent_xyz.toe"})
    d = r.json()
    assert isinstance(d, dict) and d.get("ok") is False, d
    assert "not found" in d["error"]["message"].lower()   # handler ran, path honored
    r2 = probe.call("expand_toe_file", {})
    d2 = r2.json()
    assert "toe_path" in d2["error"]["message"] and "path" in d2["error"]["message"]


def test_p03_hybrid_search(probe):
    r = probe.call("hybrid_search", {
        "query": "how do I create a feedback loop with a Feedback TOP and a Level TOP",
        "n_results": 3})
    assert r.ok, r.text[:200]
    d = r.json()
    assert isinstance(d, dict) and d.get("semantic_results")


def test_p04_query_graph(probe):
    fam = probe.call("query_graph", {"command": "family", "family": "TOP",
                                     "compact": True})
    assert fam.ok, fam.text[:200]
    params = probe.call("query_graph", {"command": "params",
                                        "operator": "Feedback TOP"})
    assert params.ok, params.text[:200]
    rel = probe.call("query_graph", {"command": "related",
                                     "operator": "Composite TOP"})
    assert rel.ok, rel.text[:200]


def test_p05_list_pop_operators(probe):
    r = probe.call("list_pop_operators", {})
    assert r.ok, r.text[:200]
    d = r.json()
    assert d, "empty POP operator list"


def test_p06_examples_and_similarity(probe):
    ex = probe.call("find_operator_examples", {"operator_name": "Composite TOP"})
    assert ex.ok, ex.text[:200]
    # find_similar_networks may legitimately return [] (W5.3) — PASS if no error
    sim = probe.call("find_similar_networks",
                      {"example_id": "analyzeCHOP/example1"})
    assert sim.ok or sim.json() == [], sim.text[:200]


def test_p07_combination_and_param_usage(probe):
    c = probe.call("find_operator_combination", {"operator_types": ["Noise TOP"]})
    assert c.ok, c.text[:200]
    u = probe.call("find_parameter_usage", {"operator_type": "Transform TOP",
                                            "compact": True})
    assert u.ok, u.text[:200]


def test_p08_network_patterns(probe):
    r = probe.call("get_network_patterns", {})
    assert r.ok, r.text[:200]


def test_p09_expert_prompt(probe):
    r = probe.call("get_expert_prompt", {"expert_name": "td_designer",
                                         "phase": "build"})
    assert r.ok, r.text[:200]
    assert len(r.text.strip()) > 50, "expert prompt suspiciously short"


# --------------------------------------------------------------------------
# P11-P14  offline engine tools
# --------------------------------------------------------------------------

def test_p11_validate_pipeline_stages(probe):
    r = probe.call("td_validate", {"network": NET, "verbose": True})
    assert r.ok, r.text[:200]
    d = r.json()
    assert "valid" in d
    # Stage set: the original 5 + W3a's advisory stages — 2.5 grounding (family-correctness
    # vs live-TD KB) and 3.5 component_wiring (a component is never a data source, BUG-3).
    assert set(d.get("stages", {})) == {
        "schema", "semantic", "grounding", "reference", "component_wiring",
        "logical", "td_rules"}


def test_p12_convert_builder_to_canonical(probe):
    r = probe.call("td_convert", {"network": NET, "source_layer": "builder",
                                  "target_layer": "canonical"})
    assert r.ok, r.text[:200]
    assert isinstance(r.json(), dict)


def test_p13_build_offline(probe):
    r = probe.call("td_build_project", {"design": BUILD_DESIGN,
                                        "project_name": "smoke_build",
                                        "mode": "tox"})
    # BASIC-mode parameter warnings are a documented limitation -> still PASS
    # as long as it produced output without an error envelope.
    if not r.ok:
        # A real .tox needs TD's toecollapse ("headless yes, TD-free no").
        # On a machine WITHOUT the binary (hosted CI) the only acceptable
        # failure is the collapse-class envelope; with the binary present,
        # any error is a real regression.
        from paths import resolve_td_tool
        assert resolve_td_tool("toecollapse") is None, \
            f"build errored WITH toecollapse available: {r.text[:300]}"
        assert "did not produce output file" in r.text, \
            f"non-collapse failure on a TD-absent machine: {r.text[:300]}"
        return
    assert r.ok, f"build errored: {r.text[:300]}"


def test_p14_expand_toe_file(probe, tmp_path):
    # Graceful error on a bad path (no TouchDesigner / no toeexpand needed):
    # the tool reports an error envelope (probe .ok is False) rather than crashing.
    bad = probe.call("expand_toe_file", {"toe_path": str(tmp_path / "nope.toe")})
    assert not bad.ok, f"bad path should be a graceful error: {bad.text[:200]}"
    assert "not found" in bad.text.lower(), bad.text[:200]
    # Functional: build a tiny network offline, then summarize its expanded dir
    # (passing the .toe.dir skips toeexpand, so this stays hermetic).
    b = probe.call("td_build_project", {"design": BUILD_DESIGN,
                                        "project_name": "expand_probe",
                                        "mode": "tox", "output_dir": str(tmp_path)})
    if not b.ok:
        # TD-absent tolerance (see test_p13): accept ONLY the collapse-class
        # envelope, and only when toecollapse genuinely isn't on this machine.
        # The pre-collapse .dir usually survives — if it does, the functional
        # expand half below still runs at full strength, TD-free.
        from paths import resolve_td_tool
        assert resolve_td_tool("toecollapse") is None, \
            f"build errored WITH toecollapse available: {b.text[:300]}"
        assert "did not produce output file" in b.text, \
            f"non-collapse failure on a TD-absent machine: {b.text[:300]}"
    dirs = list(tmp_path.glob("*.dir"))
    if not b.ok and not dirs:
        return  # graceful envelope verified; no pre-collapse dir left to expand
    assert dirs, f"build produced no .dir: {list(tmp_path.iterdir())}"
    s = probe.call("expand_toe_file", {"toe_path": str(dirs[0]), "mode": "summary"})
    assert s.ok, s.text[:300]
    sd = s.json()
    assert sd.get("ok") is True, f"summary not ok: {sd}"
    assert sd["data"]["node_count"] >= 1, f"no nodes: {sd['data']}"
    print(f"\nexpand_toe_file: {sd['data']['node_count']} nodes, "
          f"{sd['data']['connection_count']} connections")


# --------------------------------------------------------------------------
# P10 / P16-P21  live-TD tools
#   TD up   -> must return real data
#   TD down -> must degrade gracefully (clear "not running" message) = PASS
# --------------------------------------------------------------------------

def test_p10_td_python_class_docs(live_probe, td_live):
    r = live_probe.call("get_td_classes", {})
    if td_live:
        assert r.ok, r.text[:200]
    else:
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"


def test_p16_live_identity_topology(live_probe, td_live):
    r = live_probe.call("get_td_info", {})
    if td_live:
        assert r.ok, r.text[:200]
    else:
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"


def test_p17_live_capture(live_probe, td_live):
    r = live_probe.call("get_top_info", {"operator_path": "/project1/out1"})
    if td_live:
        # Whatever project happens to be open may not contain the standard
        # probe target. Before the classifier learned the "Failed to ..."
        # prefix this case PASSED vacuously (ok=True on the error string);
        # a visible skip is the honest version of that tolerance.
        if "Operator not found" in r.text:
            pytest.skip("open TD project has no /project1/out1 (not the "
                        "standard test project) - capture target unavailable")
        assert r.ok or r.images >= 1, r.text[:200]
    else:
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"


def test_p18_live_diagnostics(live_probe, td_live):
    r = live_probe.call("get_error_summary", {})
    if td_live:
        assert r.ok, r.text[:200]
    else:
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"


def test_p19_live_crud_roundtrip(live_probe, td_live):
    if not td_live:
        r = live_probe.call("create_td_node", {"parent_path": "/project1",
                                               "node_type": "constantCHOP",
                                               "node_name": "td_accept_probe"})
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"
        return
    # A reachable :9981 is NOT consent to mutate whatever project is open (it
    # could be a live show). The CRUD branch is explicit opt-in, and runs in
    # its own throwaway container so /project1 (or its absence) is irrelevant.
    if os.environ.get("TD_ACCEPT_LIVE") != "1":
        pytest.skip("TouchDesigner is reachable on :9981 but TD_ACCEPT_LIVE=1 is "
                    "not set - the live CRUD branch mutates the open project; set "
                    "TD_ACCEPT_LIVE=1 to opt in (runs sandboxed in a temp container)")
    sandbox = f"p19_sandbox_{uuid.uuid4().hex[:8]}"
    sandbox_path = f"/{sandbox}"
    created = False
    try:
        s = live_probe.call("create_td_node", {"parent_path": "/",
                                               "node_type": "containerCOMP",
                                               "node_name": sandbox})
        # Flag BEFORE the asserts: a create that succeeded but with an
        # anomalous reply must still be torn down in finally.
        created = s.ok
        assert s.ok, s.text[:200]
        assert sandbox in s.text, f"sandbox create reply dropped the name: {s.text[:200]}"
        name = "td_accept_tmp"
        path = f"{sandbox_path}/{name}"
        c = live_probe.call("create_td_node", {"parent_path": sandbox_path,
                                               "node_type": "constantCHOP",
                                               "node_name": name})
        assert c.ok, c.text[:200]
        # F1: the reply must surface the assigned name and TD op type, not just a path.
        assert name in c.text, f"created-node reply dropped the name: {c.text[:200]}"
        assert "constantCHOP" in c.text, f"created-node reply dropped the type: {c.text[:200]}"
        u = live_probe.call("update_td_node_parameters",
                            {"node_path": path, "properties": {"value0": 0.5}})
        assert u.ok, u.text[:200]
    finally:
        if created:
            # Deleting the container takes the children with it - one call.
            live_probe.call("delete_td_node", {"node_path": sandbox_path})


def test_p20_live_save_checkpoint(live_probe, td_live):
    """D3: save_td_project takes a dialog-proof checkpoint (or a clean "save first"
    message for a never-saved project). TD down -> graceful; route not yet synced
    into the running install tree -> SKIP (owner's §11 live step)."""
    r = live_probe.call("save_td_project", {})
    if not td_live:
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"
        return
    if _route_absent(r):
        pytest.skip("save_td_project route not in the running TD (install tree not "
                    "synced) — owner's §11 live verification step")
    # Either a real checkpoint, or the honest fail-fast for an unsaved project —
    # both are correct, non-crashing behavior (never a modal, never a raise).
    assert r.ok or "save" in r.text.lower(), r.text[:200]


def test_p21_live_mutation_status(live_probe, td_live):
    """D3: get_mutation_status is a pure state read (post-timeout recovery). TD down
    -> graceful; route not yet synced into the running install tree -> SKIP."""
    r = live_probe.call("get_mutation_status", {})
    if not td_live:
        assert _is_graceful_live_down(r), f"not graceful: {r.text[:200]}"
        return
    if _route_absent(r):
        pytest.skip("get_mutation_status route not in the running TD (install tree "
                    "not synced) — owner's §11 live verification step")
    assert r.ok, r.text[:200]
