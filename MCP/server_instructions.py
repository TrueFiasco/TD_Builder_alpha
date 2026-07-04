"""Single-sourced MCP ``instructions=`` payload loader (harness item 3b / D2).

The TD Builder non-negotiables live in ONE file — ``docs/NON_NEGOTIABLES.md`` —
between the ``<!-- INSTRUCTIONS:BEGIN -->`` / ``<!-- INSTRUCTIONS:END -->``
markers. Both MCP servers (offline ``td-builder`` = ``server_core/mcp_server.py``
and live ``td-builder-live`` = ``live_server.py``) load that marked region into
their ``Server(instructions=...)`` field, so the rules are delivered on the only
always-on channel the delivering clients guarantee (Claude Code / cowork). The
prose below the markers in that file is the per-surface delivery + drift-guard
documentation and is deliberately NOT part of the payload.

Delivery is client-specific (see ``eval/TD_builder audit/D2_CLIENT_DELIVERY.md``):
verbatim on Claude Code, absent on the Claude Desktop chat surface — which is why
``get_server_info`` also returns this payload as the pull-side recovery path.

Design constraints (mirrored by the canary test in
``tests/unit/test_instructions_canary.py``):
  * total payload <= ``MAX_BYTES`` (Claude Code truncates instructions at 2 KB);
  * the catastrophic/silent rules sit in the first 512 characters;
  * loading NEVER raises — a server must always start, so any failure to read or
    parse the file falls back to ``MINIMAL`` (a short pointer, not silence).
"""
from __future__ import annotations

import os
from pathlib import Path

_BEGIN = "<!-- INSTRUCTIONS:BEGIN -->"
_END = "<!-- INSTRUCTIONS:END -->"

# Claude Code truncates instructions at 2 KB; keep the payload safely under.
MAX_BYTES = 2000

# The canonical file, relative to the release root.
CANONICAL_REL = Path("docs") / "NON_NEGOTIABLES.md"

# Fail-soft fallback: short, self-contained, points at the two real sources.
# Used only when the canonical file is missing/unreadable (partial install).
MINIMAL = (
    'td-builder - non-negotiables (full text: docs/NON_NEGOTIABLES.md; deep '
    'gotchas: "td-builder-howto" skill). KB-FIRST: look up operators/params '
    "before creating or configuring - never guess. MENU params are STRING "
    "tokens, never ints. GLSL compile errors are INVISIBLE to node.errors() - "
    "read op('<n>_info').text after any shader edit. PLACE every node "
    "(nodeX/nodeY). SAVE often - TD crashes lose unsaved work. EVERY build "
    "goes through td_build_project. After context compaction, re-read these "
    "instructions / call get_server_info."
)


def _release_root() -> Path:
    """Repo/release root: honor the documented TD_BUILDER_ROOT knob, else infer
    from this module's location (``<root>/MCP/server_instructions.py``)."""
    env = os.environ.get("TD_BUILDER_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def load_instructions(root: Path | None = None) -> str:
    """Return the non-negotiables payload for ``Server(instructions=...)``.

    Reads the marked region of ``docs/NON_NEGOTIABLES.md`` under ``root`` (or the
    inferred release root). Returns ``MINIMAL`` on any failure. Never raises.
    Defensively hard-caps at ``MAX_BYTES`` even though the canary test also
    asserts the source file stays under the cap.
    """
    try:
        base = Path(root) if root is not None else _release_root()
        text = (base / CANONICAL_REL).read_text(encoding="utf-8")
        i = text.index(_BEGIN) + len(_BEGIN)
        j = text.index(_END, i)
        payload = text[i:j].strip()
        if not payload:
            return MINIMAL
        if len(payload.encode("utf-8")) > MAX_BYTES:
            # Truncate on a char boundary that keeps the byte length under cap.
            payload = payload.encode("utf-8")[:MAX_BYTES].decode("utf-8", "ignore").rstrip()
        return payload
    except Exception:
        return MINIMAL
