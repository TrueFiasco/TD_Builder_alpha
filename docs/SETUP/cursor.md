# Setup — Cursor (optional / nice-to-have)

Cursor is an optional target (not the alpha pass criterion, but commonly used).

## 1. Config file

Create or edit `.cursor/mcp.json` in your workspace (or the global
`~/.cursor/mcp.json`):

```jsonc
{
  "mcpServers": {
    "td-builder-prealpha": {
      "command": "C:\\Users\\Jake\\AppData\\Local\\Python\\pythoncore-3.11-64\\python.exe",
      "args": ["C:\\TD_builder_pre_alpha\\META_AGENTIC_TOOL\\mcp_server.py"],
      "env": {
        "PYTHONPATH": "C:\\TD_builder_pre_alpha;C:\\TD_builder_pre_alpha\\td-mcp;C:\\TD_builder_pre_alpha\\META_AGENTIC_TOOL",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

## 2. Enable + verify

Open **Settings → MCP** in Cursor, confirm `td-builder-prealpha` shows green,
then ask the agent to call **`get_server_info`** and check `script_path`.

## 3. (Optional) live-TD tools

Import `C:\TD_builder_pre_alpha\network-editor-mcp\td\mcp_webserver_base.tox`
into TouchDesigner (WebServer DAT on `http://127.0.0.1:9981`).

Same `mcpServers` shape works for Cline/Continue/Zed — only the config file
location differs.
