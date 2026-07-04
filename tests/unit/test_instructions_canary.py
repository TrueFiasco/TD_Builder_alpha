"""D2 delivery canary (harness item 3b).

Proves the single-sourced non-negotiables actually reach the model on the
always-on `instructions=` channel of BOTH MCP servers, stay within the 2 KB cap
the delivering clients enforce, and keep the catastrophic/silent rules in the
first 512 characters. Client updates have silently changed instruction-delivery
behavior between CLI versions with no changelog (see the D2 audit), so this is
the per-surface regression tripwire the audit review asked for.

Split by lane:
  * loader / source-file / fail-soft checks are KB-free -> run in the hermetic
    CI lane on every PR;
  * the both-servers InitializeResult checks use the `server` / `live_server`
    fixtures (auto-marked requires_kb by tests/conftest.py) -> run in the
    engine-kb lane on every PR, where the modules load with the KB present.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP"))

import server_instructions as si  # noqa: E402

# Stable head sentence (also the canary substring the delivery checks assert).
HEAD = "td-builder - non-negotiables"
CAP = si.MAX_BYTES  # 2 KB
CANONICAL = REPO / "docs" / "NON_NEGOTIABLES.md"

# The three SILENT-failure rules (KB-guessing, menu-int, GLSL-invisible) that
# MUST survive a 512-char truncation — the ones a model gets no error signal for.
FRONT_ANCHORS = ("KB-FIRST", "STRING TOKENS", "INVISIBLE")


def _extract_region(text: str) -> str:
    i = text.index(si._BEGIN) + len(si._BEGIN)
    j = text.index(si._END, i)
    return text[i:j].strip()


# --------------------------------------------------------------------------
# KB-free: loader + source file + fail-soft (hermetic lane, every PR)
# --------------------------------------------------------------------------

def test_loader_payload_shape():
    p = si.load_instructions(REPO)
    assert p.startswith(HEAD), f"head sentence missing: {p[:60]!r}"
    assert len(p.encode("utf-8")) <= CAP, f"payload {len(p.encode('utf-8'))} B > {CAP} B cap"
    assert all(ord(c) < 128 for c in p), "payload must be ASCII (avoids client encoding/byte inflation)"
    # Front-loading: the silent/catastrophic rules live in the first 512 chars.
    head512 = p[:512]
    for anchor in FRONT_ANCHORS:
        assert anchor in head512, f"{anchor!r} must be within the first 512 chars (front-loading)"
    # Compaction-survival instruction is present somewhere in the payload.
    assert "COMPACTION" in p


def test_source_file_region_under_cap():
    """The canonical file's marked region must itself stay <= cap.

    The loader hard-caps defensively, but that would silently truncate — this
    fails loudly if an editor grows the payload past 2 KB.
    """
    region = _extract_region(CANONICAL.read_text(encoding="utf-8"))
    assert region.startswith(HEAD)
    assert len(region.encode("utf-8")) <= CAP, (
        f"docs/NON_NEGOTIABLES.md payload region is {len(region.encode('utf-8'))} B "
        f"(> {CAP} B). Trim it — the loader would otherwise truncate silently."
    )


def test_loader_failsoft(tmp_path):
    """A missing/unreadable canonical file must degrade to MINIMAL, never raise."""
    got = si.load_instructions(tmp_path)  # empty dir, no docs/NON_NEGOTIABLES.md
    assert got == si.MINIMAL
    assert HEAD in si.MINIMAL and "docs/NON_NEGOTIABLES.md" in si.MINIMAL
    assert len(si.MINIMAL.encode("utf-8")) <= CAP


# --------------------------------------------------------------------------
# Both servers: InitializeResult.instructions (engine-kb lane, every PR)
# --------------------------------------------------------------------------

def _assert_server_instructions(mod):
    instr = mod.app.create_initialization_options().instructions
    assert instr, "server passes no instructions= (D2 push channel missing)"
    assert instr.startswith(HEAD), f"instructions head sentence missing: {instr[:60]!r}"
    assert len(instr.encode("utf-8")) <= CAP, f"instructions {len(instr.encode('utf-8'))} B > {CAP} B"
    return instr


def test_offline_server_instructions(server):
    _assert_server_instructions(server)


def test_live_server_instructions(live_server):
    _assert_server_instructions(live_server)


def test_both_servers_identical_instructions(server, live_server):
    """Same single source -> byte-identical payload on both servers."""
    off = server.app.create_initialization_options().instructions
    live = live_server.app.create_initialization_options().instructions
    assert off == live


def test_get_server_info_returns_non_negotiables(probe):
    """Pull affordance: get_server_info re-serves the full payload (the recovery
    path on surfaces where instructions= is dropped, e.g. Claude Desktop chat)."""
    r = probe.call("get_server_info", {})
    assert r.ok, r.text[:200]
    data = r.json()["data"]
    assert data.get("non_negotiables_file") == "docs/NON_NEGOTIABLES.md"
    assert data.get("non_negotiables", "").startswith(HEAD)
