"""D3 (W6a) read-only authorization tiering — pure policy, no TD/mcp deps.

Split out of ``api_controller`` so the decision logic is unit-testable OFFLINE:
``api_controller`` imports the live ``mcp`` package (which collides with the
installed MCP SDK under test), so the policy lives here where a CI test can load
it by file path with zero heavy imports (stdlib only).

Contract:
  * DEFAULT (env flag unset) -> the caller never even consults this (no-op);
    the server is byte-identical to today.
  * READ-ONLY MODE (``TD_BUILDER_LIVE_READONLY`` truthy) -> allow ONLY the
    ``READ_ONLY`` class; ``WRITE_CHECKPOINT`` and ``DESTRUCTIVE`` are denied, and
    any unmatched/unclassified operationId FAILS CLOSED (denied). The flag is read
    PER-REQUEST so a live 403 matrix needs no TD restart between legs.

The canonical operationId->class map is ``MCP/live_tool_risk.json`` (single source
of truth; the client annotations are CI-locked to it).
"""

import json
import os
from pathlib import Path

READONLY_ENV = "TD_BUILDER_LIVE_READONLY"
RISK_FILE_ENV = "TD_LIVE_TOOL_RISK_FILE"  # test/robustness override for the map path
_TRUTHY = {"1", "true", "yes", "on"}


def read_only_enabled() -> bool:
    """True iff read-only mode is opted in (read PER-REQUEST)."""
    return os.environ.get(READONLY_ENV, "").strip().lower() in _TRUTHY


def tier_map_path() -> Path:
    """Locate MCP/live_tool_risk.json. Honors TD_LIVE_TOOL_RISK_FILE, else resolves
    it relative to this module (.../MCP/td-webserver/modules/mcp/controllers/ ->
    .../MCP/live_tool_risk.json)."""
    env = os.environ.get(RISK_FILE_ENV)
    if env and env.strip():
        return Path(env.strip())
    return Path(__file__).resolve().parents[4] / "live_tool_risk.json"


def load_tier_map() -> dict:
    """Load {operationId: class} from live_tool_risk.json. NEVER raises: on any
    failure returns {} (with the flag OFF that changes nothing; with the flag ON an
    empty map means every route fails closed — the correct posture for a
    misconfigured observe-only deployment). Returns the parse error, if any, as a
    second element for the caller to log."""
    try:
        raw = json.loads(tier_map_path().read_text(encoding="utf-8"))
        return {op_id: entry["class"] for op_id, entry in raw.get("operations", {}).items()}
    except Exception:  # noqa: BLE001 — tiering must never block boot
        return {}


def read_only_denial(tier_map: dict, op_id) -> "str | None":
    """Return a denial reason when read-only mode blocks ``op_id``, else None.

    Callers gate on ``read_only_enabled()`` first (default no-op). Here: ONLY the
    ``READ_ONLY`` class is allowed; everything else — ``WRITE_CHECKPOINT``,
    ``DESTRUCTIVE``, an unmatched route (``op_id is None``), or an unclassified
    operationId — fails CLOSED.
    """
    if tier_map.get(op_id) == "READ_ONLY":
        return None
    return (
        f"Forbidden: read-only mode ({READONLY_ENV}) allows only READ_ONLY live "
        f"tools; {op_id or 'unmatched route'} is "
        f"{tier_map.get(op_id) or 'unclassified'} and is blocked."
    )
