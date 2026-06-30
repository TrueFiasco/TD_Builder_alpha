# Setup — Cursor

Cursor speaks MCP over stdio. Add the two servers to your MCP config (`.cursor/mcp.json` or Cursor's
MCP settings) — same shape as `MCP/claude_desktop_config.json` (replace `<RELEASE_ROOT>`):

- **`td-builder`** → `python <RELEASE_ROOT>/MCP/server.py` — 16 offline tools, key-free.
- **`td-builder-live`** → `python <RELEASE_ROOT>/MCP/live_server.py` — 19 live tools; only with
  TouchDesigner open.

Env: `PYTHONIOENCODING=utf-8`, `TD_BUILDER_ROOT=<RELEASE_ROOT>` (+ `TD_API_URL` for the live server).
No API key. Run `python scripts/check_deps.py` to verify your install, then confirm with
`get_server_info` (version `0.2.0`).
