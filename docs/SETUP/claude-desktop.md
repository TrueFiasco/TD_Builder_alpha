# Setup — Claude Desktop

Register the two TD Builder MCP servers. Replace `<RELEASE_ROOT>` with this release folder's
absolute path. **No API key is needed.**

## 1. Config location
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

## 2. Add the servers
(Template: `MCP/claude_desktop_config.json`.)
```jsonc
{
  "mcpServers": {
    "td-builder": {
      "command": "<RELEASE_ROOT>/.venv/Scripts/python.exe",
      "args": ["<RELEASE_ROOT>/MCP/server.py"],
      "env": { "PYTHONIOENCODING": "utf-8", "TD_BUILDER_ROOT": "<RELEASE_ROOT>" }
    },
    "td-builder-live": {
      "command": "<RELEASE_ROOT>/.venv/Scripts/python.exe",
      "args": ["<RELEASE_ROOT>/MCP/live_server.py"],
      "env": { "PYTHONIOENCODING": "utf-8", "TD_API_URL": "http://127.0.0.1:9981" }
    }
  }
}
```
- **`command` must be the venv's python** — the interpreter the quick start installed the
  dependencies into: `<RELEASE_ROOT>\.venv\Scripts\python.exe` (Windows) or
  `<RELEASE_ROOT>/.venv/bin/python` (macOS/Linux). A bare `"python"` is the system interpreter,
  which doesn't have the deps — the server dies with `ImportError` before it ever registers.
  Verify with `.venv\Scripts\python.exe scripts\check_deps.py` (all green) before restarting.
- Add **`td-builder-live`** only when TouchDesigner is open (it carries 19 extra tool schemas).

## 3. Restart Claude Desktop
Fully quit and reopen. Confirm with **`get_server_info`** — `version` should be `0.2.0`.

## 4. Live-TD tools
Open TouchDesigner 2023+ and import `<RELEASE_ROOT>/MCP/td-webserver/mcp_webserver_base.tox`. Its
WebServer DAT listens on `http://127.0.0.1:9981` (override with the `TD_API_URL` env var).
