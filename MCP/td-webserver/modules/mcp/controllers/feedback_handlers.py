"""
Feedback Handlers for Network Editor MCP
Provides HTTP endpoint handlers for visual feedback tools.

Part of Phase 1 POC for TD Builder visual feedback integration.
Author: FELIX (Feature Engineer)
Date: 2024-12-25
"""

import json
from typing import Any, Dict

from mcp.services.capture_service import capture_service
from mcp.services.error_monitor import error_monitor
from mcp.services.glsl_status import glsl_status_service
from utils.logging import log_message
from utils.types import LogLevel, Result


# Export all handler operation IDs for registration
__all__ = [
    "captureTopOutput",
    "getTopInfo",
    "getCookErrors",
    "getErrorSummary",
    # Phase 2: Network Layout & Python Exceptions
    "captureNetworkLayout",
    "getPythonExceptions",
    # Phase 3: Universal Op Viewer
    "captureOpViewer",
    # W-A2: GLSL compile status
    "getGlslStatus",
]


def captureTopOutput(**kwargs) -> Result:
    """
    Handler for POST /api/feedback/capture/top

    Captures a TOP operator's rendered output as base64 image.

    Request body:
        {
            "operator_path": "/project1/null1",
            "resolution": "original",  // optional: "original", "256", "512", "1024"
            "format": "jpeg",          // optional: "jpeg" (smaller) or "png" (lossless)
            "quality": 0.85            // optional: JPEG quality 0.0-1.0
        }

    Response:
        {
            "success": true,
            "data": {
                "image_base64": "iVBORw0KGgo...",
                "width": 1920,
                "height": 1080,
                "format": "jpeg",  // or "png"
                "operator_path": "/project1/null1"
            }
        }
    """
    log_message(f"captureTopOutput called with kwargs: {kwargs}", LogLevel.DEBUG)

    # Extract parameters - handle both body JSON and query params
    body = kwargs.get("body")
    if body and isinstance(body, str):
        import json as json_module
        try:
            body = json_module.loads(body)
        except:
            body = {}
    elif not isinstance(body, dict):
        body = {}

    # Check body first, then kwargs
    operator_path = body.get("operator_path") or body.get("operatorPath") or kwargs.get("operator_path") or kwargs.get("operatorPath")
    resolution = body.get("resolution") or kwargs.get("resolution", "original")
    format = body.get("format") or kwargs.get("format", "jpeg")
    quality = float(body.get("quality") or kwargs.get("quality", 0.85))

    if not operator_path:
        return Result(
            success=False,
            error="Missing required parameter: operator_path"
        )

    # Call the capture service
    result = capture_service.capture_top_output(operator_path, resolution, format=format, quality=quality)

    return result


def getTopInfo(**kwargs) -> Result:
    """
    Handler for GET /api/feedback/top/info

    Gets metadata about a TOP operator without capturing its output.

    Query parameters:
        - operator_path: Path to the TOP operator

    Response:
        {
            "success": true,
            "data": {
                "operator_path": "/project1/null1",
                "width": 1920,
                "height": 1080,
                "aspect": 1.777,
                "pixel_format": "RGBA8Fixed",
                "gpu_memory": 8294400
            }
        }
    """
    log_message(f"getTopInfo called with kwargs: {kwargs}", LogLevel.DEBUG)

    operator_path = kwargs.get("operator_path") or kwargs.get("operatorPath")

    if not operator_path:
        return Result(
            success=False,
            error="Missing required parameter: operator_path"
        )

    result = capture_service.get_top_info(operator_path)

    return result


def getCookErrors(**kwargs) -> Result:
    """
    Handler for GET /api/feedback/errors/cook

    Gets all current cook errors from the Error DAT.

    Query parameters:
        - source_filter: Optional operator path to filter by
        - severity_filter: Optional severity level ("info", "warning", "error", "fatal")
        - limit: Maximum errors to return (default: 100)

    Response:
        {
            "success": true,
            "data": {
                "errors": [
                    {
                        "source": "/project1/noise1",
                        "message": "Cook error description",
                        "severity": "error",
                        "frame": 1234
                    }
                ],
                "total_count": 1
            }
        }
    """
    log_message(f"getCookErrors called with kwargs: {kwargs}", LogLevel.DEBUG)

    source_filter = kwargs.get("source_filter") or kwargs.get("sourceFilter")
    severity_filter = kwargs.get("severity_filter") or kwargs.get("severityFilter")
    limit = int(kwargs.get("limit", 100))

    result = error_monitor.get_cook_errors(
        source_filter=source_filter,
        severity_filter=severity_filter,
        limit=limit
    )

    return result


