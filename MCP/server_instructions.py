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

Each line in the marked region is tagged ``[always]`` or ``[live-only]``. The
loader delivers a **per-server scope**:
  * the offline ``td-builder`` server loads ``scope="offline"`` -> ``[always]``
    only (the grounding + build rules that hold with or without TD running; this
    is also the only server Cursor / ChatGPT can reach, so its budget stays
    on-message);
  * the live ``td-builder-live`` server loads ``scope="live"`` -> ``[always]`` +
    ``[live-only]`` (adds the running-TD gotchas: GLSL info-DAT, save, place,
    flat exec scope).
The tags are stripped before delivery.

Design constraints (mirrored by the canary test in
``tests/unit/test_instructions_canary.py``):
  * each scoped payload <= ``MAX_BYTES`` (Claude Code truncates instructions at 2 KB);
  * the catastrophic/silent rules of each scope sit in its first 512 characters
    (offline: offline-generation + KB-first; live: GLSL-invisible + flat-exec);
  * loading NEVER raises — a server must always start, so any failure to read or
    parse the file falls back to ``MINIMAL`` (a short pointer, not silence).
"""
from __future__ import annotations

import os
from pathlib import Path

_BEGIN = "<!-- INSTRUCTIONS:BEGIN -->"
_END = "<!-- INSTRUCTIONS:END -->"

# Per-line scope tags in the canonical file. "offline" keeps only _ALWAYS lines;
# "live" keeps both. Untagged lines are treated as _ALWAYS (delivered by both).
_ALWAYS = "[always]"
_LIVE_ONLY = "[live-only]"

# Claude Code truncates instructions at 2 KB; keep each scoped payload safely under.
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


def scope_for_server(serves_live_tools: bool) -> str:
    """Scope FOLLOWS TOOLS SERVED.

    A server that exposes the live-TD tools must ship the live rules — including
    the catastrophic-silent ones (GLSL-invisible-errors, flat-exec-scope) — even
    when it is the "offline" ``td-builder`` server co-loading them via
    ``TD_LIVE_ENABLED``. Shipping a live-tool surface without its live safety
    rules is exactly the silent-footgun class these rules warn against. A pure
    offline server (no live tools) ships the ``[always]`` scope only.
    """
    return "live" if serves_live_tools else "offline"


def _release_root() -> Path:
    """Repo/release root: honor the documented TD_BUILDER_ROOT knob, else infer
    from this module's location (``<root>/MCP/server_instructions.py``)."""
    env = os.environ.get("TD_BUILDER_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def load_instructions(root: Path | None = None, scope: str = "live") -> str:
    """Return the scoped non-negotiables payload for ``Server(instructions=...)``.

    ``scope="offline"`` keeps only ``[always]`` lines; ``scope="live"`` (default,
    the complete set) keeps both. Tags are stripped. Reads the marked region of
    ``docs/NON_NEGOTIABLES.md`` under ``root`` (or the inferred release root).
    Returns ``MINIMAL`` on any failure. Never raises. Defensively hard-caps at
    ``MAX_BYTES`` even though the canary test also asserts the source file's
    per-scope region stays under the cap.
    """
    try:
        base = Path(root) if root is not None else _release_root()
        text = (base / CANONICAL_REL).read_text(encoding="utf-8")
        i = text.index(_BEGIN) + len(_BEGIN)
        j = text.index(_END, i)
        region = text[i:j].strip()
        if not region:
            return MINIMAL

        keep_live = scope != "offline"
        out: list[str] = []
        for line in region.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith(_LIVE_ONLY):
                if keep_live:
                    out.append(s[len(_LIVE_ONLY):].strip())
            elif s.startswith(_ALWAYS):
                out.append(s[len(_ALWAYS):].strip())
            else:
                out.append(s)  # untagged -> both scopes
        payload = "\n".join(out).strip()
        if not payload:
            return MINIMAL
        if len(payload.encode("utf-8")) > MAX_BYTES:
            # Truncate on a char boundary that keeps the byte length under cap.
            payload = payload.encode("utf-8")[:MAX_BYTES].decode("utf-8", "ignore").rstrip()
        return payload
    except Exception:
        return MINIMAL
