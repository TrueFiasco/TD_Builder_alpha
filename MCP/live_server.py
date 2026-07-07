"""TD Builder - live-TD MCP server.

The 21 tools that talk to a *running* TouchDesigner via its WebServer DAT
(default http://127.0.0.1:9981). Register this server *in addition to* the
offline `td-builder` server, and only when TouchDesigner is open. Keeping the
live tools in a separate server means offline sessions don't carry their ~21
tool schemas in the model's context.

Override the TD endpoint with the TD_API_URL env var.

    "td-builder-live": { "command": "python",
                         "args": ["<RELEASE_ROOT>/MCP/live_server.py"] }
"""
import asyncio
import sys
from pathlib import Path

# The live client is a self-contained module under MCP/live_client/.
sys.path.insert(0, str(Path(__file__).resolve().parent / "live_client"))
# server_instructions lives one level up, in MCP/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import Tool, TextContent  # noqa: E402

import td_live_client  # noqa: E402
from server_instructions import load_instructions  # noqa: E402

# D2 (harness item 3b): same single-sourced non-negotiables file, but this is the
# LIVE server, so scope="live" -> [always] + [live-only] (adds the running-TD
# gotchas: GLSL info-DAT, save, place, flat exec scope). Fail-soft baked in.
app = Server("td-builder-live", instructions=load_instructions(scope="live"))


@app.list_tools()
async def list_tools() -> list[Tool]:
    return list(td_live_client.TD_LIVE_TOOLS)


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = td_live_client.TD_LIVE_HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown live tool: {name}")]
    return await handler(arguments or {})


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
