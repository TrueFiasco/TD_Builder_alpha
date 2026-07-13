"""D2 delivery canary (harness item 3b).

Proves the single-sourced non-negotiables reach the model on the always-on
`instructions=` channel of BOTH MCP servers with the correct **per-server scope**,
stay within the 2 KB cap the delivering clients enforce, and keep each scope's
catastrophic/silent rules in its first 512 characters. Client updates have
silently changed instruction-delivery behavior between CLI versions with no
changelog (see the D2 audit), so this is the per-surface regression tripwire the
audit review asked for.

Scoping (canonical file tags each line [always] / [live-only]):
  * offline `td-builder` server  -> [always] only  (grounding + build + the
    offline-generation capability; the only server Cursor/ChatGPT reach);
  * live `td-builder-live` server -> [always] + [live-only]  (adds the running-TD
    gotchas: GLSL info-DAT, save, place, next-frame reads).

Split by lane:
  * loader / source-file / fail-soft checks are KB-free -> hermetic lane, every PR;
  * the both-servers InitializeResult checks use the `server` / `live_server`
    fixtures (auto-marked requires_kb by tests/conftest.py) -> engine-kb lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP"))

import server_instructions as si  # noqa: E402

HEAD = "td-builder - non-negotiables"
CAP = si.MAX_BYTES  # 2 KB

# Text that identifies each [live-only] rule; MUST be absent from the offline
# payload and present in the live payload.
LIVE_ONLY_MARKERS = ("GLSL COMPILE", "execute_python_script", "SAVE OFTEN", "PLACE EVERY NODE")
# [always] grounding/build rules; present in BOTH payloads.
ALWAYS_MARKERS = ("KB-FIRST", "STRING TOKENS", "EVERY BUILD", "RELATIVE PATHS")


def _no_tags(p: str) -> bool:
    return si._ALWAYS not in p and si._LIVE_ONLY not in p


# --------------------------------------------------------------------------
# KB-free: scoped loader + source file + fail-soft (hermetic lane, every PR)
# --------------------------------------------------------------------------

def test_offline_scope_payload():
    p = si.load_instructions(REPO, scope="offline")
    assert p.startswith(HEAD)
    assert len(p.encode("utf-8")) <= CAP, f"offline payload {len(p.encode('utf-8'))} B > {CAP} B"
    assert all(ord(c) < 128 for c in p), "payload must be ASCII"
    assert _no_tags(p), "scope tags leaked into the delivered payload"
    assert "CAPABILITY:" in p, "offline payload must front the offline-generation capability"
    assert "td_build_project" in p[:512] and "KB-FIRST" in p[:512], "offline front-loading"
    for m in ALWAYS_MARKERS:
        assert m in p, f"offline payload missing [always] rule {m!r}"
    for m in LIVE_ONLY_MARKERS:
        assert m not in p, f"offline payload must NOT carry [live-only] text {m!r}"


def test_live_scope_payload():
    p = si.load_instructions(REPO, scope="live")
    assert p.startswith(HEAD)
    assert len(p.encode("utf-8")) <= CAP, f"live payload {len(p.encode('utf-8'))} B > {CAP} B"
    assert all(ord(c) < 128 for c in p), "payload must be ASCII"
    assert _no_tags(p)
    for m in ALWAYS_MARKERS + LIVE_ONLY_MARKERS:
        assert m in p, f"live payload missing rule {m!r}"
    # Both catastrophic/silent live rules must survive a 512-char truncation.
    assert 0 <= p.find("INVISIBLE") < 512, "GLSL-invisible must be in the live first 512"
    assert 0 <= p.find("NEXT FRAME") < 512, "next-frame-reads rule must be in the live first 512"
    assert "CAPABILITY:" in p


def test_default_scope_is_live():
    """A caller that forgets `scope` gets the complete set, never a silent subset."""
    assert si.load_instructions(REPO) == si.load_instructions(REPO, scope="live")


def test_scopes_differ_offline_subset_of_live():
    off = si.load_instructions(REPO, scope="offline")
    live = si.load_instructions(REPO, scope="live")
    assert off != live, "offline and live payloads must differ"
    assert len(off.encode("utf-8")) < len(live.encode("utf-8"))


def test_loader_failsoft(tmp_path):
    """A missing/unreadable canonical file must degrade to MINIMAL, never raise."""
    for scope in ("offline", "live"):
        got = si.load_instructions(tmp_path, scope=scope)
        assert got == si.MINIMAL
    assert HEAD in si.MINIMAL and "docs/NON_NEGOTIABLES.md" in si.MINIMAL
    assert len(si.MINIMAL.encode("utf-8")) <= CAP


def test_scope_follows_tools_served():
    """A server co-loading the live tools ships the live scope; a pure offline
    server ships offline. Guards the silent-footgun gap: a live-tool surface must
    never ship without its live safety rules."""
    assert si.scope_for_server(True) == "live"
    assert si.scope_for_server(False) == "offline"
    # A co-loaded offline server therefore carries the [live-only] rules.
    coloaded = si.load_instructions(REPO, scope=si.scope_for_server(True))
    assert all(m in coloaded for m in LIVE_ONLY_MARKERS)


# --------------------------------------------------------------------------
# Both servers: InitializeResult.instructions is the correct scope
# (engine-kb lane, every PR)
# --------------------------------------------------------------------------

def _server_instructions(mod) -> str:
    instr = mod.app.create_initialization_options().instructions
    assert instr, "server passes no instructions= (D2 push channel missing)"
    assert instr.startswith(HEAD)
    assert len(instr.encode("utf-8")) <= CAP
    assert _no_tags(instr)
    return instr


def test_offline_server_scope(server):
    instr = _server_instructions(server)
    # Scope follows tools served: whatever this offline server actually co-loads
    # (TD_LIVE_ENABLED) decides its scope. In the standard offline harness it
    # serves no live tools -> offline scope, zero [live-only] text.
    serves_live = bool(getattr(server, "TD_LIVE_ENABLED", False)
                       and getattr(server, "TD_LIVE_TOOLS", None))
    expected = si.load_instructions(REPO, scope=si.scope_for_server(serves_live))
    assert instr == expected
    if not serves_live:
        for m in LIVE_ONLY_MARKERS:
            assert m not in instr, f"pure-offline server leaked [live-only] text {m!r}"


def test_live_server_scope(live_server):
    instr = _server_instructions(live_server)
    for m in ALWAYS_MARKERS + LIVE_ONLY_MARKERS:
        assert m in instr
    assert instr == si.load_instructions(REPO, scope="live")


def test_servers_carry_distinct_scopes(server, live_server):
    off = server.app.create_initialization_options().instructions
    live = live_server.app.create_initialization_options().instructions
    assert off != live


def test_get_server_info_returns_offline_scope(probe):
    """Pull affordance: the offline server's get_server_info re-serves its own
    scoped payload (the recovery path where instructions= is dropped)."""
    r = probe.call("get_server_info", {})
    assert r.ok, r.text[:200]
    data = r.json()["data"]
    assert data.get("non_negotiables_file") == "docs/NON_NEGOTIABLES.md"
    assert data.get("non_negotiables") == si.load_instructions(REPO, scope="offline")