def getErrorSummary(**kwargs) -> Result:
    """
    Handler for GET /api/feedback/errors/summary

    Gets a summary of errors grouped by severity level.

    Response:
        {
            "success": true,
            "data": {
                "summary": {
                    "info": {"count": 0, "latest": null},
                    "warning": {"count": 2, "latest": {...}},
                    "error": {"count": 1, "latest": {...}},
                    "fatal": {"count": 0, "latest": null}
                },
                "total_count": 3
            }
        }
    """
    log_message("getErrorSummary called", LogLevel.DEBUG)

    result = error_monitor.get_error_summary()

    return result


# ============================================================================
# Phase 2: Network Layout & Python Exceptions
# ============================================================================


def captureNetworkLayout(**kwargs) -> Result:
    """
    Handler for GET /api/feedback/capture/network

    Gets network graph data (nodes + connections) for a COMP.

    Query parameters:
        - comp_path: Path to the COMP (e.g., "/project1")
        - depth: How deep to search (default: 1)

    Response:
        {
            "success": true,
            "data": {
                "comp_path": "/project1",
                "nodes": [
                    {"name": "noise1", "path": "/project1/noise1", "type": "TOP", "x": 100, "y": 200},
                    ...
                ],
                "connections": [
                    {"from_path": "/project1/noise1", "to_path": "/project1/null1", "to_input": 0},
                    ...
                ],
                "node_count": 5,
                "connection_count": 3
            }
        }
    """
    log_message(f"captureNetworkLayout called with kwargs: {kwargs}", LogLevel.DEBUG)

    comp_path = kwargs.get("comp_path") or kwargs.get("compPath")
    depth = int(kwargs.get("depth", 1))

    if not comp_path:
        return {
            'success': False,
            'error': "Missing required parameter: comp_path"
        }

    result = capture_service.capture_network_layout(comp_path, depth=depth)

    return result


def getPythonExceptions(**kwargs) -> Result:
    """
    Handler for GET /api/feedback/errors/python

    Gets Python-specific exceptions from the Error DAT.

    Query parameters:
        - limit: Maximum exceptions to return (default: 50)

    Response:
        {
            "success": true,
            "data": {
                "exceptions": [
                    {
                        "source": "/project1/script1",
                        "message": "NameError: name 'foo' is not defined",
                        "type": "textDAT",
                        "frame": 1234,
                        "severity": "error"
                    }
                ],
                "total_count": 1
            }
        }
    """
    log_message(f"getPythonExceptions called with kwargs: {kwargs}", LogLevel.DEBUG)

    limit = int(kwargs.get("limit", 50))

    result = error_monitor.get_python_exceptions(limit=limit)

    return result



# ============================================================================
# Phase 3: Universal Op Viewer
# ============================================================================


