"""
TouchDesigner Live Client - HTTP Client for TD WebServer DAT

Provides async HTTP client and MCP tool implementations for visual feedback
and TD CRUD operations. Communicates with TouchDesigner via WebServer DAT.

Author: FELIX (Feature Engineer) - Consolidated from TypeScript MCP
Date: 2024-12-27
"""

import os
import json
import httpx
from pathlib import Path
from typing import Sequence, Dict, Any, List, Optional, Union
from mcp.types import Tool, TextContent, ImageContent, ToolAnnotations

# Configuration
TD_API_URL = os.environ.get("TD_API_URL", "http://127.0.0.1:9981")

# Shared-secret auth. These env names + the token-file location MUST match the TD
# side (MCP/td-webserver/modules/utils/auth.py); kept as constants so a rename is
# a one-line change on both sides.
TD_API_TOKEN_ENV = "TD_API_TOKEN"
TD_API_TOKEN_FILE_ENV = "TD_API_TOKEN_FILE"


def _default_token_path() -> Path:
    override = os.environ.get(TD_API_TOKEN_FILE_ENV)
    if override and override.strip():
        return Path(override.strip())
    return Path.home() / ".td_builder" / "api_token"


def _resolve_token() -> Optional[str]:
    """Resolve the shared secret: TD_API_TOKEN env → token file (per request, so a
    token generated after this client started is still picked up).

    NEVER raises: any file-read error returns None. An exception in
    TDClient.__aenter__ would surface as a non-graceful "Error: ..." string that
    does not match the TD-down acceptance check, breaking the graceful path.
    """
    env = os.environ.get(TD_API_TOKEN_ENV)
    if env and env.strip():
        return env.strip()
    try:
        path = _default_token_path()
        if path.exists():
            tok = path.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    except OSError:
        pass
    return None


class TDClient:
    """Async HTTP client for TouchDesigner WebServer DAT"""

    def __init__(self, base_url: str = None, read_timeout: float = 20.0):
        self.base_url = base_url or TD_API_URL
        self._read_timeout = read_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        headers = {}
        token = _resolve_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self._read_timeout, connect=5.0),
            headers=headers or None,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def get(self, endpoint: str, params: dict = None) -> httpx.Response:
        return await self._client.get(endpoint, params=params)

    async def post(self, endpoint: str, json: dict = None) -> httpx.Response:
        return await self._client.post(endpoint, json=json)

    async def patch(self, endpoint: str, json: dict = None) -> httpx.Response:
        return await self._client.patch(endpoint, json=json)

    async def delete(self, endpoint: str, params: dict = None) -> httpx.Response:
        return await self._client.delete(endpoint, params=params)


def _connection_error_message() -> str:
    return (
        "TouchDesigner not running or WebServer DAT not active.\n\n"
        f"Expected: TD WebServer on {TD_API_URL}\n\n"
        "To enable visual feedback:\n"
        "1. Open TouchDesigner\n"
        "2. Import mcp_webserver_base.tox into your project\n"
        "3. The WebServer DAT will listen on port 9981"
    )


def _restore_point_note(data: dict) -> str:
    """OBS-1 (D3): a one-line warning appended to a mutator's rendered result when
    the pre-mutation restore point was NOT taken (skipped = untitled project;
    unavailable = copy failed). The mutation already happened, so this is the
    condition under which the user should act. Mirrors the get_td_info rendering.
    Returns "" when the restore point is fine (ok / not_run) or absent.
    """
    rp = data.get("restorePoint")
    if not isinstance(rp, dict):
        return ""
    status = rp.get("status")
    if status not in ("skipped", "unavailable"):
        return ""
    if status == "skipped":
        return (
            "\n\n⚠️ Restore point unavailable — save the project once (Ctrl+S) to "
            "enable restore points. This edit proceeded without a rollback point."
        )
    detail = rp.get("detail")
    return (
        f"\n\n⚠️ Restore point **unavailable**"
        f"{f' ({detail})' if detail else ''} — this edit proceeded without a "
        "rollback point."
    )


# =============================================================================
# VISUAL FEEDBACK TOOLS (7 tools)
# =============================================================================

