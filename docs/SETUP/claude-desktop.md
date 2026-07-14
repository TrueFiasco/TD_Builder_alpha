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
- Add **`td-builder-live`** only when TouchDesigner is open (it carries 22 extra tool schemas).

## 3. Restart Claude Desktop
Fully quit and reopen. Confirm with **`get_server_info`** — `version` should be `0.2.0`.

## 4. Live-TD tools
Open TouchDesigner 2025+ and import `<RELEASE_ROOT>/MCP/td-webserver/mcp_webserver_base.tox`. Its
WebServer DAT listens on `http://127.0.0.1:9981` (override with the `TD_API_URL` env var).

## 5. Get better results
- **Expert prompts** — before a complex build, ask Claude to call **`get_expert_prompt`** and follow
  it (experts: `td_designer`, `network_builder`, `td_glsl_expert`, `td_python_expert`, `ui_expert`,
  `critic`). This loads deep TD-specific rules the model won't otherwise apply.
- **Pre-prompts** — paste a primer from [`LLM/Pre-Prompts/README.md`](../../LLM/Pre-Prompts/README.md)
  at the start of a session (builder / GLSL / live-session variants).
- **Agent skills** — clients that support skills (e.g. Claude Code) can load
  [`Agents/td-builder-howto/SKILL.md`](../../Agents/td-builder-howto/SKILL.md) (live-TD gotchas and
  tool preferences) and [`Agents/td_network_analysis/SKILL.md`](../../Agents/td_network_analysis/SKILL.md)
  (analyzing existing `.toe`/`.tox` files).
