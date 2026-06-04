# Unified KB MCP Server

This folder contains the unified MCP server and the assistant contract (skills/schemas/workflows).

## Server
- `unified_mcp_server.py`
  - Tool: `td_assistant`
    - `action="query"`: search unified KB (vector + graph)
    - `action="build_python"`: generate a TouchDesigner Text DAT python script from a `TDNetworkSpec`-like object
    - `action="stats"`: retrieval performance stats

## Python runtime (recommended)
TouchDesigner ships Python 3.11. ChromaDB currently installs cleanly on Py311 but not on Py3.14.

Recommended:
- Use `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe` to run KB scripts and the MCP server.

## Config
- `claude_desktop_config_kb_pipeline.json`
  - Add/merge its `mcpServers` entry into your Claude Desktop MCP config to enable the server.
  - This config uses the project venv Python: `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe`

## TouchDesigner tools
Default bin path assumed by workflows:
- `C:\Program Files\Derivative\TouchDesigner\bin`
