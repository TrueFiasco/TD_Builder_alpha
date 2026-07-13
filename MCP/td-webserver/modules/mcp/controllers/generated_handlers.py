"""
Generated Handlers for TouchDesigner MCP CRUD Operations

These handlers implement the operationIds from the OpenAPI schema,
connecting HTTP requests to the api_service methods.

Author: FELIX (Feature Engineer)
Date: 2024-12-28
"""

import json
from typing import Any

from mcp.services.api_service import api_service
from utils.logging import log_message
from utils.types import LogLevel, Result


# Export all handler operation IDs for registration
__all__ = [
    "get_td_info",
    "get_nodes",
    "get_node_detail",
    "get_node_errors",
    "create_node",
    "update_node",
    "delete_node",
    "exec_node_method",
    "exec_python_script",
    "get_td_python_classes",
    "get_td_python_class_details",
    "get_module_help",
]


def _parse_body(body: Any) -> dict:
    """Parse request body from string or dict."""
    if body is None:
        return {}
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    if isinstance(body, dict):
        return body
    return {}


def get_td_info(**kwargs) -> Result:
    """
    Handler for GET /api/td/server/td

    Returns TouchDesigner server information.
    """
    log_message("get_td_info called", LogLevel.DEBUG)
    return api_service.get_td_info()


def get_nodes(**kwargs) -> Result:
    """
    Handler for GET /api/nodes

    Query parameters:
        - parentPath: Required. Parent path to list nodes from.
        - pattern: Optional. Pattern to filter nodes.
        - includeProperties: Optional. Whether to include full properties.
        - limit: Optional. Max children to return (response is truncated+flagged if exceeded).
    """
    log_message(f"get_nodes called with kwargs: {kwargs}", LogLevel.DEBUG)

    parent_path = kwargs.get("parentPath") or kwargs.get("parent_path")
    if not parent_path:
        return {
            "success": False,
            "error": "Missing required parameter: parentPath"
        }

    pattern = kwargs.get("pattern")
    include_properties = kwargs.get("includeProperties", False)

    # Handle string "true"/"false" from query params
    if isinstance(include_properties, str):
        include_properties = include_properties.lower() == "true"

    # Query params arrive as strings; coerce a numeric limit to int (same pattern
    # as includeProperties above). Non-numeric/blank/non-positive limit is treated
    # as absent — a negative value would otherwise become a negative slice that
    # silently drops children from the END of the list.
    limit_raw = kwargs.get("limit")
    limit = None
    if isinstance(limit_raw, str):
        if limit_raw.strip().isdigit():
            limit = int(limit_raw)
    elif isinstance(limit_raw, int) and not isinstance(limit_raw, bool):
        limit = limit_raw
    if limit is not None and limit < 1:
        limit = None

    return api_service.get_nodes(
        parent_path=parent_path,
        pattern=pattern,
        include_properties=include_properties,
        limit=limit,
    )


def get_node_detail(**kwargs) -> Result:
    """
    Handler for GET /api/nodes/detail

    Query parameters:
        - nodePath: Required. Path to the node.
    """
    log_message(f"get_node_detail called with kwargs: {kwargs}", LogLevel.DEBUG)

    node_path = kwargs.get("nodePath") or kwargs.get("node_path")
    if not node_path:
        return {
            "success": False,
            "error": "Missing required parameter: nodePath"
        }

    return api_service.get_node_detail(node_path)


def get_node_errors(**kwargs) -> Result:
    """
    Handler for GET /api/nodes/errors

    Query parameters:
        - nodePath: Required. Path to the node.
        - recurse:  Optional bool (default True). When false, only the node's
                    own errors are returned; descendants are not walked.

    B17 — `recurse` was previously not threaded through; the service-layer call
    hardcoded recurse=True regardless of caller input.
    """
    log_message(f"get_node_errors called with kwargs: {kwargs}", LogLevel.DEBUG)

    node_path = kwargs.get("nodePath") or kwargs.get("node_path")
    if not node_path:
        return {
            "success": False,
            "error": "Missing required parameter: nodePath"
        }

    recurse = kwargs.get("recurse", True)
    if isinstance(recurse, str):
        recurse = recurse.strip().lower() in ("true", "1", "yes", "on")

    return api_service.get_node_errors(node_path, recurse=bool(recurse))


def create_node(**kwargs) -> Result:
    """
    Handler for POST /api/nodes

    Request body:
        - parentPath: Required. Path to parent node.
        - nodeType: Required. Type of node to create (e.g., "noiseTOP").
        - nodeName: Optional. Name for the new node.
    """
    log_message(f"create_node called with kwargs: {kwargs}", LogLevel.DEBUG)

    body = _parse_body(kwargs.get("body"))

    parent_path = body.get("parentPath") or kwargs.get("parentPath")
    node_type = body.get("nodeType") or kwargs.get("nodeType")
    node_name = body.get("nodeName") or kwargs.get("nodeName")
    parameters = body.get("parameters")

    if not parent_path:
        return {
            "success": False,
            "error": "Missing required parameter: parentPath"
        }

    if not node_type:
        return {
            "success": False,
            "error": "Missing required parameter: nodeType"
        }

    return api_service.create_node(
        parent_path=parent_path,
        node_type=node_type,
        node_name=node_name,
        parameters=parameters
    )


