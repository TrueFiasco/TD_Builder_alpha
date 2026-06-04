# Setup — Claude Desktop (control client)

Claude Desktop is the **control** in our compatibility matrix (the demo ran
here). Setup is one config edit.

## 1. Locate the config

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

## 2. Add the server

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

- Use the full path to your Python 3.11 executable (or just `"python"` if 3.11
  is first on `PATH`).
- The three `PYTHONPATH` entries are **required** — the server imports from the
  repo root, `td-mcp`, and `META_AGENTIC_TOOL`.
- For Mode 2, add `"ANTHROPIC_API_KEY": "sk-..."` to `env`.
- If you already have a `touchdesigner` server pointing at another tree
  (e.g. `C:\TD_Projects\`), set its `"disabled": true` while testing this one.

## 3. Restart Claude Desktop

Fully quit and reopen. Confirm the tools loaded by calling **`get_server_info`** —
it returns `{cwd, script_path, version, server_name}`; `script_path` must show
`C:\TD_builder_pre_alpha\...` so you know which copy is live.

## 4. (Optional) live-TD tools

Open TouchDesigner, import
`C:\TD_builder_pre_alpha\network-editor-mcp\td\mcp_webserver_base.tox`. The
WebServer DAT listens on `http://127.0.0.1:9981`.
