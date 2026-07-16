"""Session Handlers for the live TouchDesigner MCP surface (D3 / W6a).

HTTP endpoint handlers for the two session-management tools added by D3:

  * ``saveProject``      POST /api/td/server/save            — a client-callable,
    dialog-proof checkpoint of the last-saved .toe (wraps the shared
    ``TouchDesignerApiService._snapshot_toe`` primitive; never ``project.save()``).
  * ``getMutationStatus`` GET  /api/td/server/mutation_status — the post-timeout
    reconciliation surface (last committed mutation seq + snapshot/restore-point
    staleness), so a client that timed out can learn what actually committed.

Registered dynamically via ``register_route`` (the same pattern as
``feedback_handlers``) — the static handler module (``generated_handlers.py``,
hand-maintained) and the ``openapi.yaml`` routing source are deliberately NOT
touched. The operationIds are the handler ``__name__``s below;
``MCP/live_tool_risk.json`` classifies them.
"""

from mcp.services.api_service import api_service
from utils.logging import log_message
from utils.types import LogLevel, Result


# Export handler operation IDs for registration parity with feedback_handlers.
__all__ = [
    "saveProject",
    "getMutationStatus",
]


def saveProject(**kwargs) -> Result:
    """Handler for POST /api/td/server/save.

    Argless — the target is server-chosen (a caller-supplied path would invite
    overwrite/validation surface). Delegates to the service, which fail-fast
    JSON-errors on any I/O failure and never raises a TD modal.
    """
    log_message("saveProject (save_td_project) called", LogLevel.DEBUG)
    return api_service.save_project()


def getMutationStatus(**kwargs) -> Result:
    """Handler for GET /api/td/server/mutation_status.

    Pure state read — returns the mutation-seq receipt, last mutation, dirty flag,
    and the explicit/implicit snapshot metadata for post-timeout reconciliation.
    """
    log_message("getMutationStatus (get_mutation_status) called", LogLevel.DEBUG)
    return api_service.get_mutation_status()


# Route mapping for the OpenAPI router (dynamic registration; see api_controller).
SESSION_ROUTES = {
    ("POST", "/api/td/server/save"): saveProject,
    ("GET", "/api/td/server/mutation_status"): getMutationStatus,
}


def get_session_routes():
    """Return the route mapping for the D3 session endpoints."""
    return SESSION_ROUTES
