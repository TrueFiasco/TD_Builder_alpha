"""De-risk the in-process seam: import the server, list tools, call the two
cheapest deterministic tools (get_server_info, td_validate). No KB, no API,
no TD. If this fails, every target fails — so keep it first and minimal.
"""
from __future__ import annotations

SMOKE_NET = {
    "meta": {"project_name": "smoke", "mode": "toe"},
    "operators": [
        {"name": "noise1", "family": "CHOP", "type": "noise"},
        {"name": "null1", "family": "CHOP", "type": "null",
         "inputs": [{"index": 0, "src": "noise1"}]},
    ],
}


def test_server_identity(probe):
    r = probe.call("get_server_info", {})
    assert r.ok, f"get_server_info errored: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, dict) and data.get("ok") is True
    sp = data["data"]["script_path"]
    assert "mcp_server.py" in sp, f"unexpected script_path: {sp}"
    print(f"\nserver {data['data']['version']} @ {sp} "
          f"(td_live={data['data']['td_live_enabled']}, "
          f"{r.latency_s*1000:.0f}ms, ~{r.resp_tokens}tok)")


def test_tool_inventory(probe):
    tools = probe.list_tools()
    names = sorted(t.name for t in tools)
    assert len(names) == 15, f"expected 15 offline tools, got {len(names)}: {names}"
    assert "get_server_info" in names
    assert "td_validate" in names and "td_build_project" in names
    print(f"\n{len(names)} tools exposed")


def test_validate_runs_five_stages(probe):
    r = probe.call("td_validate", {"network": SMOKE_NET, "verbose": True})
    assert r.ok, f"td_validate errored: {r.text[:300]}"
    data = r.json()
    assert isinstance(data, dict) and "valid" in data
    stages = data.get("stages", {})
    assert stages, f"verbose td_validate returned no stages: {data}"
    print(f"\ntd_validate: valid={data['valid']} "
          f"stages={list(stages)} ({r.latency_s*1000:.0f}ms)")
