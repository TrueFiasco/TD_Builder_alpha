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
      "command": "python",
      "args": ["<RELEASE_ROOT>/MCP/server.py"],
      "env": { "PYTHONIOENCODING": "utf-8", "TD_BUILDER_ROOT": "<RELEASE_ROOT>" }
    },
    "td-builder-live": {
      "command": "python",
      "args": ["<RELEASE_ROOT>/MCP/live_server.py"],
      "env": { "PYTHONIOENCODING": "utf-8", "TD_API_URL": "http://127.0.0.1:9981" }
    }
  }
}
```
- Use your Python 3.11 path (or `"python"` if 3.11 is first on `PATH`). Run
  `python scripts\check_deps.py` first to confirm deps + KB are in place.
- Add **`td-builder-live`** only when TouchDesigner is open (it carries 19 extra tool schemas).

## 3. Restart Claude Desktop
Fully quit and reopen. Confirm with **`get_server_info`** — `version` should be `0.1.1`.

## 4. Live-TD tools
Open TouchDesigner 2023+ and import `<RELEASE_ROOT>/MCP/td-webserver/mcp_webserver_base.tox`. Its
WebServer DAT listens on `http://127.0.0.1:9981` (override with the `TD_API_URL` env var).
