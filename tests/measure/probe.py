"""In-process tool-call probe + cross-cutting metrics capture.

Every tool call goes through `Probe.call`, which records, regardless of the
tool's primary target:
  - response size in estimated tokens (and an approximate USD cost),
  - wall-clock latency,
  - whether the response was a structured error envelope / error string,
  - a coarse output-quality signal (valid JSON, error-message actionability).

These are the cross-cutting metrics that make even "contract" tools
(get_server_info, the Mode-2 envelope, live-fallback messages) improvable on
cost / latency / actionability rather than just "passes".
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

# Approx Claude pricing (mirrors META_AGENTIC_TOOL metrics.py constants).
_COST_PER_1K_INPUT = 0.015
_COST_PER_1K_OUTPUT = 0.075


def estimate_tokens(s: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token)."""
    return max(1, round(len(s) / 4))


def _looks_actionable(text: str) -> float:
    """0..1 heuristic: does an error/fallback message name a cause AND a remedy?

    Rewards messages that tell the user what to do (port 9981, import the tox,
    set ANTHROPIC_API_KEY, MODES.md, a concrete path). Used by the crosscut
    target to drive error-message quality up, not just presence.
    """
    t = text.lower()
    cause = any(k in t for k in ("not running", "not available", "not initialized",
                                 "requires an api key", "not found", "unavailable",
                                 "not set", "failed", "error"))
    remedy = any(k in t for k in ("9981", "anthropic_api_key", "mode 2", "modes.md",
                                  "import ", "pip install", "set ", "see docs",
                                  "webserver dat", "hint"))
    if cause and remedy:
        return 1.0
    if cause or remedy:
        return 0.5
    return 0.0


@dataclass
class ToolResult:
    name: str
    ok: bool                       # True unless an error envelope/string/exception text
    text: str                      # concatenated TextContent
    data: Any                      # parsed JSON (dict/list) or None
    images: int                    # count of ImageContent parts
    latency_s: float
    resp_tokens: int
    cost_usd: float
    error_kind: str | None         # None | "string" | "envelope" | "exception_text"
    actionability: float           # 0..1 (only meaningful when not ok)

    def json(self) -> Any:
        return self.data


def _classify(text: str, data: Any) -> tuple[bool, str | None]:
    stripped = text.lstrip()
    # The live client's error strings come in three shapes the bare "Error:"
    # check missed: f"TD Error: {...}" / f"TD Error ({status}): {...}" (non-200
    # HTTP) and f"Failed: {...}" / f"Failed to get X: {...}" (success=False
    # payloads). They evaded classification, so `assert r.ok` was toothless
    # against them.
    if stripped.startswith(("Error:", "ERROR:", "TD Error:", "TD Error (",
                            "Failed:", "Failed to ")):
        kind = "exception_text" if "Traceback (most recent call last)" in text else "string"
        return False, kind
    if isinstance(data, dict):
        if data.get("ok") is False:
            return False, "envelope"
        if "error" in data and data.get("error"):
            return False, "envelope"
        if str(data.get("status", "")).upper() == "ERROR":
            return False, "envelope"
        if data.get("success") is False:
            return False, "envelope"
    return True, None


class Probe:
    """Holds the loaded server module + a dedicated event loop for sync calls."""

    def __init__(self, server_mod: Any):
        self.mod = server_mod
        self._loop = asyncio.new_event_loop()
        self.history: list[ToolResult] = []

    def close(self) -> None:
        try:
            self._loop.close()
        except Exception:
            pass

    def list_tools(self) -> list[Any]:
        return self._loop.run_until_complete(self.mod.list_tools())

    def call(self, name: str, arguments: dict | None = None) -> ToolResult:
        args = dict(arguments or {})
        t0 = time.perf_counter()
        try:
            seq = self._loop.run_until_complete(self.mod.call_tool(name, args))
        except Exception as exc:  # the server is supposed to never raise; record if it does
            dt = time.perf_counter() - t0
            r = ToolResult(
                name=name, ok=False, text=f"RAISED: {type(exc).__name__}: {exc}",
                data=None, images=0, latency_s=dt, resp_tokens=0, cost_usd=0.0,
                error_kind="exception_text", actionability=0.0,
            )
            self.history.append(r)
            return r
        dt = time.perf_counter() - t0

        text_parts: list[str] = []
        images = 0
        for part in seq or []:
            ptype = getattr(part, "type", None)
            if ptype == "text":
                text_parts.append(getattr(part, "text", "") or "")
            elif ptype == "image":
                images += 1
            else:
                text_parts.append(str(part))
        text = "\n".join(text_parts)

        data: Any = None
        try:
            data = json.loads(text) if text.strip() else None
        except (ValueError, TypeError):
            data = None

        ok, error_kind = _classify(text, data)
        tokens = estimate_tokens(text)
        cost = round((tokens / 1000) * _COST_PER_1K_OUTPUT, 6)
        r = ToolResult(
            name=name, ok=ok, text=text, data=data, images=images,
            latency_s=dt, resp_tokens=tokens, cost_usd=cost,
            error_kind=error_kind,
            actionability=(_looks_actionable(text) if not ok else 1.0),
        )
        self.history.append(r)
        return r