def captureOpViewer(**kwargs) -> Result:
    """
    Handler for POST /api/feedback/capture/op

    Captures ANY operator's viewer as an image (Universal Op Viewer).
    For DATs, returns text content instead of an image.

    Request body:
        {
            "operator_path": "/project1/noise1",
            "resolution": 512,           // optional: output resolution
            "format": "jpeg",            // optional: "jpeg" or "png"
            "quality": 0.85              // optional: JPEG quality 0.1-1.0
        }

    Response (for image):
        {
            "success": true,
            "data": {
                "type": "image",
                "image_base64": "...",
                "width": 512,
                "height": 512,
                "format": "jpeg",
                "family": "CHOP",
                "operator_path": "/project1/noise1"
            }
        }

    Response (for DAT):
        {
            "success": true,
            "data": {
                "type": "text",
                "content": "...",
                "rows": 10,
                "cols": 2,
                "family": "DAT",
                "operator_path": "/project1/text1"
            }
        }
    """
    log_message(f"captureOpViewer called with kwargs: {kwargs}", LogLevel.DEBUG)

    body = kwargs.get("body")
    if body and isinstance(body, str):
        import json as json_module
        try:
            body = json_module.loads(body)
        except:
            body = {}
    elif not isinstance(body, dict):
        body = {}

    operator_path = body.get("operator_path") or body.get("operatorPath") or kwargs.get("operator_path") or kwargs.get("operatorPath")
    resolution = int(body.get("resolution") or kwargs.get("resolution", 512))
    format = body.get("format") or kwargs.get("format", "jpeg")
    quality = float(body.get("quality") or kwargs.get("quality", 0.85))
    # W-B two-phase routing: phase="prime" (create+wire+prime, return handle),
    # phase="pull" (force-cook the handle to size-stability + destroy). Absent phase
    # = legacy single-shot (backward-compatible for direct HTTP callers).
    phase = body.get("phase") or kwargs.get("phase")

    if phase == "pull":
        handle = body.get("handle") or kwargs.get("handle")
        if not handle:
            return {'success': False, 'error': "Missing required parameter: handle (phase=pull)"}
        # primed_bytes: phase-1's prime-pull size. When present, the pull only
        # accepts a converged size that GREW past it (else returns a retryable
        # op_viewer_warming). Absent (legacy callers / the client's final
        # attempt) = plain size-stability. 0 is meaningful — no `or` chaining.
        primed_bytes = body.get("primed_bytes", kwargs.get("primed_bytes"))
        return capture_service.pull_op_viewer(
            handle, operator_path=operator_path or "", format=format, quality=quality,
            primed_bytes=primed_bytes,
        )

    if not operator_path:
        return {
            'success': False,
            'error': "Missing required parameter: operator_path"
        }

    result = capture_service.capture_op_viewer(
        operator_path, resolution=resolution, format=format, quality=quality,
        prime_only=(phase == "prime"),
    )

    return result


# ============================================================================
# W-A2: GLSL compile status
# ============================================================================


def getGlslStatus(**kwargs) -> Result:
    """
    Handler for GET /api/feedback/glsl/status

    Report the compile status of a GLSL-family op (TOP/multiTOP/POP/MAT). This is
    the foolproof answer to "did my shader edit compile?" — it reads the shader's
    Info DAT (the source of truth ``op.errors()`` misses on a hard compile failure)
    and folds in ``op.warnings()``.

    Query parameters:
        - node_path: Path to the operator to check

    Response:
        {
            "success": true,
            "data": {
                "node_path": "/project1/glsl1",
                "op_type": "glslTOP",
                "is_glsl": true,
                "ok": false,
                "compile_failed": true,
                "errors": [...],
                "warnings": ["The GLSL Shader has compile errors (...)"],
                "compiler_log": "...ERROR: 0:12: ...",
                "compiler_errors": ["ERROR: 0:12: ..."]
            }
        }
    """
    log_message(f"getGlslStatus called with kwargs: {kwargs}", LogLevel.DEBUG)

    node_path = kwargs.get("node_path") or kwargs.get("nodePath")
    # file_path: check every GLSL op whose shader source is a DAT synced to this
    # disk file (the edit-the-.glsl-file workflow; TD reloads the DAT itself).
    file_path = kwargs.get("file_path") or kwargs.get("filePath")

    if not node_path and not file_path:
        return {
            'success': False,
            'error': "Missing required parameter: node_path (or file_path)"
        }

    return glsl_status_service.get_glsl_status(node_path or "", file_path or "")


# Route mapping for the OpenAPI router
# Maps path patterns to handler functions
FEEDBACK_ROUTES = {
    # Phase 1: TOP Capture & Error Monitoring
    ("POST", "/api/feedback/capture/top"): captureTopOutput,
    ("GET", "/api/feedback/top/info"): getTopInfo,
    ("GET", "/api/feedback/errors/cook"): getCookErrors,
    ("GET", "/api/feedback/errors/summary"): getErrorSummary,
    # Phase 2: Network Layout & Python Exceptions
    ("GET", "/api/feedback/capture/network"): captureNetworkLayout,
    ("GET", "/api/feedback/errors/python"): getPythonExceptions,
    # Phase 3: Universal Op Viewer
    ("POST", "/api/feedback/capture/op"): captureOpViewer,
    # W-A2: GLSL compile status
    ("GET", "/api/feedback/glsl/status"): getGlslStatus,
}


def get_feedback_routes():
    """Return the route mapping for feedback endpoints."""
    return FEEDBACK_ROUTES
