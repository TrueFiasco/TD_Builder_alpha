# MCP/ — the servers + engine

This folder holds **both MCP servers and all the code they run**.

```
MCP/
├── server.py          # OFFLINE launcher → server_core/mcp_server.py  (register as "td-builder")
├── live_server.py     # LIVE launcher    → live_client/td_live_client (register as "td-builder-live")
├── server_core/       # the offline server brain: mcp_server.py + KB search stack + config/ + meta_agentic/{execution}
├── engine/            # the TouchDesigner-file engine (parser, 5-stage validator, format converter, builder)
├── live_client/       # td_live_client.py — HTTP client + the 22 live-TD tools
├── td-webserver/      # the TouchDesigner-side asset: mcp_webserver_base.tox + handlers (WebServer DAT on :9981)
└── COMM_LAYER.md      # the HTTP protocol between the live tools and TouchDesigner
```

## Registering the servers

Both servers are plain stdio servers launched with a Python interpreter. Register **`td-builder`**
always, and **`td-builder-live`** only when you'll have TouchDesigner open (it carries 19 extra
tool schemas).

Use `claude_desktop_config.json` (template below — replace `<RELEASE_ROOT>` with this folder's path):

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

- **`command` must be the venv's interpreter** — the one the quick start installed the deps into:
  `<RELEASE_ROOT>\.venv\Scripts\python.exe` (Windows) / `<RELEASE_ROOT>/.venv/bin/python`
  (macOS/Linux). A bare `"python"` is the system interpreter: no deps installed there, so the
  server exits with `ImportError` before registering.

- Setting **`TD_BUILDER_ROOT`** makes the install fully relocatable (the server resolves `KB/`,
  `Agents/`, etc. from there). Without it, paths are inferred from the file location.
- The **live server** needs TouchDesigner running with `td-webserver/mcp_webserver_base.tox`
  imported (its WebServer DAT listens on `http://127.0.0.1:9981`; override with `TD_API_URL`).
- See `docs/SETUP/` for ChatGPT-desktop and Cursor variants.

## What each server exposes

- **`td-builder` (offline, 18 tools):** KB search + `td_validate` / `td_convert` / `td_build_project`
  / `td_build_status` + `expand_toe_file` + `get_expert_prompt` + `get_server_info`. 100% key-free.
- **`td-builder-live` (22 tools):** capture / node CRUD / introspection of the running TD project.

Full tool reference: [`../Tools/TOOLS.md`](../Tools/TOOLS.md).