async def capture_top_output(arguments: dict) -> Sequence[Union[TextContent, ImageContent]]:
    """Capture a TOP operator's rendered output as an image."""
    try:
        async with TDClient(read_timeout=60.0) as client:
            response = await client.post("/api/feedback/capture/top", json={
                "operator_path": arguments["operator_path"],
                "resolution": arguments.get("resolution", "original"),
                "format": arguments.get("format", "jpeg"),
                "quality": arguments.get("quality", 0.85)
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error ({response.status_code}): {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                img_data = data["data"]
                return [
                    ImageContent(
                        type="image",
                        data=img_data["image_base64"],
                        mimeType=f"image/{img_data['format']}"
                    ),
                    TextContent(
                        type="text",
                        text=f"Captured {img_data['width']}x{img_data['height']} {img_data['format'].upper()} from {img_data['operator_path']}"
                    )
                ]
            return [TextContent(type="text", text=f"Capture failed: {data.get('error', 'Unknown error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error capturing TOP: {str(e)}")]


async def get_top_info(arguments: dict) -> Sequence[TextContent]:
    """Get metadata about a TOP operator without capturing."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/feedback/top/info", params={
                "operator_path": arguments["operator_path"]
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                info = data["data"]
                text = f"""## TOP Info: {info['operator_path']}

| Property | Value |
|----------|-------|
| Resolution | {info['width']}x{info['height']} |
| Aspect Ratio | {info['aspect']:.3f} |
| Pixel Format | {info['pixel_format']} |
| GPU Memory | {info['gpu_memory'] / 1024:.1f} KB |
"""
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed to get TOP info: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting TOP info: {str(e)}")]


async def get_cook_errors(arguments: dict) -> Sequence[TextContent]:
    """Get all current cook errors from TouchDesigner."""
    try:
        async with TDClient() as client:
            params = {}
            if arguments.get("source_filter"):
                params["source_filter"] = arguments["source_filter"]
            if arguments.get("severity_filter"):
                params["severity_filter"] = arguments["severity_filter"]
            if arguments.get("limit"):
                params["limit"] = arguments["limit"]

            response = await client.get("/api/feedback/errors/cook", params=params)

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                errors = data["data"]["errors"]
                total = data["data"]["total_count"]

                if not errors:
                    return [TextContent(type="text", text="No cook errors found.")]

                lines = [f"## Cook Errors ({total} total)\n"]
                for err in errors:
                    severity_icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "fatal": "💀"}.get(err["severity"], "•")
                    lines.append(f"{severity_icon} **{err['source']}** (frame {err['frame']})")
                    lines.append(f"   {err['message']}\n")

                return [TextContent(type="text", text="\n".join(lines))]
            return [TextContent(type="text", text=f"Failed to get errors: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting cook errors: {str(e)}")]


async def get_error_summary(arguments: dict) -> Sequence[TextContent]:
    """Get error summary grouped by severity level."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/feedback/errors/summary")

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                summary = data["data"]["summary"]
                total = data["data"]["total_count"]

                lines = [f"## Error Summary ({total} total)\n"]
                for severity in ["fatal", "error", "warning", "info"]:
                    if severity in summary:
                        count = summary[severity]["count"]
                        icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "fatal": "💀"}[severity]
                        lines.append(f"{icon} **{severity.upper()}**: {count}")

                return [TextContent(type="text", text="\n".join(lines))]
            return [TextContent(type="text", text=f"Failed to get summary: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting summary: {str(e)}")]


async def capture_network_layout(arguments: dict) -> Sequence[TextContent]:
    """Get network layout showing operators and connections within a COMP."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/feedback/capture/network", params={
                "comp_path": arguments["comp_path"],
                "depth": arguments.get("depth", 1)
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                layout = data["data"]
                nodes = layout["nodes"]
                connections = layout["connections"]

                lines = [f"## Network Layout: {layout['comp_path']}"]
                lines.append(f"**Operators**: {layout['node_count']} | **Connections**: {layout['connection_count']}\n")

                lines.append("### Operators")
                for node in nodes:
                    lines.append(f"- `{node['name']}` ({node['family']}/{node['type']}) at ({node['x']}, {node['y']})")

                if connections:
                    lines.append("\n### Connections")
                    for conn in connections:
                        lines.append(f"- {conn['from_path']} → {conn['to_path']} (input {conn['to_input']})")

                return [TextContent(type="text", text="\n".join(lines))]
            return [TextContent(type="text", text=f"Failed to get layout: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting network layout: {str(e)}")]


async def get_python_exceptions(arguments: dict) -> Sequence[TextContent]:
    """Get Python-specific exceptions from TouchDesigner."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/feedback/errors/python", params={
                "limit": arguments.get("limit", 50)
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                exceptions = data["data"]["exceptions"]
                total = data["data"]["total_count"]

                if not exceptions:
                    return [TextContent(type="text", text="No Python exceptions found.")]

                lines = [f"## Python Exceptions ({total} total)\n"]
                for exc in exceptions:
                    lines.append(f"### {exc['type']} in `{exc['source']}`")
                    lines.append(f"Frame: {exc['frame']} | Severity: {exc['severity']}")
                    lines.append(f"```\n{exc['message']}\n```\n")

                return [TextContent(type="text", text="\n".join(lines))]
            return [TextContent(type="text", text=f"Failed to get exceptions: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting Python exceptions: {str(e)}")]


async def capture_op_viewer(arguments: dict) -> Sequence[Union[TextContent, ImageContent]]:
    """Universal operator viewer - captures any operator type."""
    try:
        async with TDClient() as client:
            response = await client.post("/api/feedback/capture/op", json={
                "operator_path": arguments["operator_path"],
                "resolution": arguments.get("resolution", 512),
                "format": arguments.get("format", "jpeg"),
                "quality": arguments.get("quality", 0.85)
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                result = data["data"]
                result_type = result.get("type")

                if result_type == "image":
                    return [
                        ImageContent(
                            type="image",
                            data=result["image_base64"],
                            mimeType=f"image/{result['format']}"
                        ),
                        TextContent(
                            type="text",
                            text=f"Captured {result['family']} {result['operator_path']}: {result['width']}x{result['height']}"
                        )
                    ]
                elif result_type == "text":
                    return [TextContent(
                        type="text",
                        text=f"## DAT Content: {result['operator_path']}\n\n"
                             f"Rows: {result['rows']} | Cols: {result['cols']}\n\n"
                             f"```\n{result['content']}\n```"
                    )]
                elif result_type == "geometry_info":
                    return [TextContent(
                        type="text",
                        text=f"## SOP Info: {result['operator_path']}\n\n"
                             f"Points: {result['num_points']} | Prims: {result['num_prims']} | Vertices: {result['num_vertices']}\n\n"
                             f"Note: {result.get('note', 'Use capture_top_output on a Render TOP for visual')}"
                    )]
                else:
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]

            return [TextContent(type="text", text=f"Capture failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error capturing operator: {str(e)}")]


# =============================================================================
# CORE TD CRUD TOOLS (12 tools)
# =============================================================================

async def get_td_info(arguments: dict) -> Sequence[TextContent]:
    """Get TouchDesigner server information."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/td/server/td")

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                info = data["data"]
                text = f"""## TouchDesigner Info

| Property | Value |
|----------|-------|
| Server | {info.get('server', 'N/A')} |
| Version | {info.get('version', 'N/A')} |
| OS | {info.get('osName', 'N/A')} {info.get('osVersion', '')} |
| MCP API | {info.get('mcpApiVersion', 'N/A')} |
"""
                # Session restore point (pre-mutation safety copy). Surface it so the
                # AI can tell the user where rollback lives AND — critically — notice
                # when the best-effort copy did NOT happen (skipped/unavailable), i.e.
                # mutations proceeded without a rollback point.
                rp = info.get("restorePoint")
                if isinstance(rp, dict):
                    status = rp.get("status", "unknown")
                    detail = rp.get("detail")
                    text += f"| Restore point | {status if not detail else f'{status} ({detail})'} |\n"
                    if status not in ("ok", "not_run"):
                        text += (
                            f"\n⚠️ Session restore point **{status}** — the pre-mutation "
                            "safety copy was not created; edits proceed without a rollback "
                            "point (save the project once to enable it).\n"
                        )
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_td_nodes(arguments: dict) -> Sequence[TextContent]:
    """List nodes under a parent path."""
    try:
        async with TDClient() as client:
            params = {"parentPath": arguments["parent_path"]}
            if arguments.get("pattern"):
                params["pattern"] = arguments["pattern"]
            if arguments.get("include_properties"):
                params["includeProperties"] = arguments["include_properties"]
            if arguments.get("limit"):
                params["limit"] = arguments["limit"]

            response = await client.get("/api/nodes", params=params)

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                nodes = data["data"].get("nodes", [])
                lines = [f"## Nodes under {arguments['parent_path']}\n"]
                for node in nodes:
                    lines.append(f"- `{node['name']}` ({node.get('opType', 'unknown')}) - {node['path']}")
                return [TextContent(type="text", text="\n".join(lines))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_td_node_parameters(arguments: dict) -> Sequence[TextContent]:
    """Get detailed parameters of a node."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/nodes/detail", params={
                "nodePath": arguments["node_path"]
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                return [TextContent(type="text", text=json.dumps(data["data"], indent=2))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def create_td_node(arguments: dict) -> Sequence[TextContent]:
    """Create a new operator under a parent path."""
    try:
        async with TDClient(read_timeout=60.0) as client:
            response = await client.post("/api/nodes", json={
                "parentPath": arguments["parent_path"],
                "nodeType": arguments["node_type"],
                "nodeName": arguments.get("node_name")
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                node = data["data"]
                text = f"Created node: {node.get('path', 'unknown')}"
                text += _restore_point_note(node)
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def update_td_node_parameters(arguments: dict) -> Sequence[TextContent]:
    """Update parameters of an existing node."""
    try:
        async with TDClient() as client:
            response = await client.patch("/api/nodes/detail", json={
                "nodePath": arguments["node_path"],
                "properties": arguments["properties"]
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                result = data["data"]
                updated = result.get("updated", [])
                failed = result.get("failed", [])
                text = f"Updated {len(updated)} parameters"
                if failed:
                    text += f"\nFailed: {failed}"
                text += _restore_point_note(result)
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def delete_td_node(arguments: dict) -> Sequence[TextContent]:
    """Delete an operator."""
    try:
        async with TDClient() as client:
            response = await client.delete("/api/nodes", params={
                "nodePath": arguments["node_path"]
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success"):
                text = f"Deleted: {arguments['node_path']}"
                text += _restore_point_note(data.get("data") or {})
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def execute_python_script(arguments: dict) -> Sequence[TextContent]:
    """Execute arbitrary Python script in TouchDesigner."""
    try:
        async with TDClient(read_timeout=120.0) as client:
            response = await client.post("/api/td/server/exec", json={
                "script": arguments["script"]
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                result = data["data"]
                text = f"## Script Execution Result\n\n"
                if result.get("result") is not None:
                    text += f"**Result**: {result['result']}\n"
                if result.get("stdout"):
                    text += f"\n**Stdout**:\n```\n{result['stdout']}\n```\n"
                if result.get("stderr"):
                    text += f"\n**Stderr**:\n```\n{result['stderr']}\n```\n"
                text += _restore_point_note(result)
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def exec_node_method(arguments: dict) -> Sequence[TextContent]:
    """Call a method on a node."""
    try:
        async with TDClient() as client:
            response = await client.post("/api/td/nodes/exec", json={
                "nodePath": arguments["node_path"],
                "method": arguments["method"],
                "args": arguments.get("args", []),
                "kwargs": arguments.get("kwargs", {})
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                text = json.dumps(data["data"], indent=2)
                text += _restore_point_note(data["data"])
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_td_node_errors(arguments: dict) -> Sequence[TextContent]:
    """Check node and descendant errors."""
    try:
        async with TDClient() as client:
            params = {"nodePath": arguments["node_path"]}
            if arguments.get("recurse") is not None:
                params["recurse"] = arguments["recurse"]

            response = await client.get("/api/nodes/errors", params=params)

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                return [TextContent(type="text", text=json.dumps(data["data"], indent=2))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_td_classes(arguments: dict) -> Sequence[TextContent]:
    """List TouchDesigner Python classes.

    B25 — `mode` arg controls response size:
      "full"    (default, ~50k tokens): every class with full docstring.
      "summary" (~150 tokens):           category counts only.
      "names"   (~1-2k tokens):          sorted name list, no descriptions.
    """
    try:
        mode = (arguments.get("mode") or "full").strip().lower()
        params = {"mode": mode} if mode in ("summary", "names") else {}
        async with TDClient() as client:
            response = await client.get("/api/td/classes", params=params)

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                return [TextContent(type="text", text=json.dumps(data["data"], indent=2))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_td_class_details(arguments: dict) -> Sequence[TextContent]:
    """Get details of a specific TouchDesigner class."""
    try:
        async with TDClient() as client:
            response = await client.get(f"/api/td/classes/{arguments['class_name']}")

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                return [TextContent(type="text", text=json.dumps(data["data"], indent=2))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_td_module_help(arguments: dict) -> Sequence[TextContent]:
    """Get Python help() for module/class.

    W6.2 (B35) — `mode` defaults to 'summary' (~1-3 KB, attribute list +
    first docstring line). Pass `mode='full'` for the complete pydoc text.
    No cap on full mode; narrow your target (e.g. 'td.OP' not 'td') to
    keep response size sane.
    """
    try:
        mode = (arguments.get("mode") or "summary").strip().lower()
        async with TDClient() as client:
            response = await client.get("/api/td/modules/help", params={
                "moduleName": arguments["target"],
                "mode": mode,
            })

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                return [TextContent(type="text", text=data["data"].get("helpText", "No help available"))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def save_td_project(arguments: dict) -> Sequence[TextContent]:
    """Take a dialog-proof checkpoint of the last-saved .toe (D3)."""
    try:
        # The copy blocks TD's single main thread; a realistically large project can
        # take a moment. Generous read timeout so a big-project copy doesn't look
        # like a hang.
        async with TDClient(read_timeout=60.0) as client:
            response = await client.post("/api/td/server/save", json={})

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                d = data["data"]
                text = "## Checkpoint saved\n\n"
                text += f"- **Snapshot**: `{d.get('path')}`\n"
                text += f"- **Source**: `{d.get('source_path')}`\n"
                text += f"- **Captures last-saved state as of**: {d.get('source_mtime')}\n"
                text += f"- **mutation_seq** (receipt): {d.get('mutation_seq')}\n"
                if d.get("warning"):
                    text += f"\n⚠️ {d['warning']}\n"
                return [TextContent(type="text", text=text)]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def get_mutation_status(arguments: dict) -> Sequence[TextContent]:
    """Report what committed since server start — the post-timeout recovery surface (D3)."""
    try:
        async with TDClient() as client:
            response = await client.get("/api/td/server/mutation_status")

            if response.status_code != 200:
                return [TextContent(type="text", text=f"TD Error: {response.text}")]

            data = response.json()
            if data.get("success") and data.get("data"):
                return [TextContent(type="text", text=json.dumps(data["data"], indent=2))]
            return [TextContent(type="text", text=f"Failed: {data.get('error')}")]

    except httpx.ConnectError:
        return [TextContent(type="text", text=_connection_error_message())]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# =============================================================================
# TOOL DEFINITIONS (for mcp_server.py list_tools)
# =============================================================================

# MCP risk annotations (W4b, audit cluster C3). Owner-decided: ship only the three
# named hints (openWorldHint omitted). destructiveHint/idempotentHint are meaningful
# only when readOnlyHint is false.
#   READ_ONLY       — reads/captures live state; no graph mutation (captures force a
#                     cook, which is not a persistent mutation).
#   WRITE_CHECKPOINT — writes a file to disk (an honest readOnlyHint=False), does NOT
#                     mutate the live graph, and overwrites a stable target
#                     (checkpoint-idempotent). D3's save_td_project only. Distinct
#                     from DESTRUCTIVE (no graph mutation) and from the offline
#                     WRITE_ADDITIVE (which pins idempotentHint=False).
#   DESTRUCTIVE     — mutates/destroys live graph state or runs arbitrary code
#                     (create/update/delete node, execute_python_script, exec_node_method).
# Shared singletons — never mutated. See docs/TOOL_RISK_ANNOTATIONS.md.
READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITE_CHECKPOINT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True
)
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False
)

TD_LIVE_TOOLS: List[Tool] = [
    # Visual Feedback Tools (7)
    Tool(
        annotations=READ_ONLY,
        name="capture_top_output",
        description="Capture a TOP operator's rendered output as an image. Returns base64-encoded JPEG/PNG. Requires TouchDesigner running with WebServer DAT.",
        inputSchema={
            "type": "object",
            "properties": {
                "operator_path": {
                    "type": "string",
                    "description": "Path to TOP operator (e.g., /project1/moviefilein1)"
                },
                "resolution": {
                    "type": "string",
                    "enum": ["original", "256", "512", "1024"],
                    "default": "original",
                    "description": "Output resolution"
                },
                "format": {
                    "type": "string",
                    "enum": ["jpeg", "png"],
                    "default": "jpeg",
                    "description": "Image format"
                },
                "quality": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 1.0,
                    "default": 0.85,
                    "description": "JPEG quality (ignored for PNG)"
                }
            },
            "required": ["operator_path"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_top_info",
        description="Get metadata about a TOP operator (resolution, aspect, pixel format, GPU memory) without capturing.",
        inputSchema={
            "type": "object",
            "properties": {
                "operator_path": {
                    "type": "string",
                    "description": "Path to TOP operator"
                }
            },
            "required": ["operator_path"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_cook_errors",
        description="Get all current cook errors from TouchDesigner. Errors indicate operators that failed to cook.",
        inputSchema={
            "type": "object",
            "properties": {
                "source_filter": {
                    "type": "string",
                    "description": "Filter errors by source operator path"
                },
                "severity_filter": {
                    "type": "string",
                    "enum": ["info", "warning", "error", "fatal"],
                    "description": "Filter by severity level"
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum number of errors to return"
                }
            },
            "required": []
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_error_summary",
        description="Get a summary of all errors grouped by severity level (info, warning, error, fatal).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="capture_network_layout",
        description="Get network layout data showing operators and connections within a COMP. Returns node positions and connection graph.",
        inputSchema={
            "type": "object",
            "properties": {
                "comp_path": {
                    "type": "string",
                    "description": "Path to COMP (e.g., /project1)"
                },
                "depth": {
                    "type": "integer",
                    "default": 1,
                    "description": "How deep to search for children"
                }
            },
            "required": ["comp_path"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_python_exceptions",
        description="Get Python-specific exceptions from TouchDesigner scripts.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of exceptions to return"
                }
            },
            "required": []
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="capture_op_viewer",
        description="Universal operator viewer - captures any operator type (TOP, CHOP, SOP, DAT, MAT, COMP). Returns image for visual ops, text for DATs, geometry info for SOPs.",
        inputSchema={
            "type": "object",
            "properties": {
                "operator_path": {
                    "type": "string",
                    "description": "Path to ANY operator"
                },
                "resolution": {
                    "type": "integer",
                    "default": 512,
                    "description": "Output resolution in pixels"
                },
                "format": {
                    "type": "string",
                    "enum": ["jpeg", "png"],
                    "default": "jpeg"
                },
                "quality": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 1.0,
                    "default": 0.85
                }
            },
            "required": ["operator_path"]
        }
    ),

    # Core TD CRUD Tools (13)
    Tool(
        annotations=READ_ONLY,
        name="get_td_info",
        description="Get TouchDesigner server information (version, OS, MCP API version).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_td_nodes",
        description="List nodes under a parent path in TouchDesigner.",
        inputSchema={
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Parent path to list nodes from (e.g., /project1)"
                },
                "pattern": {
                    "type": "string",
                    "description": "Optional filter pattern"
                },
                "include_properties": {
                    "type": "boolean",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of nodes to return"
                }
            },
            "required": ["parent_path"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_td_node_parameters",
        description="Get detailed parameters of a specific node.",
        inputSchema={
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to node"
                }
            },
            "required": ["node_path"]
        }
    ),
    Tool(
        annotations=DESTRUCTIVE,
        name="create_td_node",
        description="Create a new operator under a parent path in running TouchDesigner.",
        inputSchema={
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Parent path where node will be created"
                },
                "node_type": {
                    "type": "string",
                    "description": "Type of node to create (e.g., 'noiseTOP', 'mathCHOP')"
                },
                "node_name": {
                    "type": "string",
                    "description": "Optional name for the new node"
                }
            },
            "required": ["parent_path", "node_type"]
        }
    ),
    Tool(
        annotations=DESTRUCTIVE,
        name="update_td_node_parameters",
        description="Update parameters of an existing node in running TouchDesigner.",
        inputSchema={
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to node"
                },
                "properties": {
                    "type": "object",
                    "description": "Parameter name-value pairs to update"
                }
            },
            "required": ["node_path", "properties"]
        }
    ),
    Tool(
        annotations=DESTRUCTIVE,
        name="delete_td_node",
        description="Delete an operator from running TouchDesigner.",
        inputSchema={
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to node to delete"
                }
            },
            "required": ["node_path"]
        }
    ),
    Tool(
        annotations=DESTRUCTIVE,
        name="execute_python_script",
        description=(
            "Execute arbitrary Python script in TouchDesigner. Returns result, stdout, and stderr.\n"
            "\n"
            "PERFORMANCE: prefer bulk DAT-read methods over cell-by-cell iteration.\n"
            "  Table DAT: op('/path').rows()    -> nested list of all rows\n"
            "  Text DAT:  op('/path').text      -> full text\n"
            "Measured (Wave 4 B31, 1000x24 float table):\n"
            "  - rows()                  : ~0.75 ms  (recommended)\n"
            "  - cell-by-cell 1000x24    : ~11 ms    (15x slower)\n"
            "The 1000-row case is fine in isolation, but if you're chaining many such reads\n"
            "in one script the total can compound — bulk is always safer.\n"
            "\n"
            "AVAILABLE GLOBALS (Wave 3 B16): op, ops, td, tdu, project, root, absTime, app, ui, "
            "iop, ipar, ext, mod, families, monitors, licenses, sysinfo, result. "
            "`me` and `parent` are sentinels in this context (scripts run outside any node) "
            "and raise a clear RuntimeError on access pointing you to op('/abs/path').\n"
            "\n"
            "DO NOT call ui.* (messageBox/chooseFile/chooseFolder/…) or project.save() inside "
            "the script — they block TD's single main thread and hang the live connection "
            "(~60 s, no timeout rescue). To checkpoint, use the save_td_project tool instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Python script to execute. Prefer bulk DAT-read methods (rows(), text) over cell-by-cell iteration for tables ≥ 500 rows."
                }
            },
            "required": ["script"]
        }
    ),
    Tool(
        annotations=DESTRUCTIVE,
        name="exec_node_method",
        description="Call a method on a node in TouchDesigner.",
        inputSchema={
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to node"
                },
                "method": {
                    "type": "string",
                    "description": "Method name to call"
                },
                "args": {
                    "type": "array",
                    "description": "Positional arguments"
                },
                "kwargs": {
                    "type": "object",
                    "description": "Keyword arguments"
                }
            },
            "required": ["node_path", "method"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_td_node_errors",
        description="Check node and descendant errors.",
        inputSchema={
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Path to node to check"
                },
                "recurse": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include descendant errors"
                }
            },
            "required": ["node_path"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_td_classes",
        description=(
            "List TouchDesigner Python classes from the `td` module. "
            "Use `mode='summary'` to get just category counts (~150 tokens) or "
            "`mode='names'` for a sorted name list (~1-2k tokens) instead of the "
            "default full dump (~50k tokens)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["full", "summary", "names"],
                    "description": "Response detail level. Default 'full' returns every class with its docstring. 'summary' returns category counts. 'names' returns a sorted name list with no descriptions.",
                    "default": "full"
                }
            },
            "required": []
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_td_class_details",
        description="Get details of a specific TouchDesigner Python class.",
        inputSchema={
            "type": "object",
            "properties": {
                "class_name": {
                    "type": "string",
                    "description": "Name of the class (e.g., 'OP', 'CHOP', 'TOP')"
                }
            },
            "required": ["class_name"]
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_td_module_help",
        description=(
            "Get Python help() for a module or class. "
            "Default `mode='summary'` returns ~1-3 KB overview (type + first "
            "docstring line + first 20 public attributes). Pass `mode='full'` "
            "for the complete pydoc text. No cap on full mode; narrow the target "
            "(e.g. 'td.OP' rather than bare 'td' which measures ~35 MB)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Module or class to get help for (e.g., 'td', 'td.OP', 'td.tdu')"
                },
                "mode": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "default": "summary",
                    "description": "Response detail. 'summary' (default) gives a short overview; 'full' returns the complete pydoc text with no cap. For bare 'td', use summary (full would be ~35 MB)."
                }
            },
            "required": ["target"]
        }
    ),
    Tool(
        annotations=WRITE_CHECKPOINT,
        name="save_td_project",
        description=(
            "Take a dialog-proof CHECKPOINT of the running project: a pure filesystem "
            "copy of the last-saved .toe to the project's Backup/ folder (falls back to "
            "~/.td_builder/restore_points/). Never raises a TD save/overwrite dialog and "
            "never rebinds the project — safe to call unattended before a risky edit "
            "batch. Argless.\n"
            "\n"
            "CAPTURES LAST-MANUAL-SAVE STATE ONLY. It copies what is on disk, not unsaved "
            "in-memory edits — there is no dialog-safe way to flush those. The returned "
            "`source_mtime` tells you exactly how stale the snapshot is.\n"
            "\n"
            "FRESH-CHECKPOINT RECIPE (before a risky exec batch):\n"
            "  1. Ask the artist to save (Ctrl+S).\n"
            "  2. Call save_td_project.\n"
            "  3. VERIFY: compare the returned `source_mtime` to the prior value "
            "(get_mutation_status.last_snapshot / a previous receipt). If it did NOT "
            "advance, the artist did not save — re-ask; do NOT proceed.\n"
            "  4. Proceed. This bounds any rollback loss to the batch itself.\n"
            "\n"
            "On timeout/recovery, poll get_mutation_status. Rolling back to a snapshot "
            "restores last-saved state and loses EVERY API mutation since that save — "
            "surface that (source_mtime + seq delta) before recommending it."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        annotations=READ_ONLY,
        name="get_mutation_status",
        description=(
            "Report what has committed since the server started — the post-timeout "
            "recovery surface. Returns the last committed mutation seq, the last "
            "mutation, whether the session is dirty since the last explicit checkpoint, "
            "and both the explicit (save_td_project) and implicit (pre-mutation) snapshot "
            "metadata incl. how stale each is. RETRY it after a client timeout: it queues "
            "behind TD's busy main thread and answers once TD is free. Atomic mutators "
            "(create/update/delete): seq advanced => committed, unchanged => not. Exec "
            "tools cannot self-distinguish partial-then-stalled — treat rollback as the "
            "default posture on an exec timeout, disclosing what would be lost first."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
]


# Handler dispatch map
TD_LIVE_HANDLERS = {
    # Visual Feedback
    "capture_top_output": capture_top_output,
    "get_top_info": get_top_info,
    "get_cook_errors": get_cook_errors,
    "get_error_summary": get_error_summary,
    "capture_network_layout": capture_network_layout,
    "get_python_exceptions": get_python_exceptions,
    "capture_op_viewer": capture_op_viewer,
    # Core TD CRUD
    "get_td_info": get_td_info,
    "get_td_nodes": get_td_nodes,
    "get_td_node_parameters": get_td_node_parameters,
    "create_td_node": create_td_node,
    "update_td_node_parameters": update_td_node_parameters,
    "delete_td_node": delete_td_node,
    "execute_python_script": execute_python_script,
    "exec_node_method": exec_node_method,
    "get_td_node_errors": get_td_node_errors,
    "get_td_classes": get_td_classes,
    "get_td_class_details": get_td_class_details,
    "get_td_module_help": get_td_module_help,
    # Session management (D3 / W6a)
    "save_td_project": save_td_project,
    "get_mutation_status": get_mutation_status,
}
