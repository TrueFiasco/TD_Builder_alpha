#!/usr/bin/env python3
r"""In-process td-builder server bridge for Lane R + identity capture.

Reuses the proven test scaffolding verbatim (tests/measure/_server.py loader +
tests/measure/probe.py Probe — the probe pattern the design names as the
replay lane's execution engine). Heavy: importing the server pulls the full
dependency stack; only Lane R and identity capture come through here — the
scorer's out-of-band validation deliberately imports the ENGINE directly
(score.py) so it stays runnable in the light-deps CI lanes.
"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_EVAL_DIR.parents[1]

_PROBE = None
_WARMED = False


def get_probe():
    """Lazy singleton Probe over the in-process server (loaded once)."""
    global _PROBE
    if _PROBE is None:
        tests_dir = str(REPO_ROOT / "tests")
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
        from measure._server import load_server
        from measure.probe import Probe
        _PROBE = Probe(load_server())
    return _PROBE


def ensure_warm():
    """Blocking KB warm-up (the explicit load tests/conftest.py's probe fixture
    does) so replay tool calls never see kb_warming envelopes."""
    global _WARMED
    if _WARMED:
        return
    probe = get_probe()
    ensure = getattr(probe.mod, "_ensure_kb", None)
    if callable(ensure):
        ensure()
    _WARMED = True


def tool_names() -> list[str]:
    return sorted(t.name for t in get_probe().list_tools())


# --- live surface (td-builder-live) --------------------------------------
# The live tool LIST is static data in MCP/live_client/td_live_client.py —
# importing it never touches TouchDesigner (handlers only connect when
# called), so the live inventory is stampable on machines with no TD at all.
_LIVE_PROBE = None


def live_tool_names() -> list[str]:
    live_client = str(REPO_ROOT / "MCP" / "live_client")
    if live_client not in sys.path:
        sys.path.insert(0, live_client)
    import td_live_client
    return sorted(t.name for t in td_live_client.TD_LIVE_TOOLS)


def get_live_probe():
    """Lazy singleton Probe over the in-process LIVE server (Lane R, live
    scenarios only). Calls through it reach the running TouchDesigner's
    WebServer DAT — callers gate on the td_live_running precondition first."""
    global _LIVE_PROBE
    if _LIVE_PROBE is None:
        tests_dir = str(REPO_ROOT / "tests")
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
        from measure._server import load_live_server
        from measure.probe import Probe
        _LIVE_PROBE = Probe(load_live_server())
    return _LIVE_PROBE


def server_version() -> str | None:
    r = get_probe().call("get_server_info", {})
    data = r.json() or {}
    return ((data.get("data") or {}).get("version")) or data.get("version")
