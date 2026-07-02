# MCP/td-webserver/ — TouchDesigner-side WebServer asset

This is the component you import **into TouchDesigner** so the live-TD MCP
tools (`get_td_nodes`, `create_td_node`, `capture_op_viewer`,
`execute_python_script`, …) can talk to a running TD instance.

## Files
- `mcp_webserver_base.tox` — the base component (import this into your project)
- `modules/mcp_webserver_script.py` — the WebServer DAT callback handler
- `import_modules.py` — module loader used inside the .tox
- `modules/`, `templates/` — supporting code/templates

## Use
1. Open TouchDesigner (2025+).
2. Import `mcp_webserver_base.tox` into your project (top level is fine).
3. Its WebServer DAT listens on `http://127.0.0.1:9981`
   (override via the `TD_API_URL` env var on the MCP server).
4. The live MCP server (`../live_server.py`, registered as `td-builder-live`)
   talks to it; with TD not running the live tools return a clear
   "TouchDesigner not running" message, and the offline server (`../server.py`)
   is unaffected either way.

Verified working end-to-end against TD 099.2025.32460 (MCP API 1.4.1).