def update_node(**kwargs) -> Result:
    """
    Handler for PATCH /api/nodes/detail

    Request body:
        - nodePath: Required. Path to the node.
        - properties: Required. Dict of property name-value pairs.
    """
    log_message(f"update_node called with kwargs: {kwargs}", LogLevel.DEBUG)

    body = _parse_body(kwargs.get("body"))

    node_path = body.get("nodePath") or kwargs.get("nodePath")
    properties = body.get("properties") or kwargs.get("properties")

    if not node_path:
        return {
            "success": False,
            "error": "Missing required parameter: nodePath"
        }

    if not properties or not isinstance(properties, dict):
        return {
            "success": False,
            "error": "Missing required parameter: properties (must be object)"
        }

    return api_service.update_node(node_path, properties)


def delete_node(**kwargs) -> Result:
    """
    Handler for DELETE /api/nodes

    Query parameters:
        - nodePath: Required. Path to the node to delete.
    """
    log_message(f"delete_node called with kwargs: {kwargs}", LogLevel.DEBUG)

    node_path = kwargs.get("nodePath") or kwargs.get("node_path")
    if not node_path:
        return {
            "success": False,
            "error": "Missing required parameter: nodePath"
        }

    return api_service.delete_node(node_path)


def exec_node_method(**kwargs) -> Result:
    """
    Handler for POST /api/td/nodes/exec

    Request body:
        - nodePath: Required. Path to the node.
        - method: Required. Method name to call.
        - args: Optional. List of positional arguments.
        - kwargs: Optional. Dict of keyword arguments.
    """
    log_message(f"exec_node_method called with kwargs: {kwargs}", LogLevel.DEBUG)

    body = _parse_body(kwargs.get("body"))

    node_path = body.get("nodePath") or kwargs.get("nodePath")
    method = body.get("method") or kwargs.get("method")
    args = body.get("args", [])
    method_kwargs = body.get("kwargs", {})

    if not node_path:
        return {
            "success": False,
            "error": "Missing required parameter: nodePath"
        }

    if not method:
        return {
            "success": False,
            "error": "Missing required parameter: method"
        }

    return api_service.exec_node_method(node_path, method, args, method_kwargs)


def exec_python_script(**kwargs) -> Result:
    """
    Handler for POST /api/td/server/exec

    Request body:
        - script: Required. Python script to execute.
    """
    log_message(f"exec_python_script called with kwargs: {kwargs}", LogLevel.DEBUG)

    body = _parse_body(kwargs.get("body"))

    script = body.get("script") or kwargs.get("script")

    if not script:
        return {
            "success": False,
            "error": "Missing required parameter: script"
        }

    return api_service.exec_python_script(script)


def get_td_python_classes(**kwargs) -> Result:
    """
    Handler for GET /api/td/classes

    Returns list of Python classes available in TouchDesigner.

    Query parameters:
        - mode (optional): "full" (default, current behavior), "summary"
                           (categories + counts), or "names" (sorted name list).
                           B25 — added to cut down context cost (~50k → ~150
                           or ~1-2k tokens) when the caller only needs a count
                           or a quick name list.
    """
    log_message(f"get_td_python_classes called with kwargs: {kwargs}", LogLevel.DEBUG)
    mode = (kwargs.get("mode") or "full").strip().lower()
    if mode not in ("full", "summary", "names"):
        return {
            "success": False,
            "error": f"Invalid mode {mode!r}; must be one of 'full', 'summary', 'names'",
        }
    return api_service.get_td_python_classes(mode=mode)


def get_td_python_class_details(**kwargs) -> Result:
    """
    Handler for GET /api/td/classes/{className}

    Path parameters:
        - className: Required. Name of the class.
    """
    log_message(f"get_td_python_class_details called with kwargs: {kwargs}", LogLevel.DEBUG)

    class_name = kwargs.get("className") or kwargs.get("class_name")
    if not class_name:
        return {
            "success": False,
            "error": "Missing required parameter: className"
        }

    return api_service.get_td_python_class_details(class_name)


def get_module_help(**kwargs) -> Result:
    """
    Handler for GET /api/td/modules/help

    Query parameters:
        - moduleName: Required. Module or class name.
        - mode (optional): 'summary' (default) or 'full'. W6.2 — summary
          default added because pydoc.render_doc(td) is ~35 MB. Use
          mode='full' with a narrow target (e.g. 'td.OP') for full pydoc.
    """
    log_message(f"get_module_help called with kwargs: {kwargs}", LogLevel.DEBUG)

    module_name = kwargs.get("moduleName") or kwargs.get("module_name")
    if not module_name:
        return {
            "success": False,
            "error": "Missing required parameter: moduleName"
        }

    mode = (kwargs.get("mode") or "summary").strip().lower()
    if mode not in ("summary", "full"):
        return {
            "success": False,
            "error": f"Invalid mode {mode!r}; must be 'summary' or 'full'",
        }
    return api_service.get_module_help(module_name, mode=mode)
