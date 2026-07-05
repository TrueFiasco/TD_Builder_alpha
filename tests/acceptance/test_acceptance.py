"""Conventional pass/fail acceptance tests for the td-builder MCP server.

Exercises the key-free tool surface — 17 offline (`td-builder`) +
19 live (`td-builder-live`) tools — across prompts P1-P19. Run it and every
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


# --------------------------------------------------------------------------
# P1-P9  base knowledge tools (Mode 1, offline)
# --------------------------------------------------------------------------

def test_p01_server_identity(probe):
    r = probe.call("get_server_info", {})
    assert r.ok, f"errored: {r.text[:200]}"
    d = r.json()
    assert d["ok"] is True
    assert "mcp_server.py" in d["data"]["script_path"]
    assert d["data"]["version"] == "0.2.0"


def test_p01b_tool_inventory(probe):
    names = sorted(t.name for t in probe.list_tools())
    assert len(names) == 17, f"expected 17 offline tools, got {len(names)}: {names}"
    for required in ("get_server_info", "td_validate", "td_convert",
                     "td_build_project", "td_build_status", "hybrid_search",
                     "query_graph", "expand_toe_file"):
        assert required in names
    # API / agent-spawning tools removed for the key-free release
    for gone in ("spawn_engineer", "spawn_expert", "td_compact_expertise"):
        assert gone not in names, f"{gone} should be removed"


def test_p01c_server_compat(probe):
    """W5: get_server_info surfaces a server<->KB version-compat block. Shipped server and
    shipped KB are both 0.2.0 -> compatible. WARN-not-fail policy is advertised."""
    r = probe.call("get_server_info", {})
    assert r.ok, f"errored: {r.text[:200]}"
    d = r.json()
    compat = d["data"]["compat"]
    assert isinstance(compat, dict), f"compat missing/malformed: {compat!r}"
    for key in ("compatible", "status", "server_version", "kb_version", "kb_td_build", "policy"):
        assert key in compat, f"compat missing key {key!r}: {compat}"
    assert compat["policy"] == "warn"
    # Shipped release: SERVER_VERSION == KB manifest version == 0.2.0.
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
# P10 / P16-P19  live-TD tools
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
    name = "td_accept_tmp"
    path = f"/project1/{name}"
    try:
        c = live_probe.call("create_td_node", {"parent_path": "/project1",
                                               "node_type": "constantCHOP",
                                               "node_name": name})
        assert c.ok, c.text[:200]
        u = live_probe.call("update_td_node_parameters",
                            {"node_path": path, "properties": {"value0": 0.5}})
        assert u.ok, u.text[:200]
    finally:
        live_probe.call("delete_td_node", {"node_path": path})
