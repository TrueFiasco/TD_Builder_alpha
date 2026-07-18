# Setup — Cursor

Cursor speaks MCP over stdio. Add the two servers to your MCP config (`.cursor/mcp.json` or Cursor's
MCP settings) — same shape as `MCP/claude_desktop_config.json` (replace `<RELEASE_ROOT>`):

- **`td-builder`** → `<RELEASE_ROOT>/.venv/Scripts/python.exe <RELEASE_ROOT>/MCP/server.py` —
  18 offline tools, key-free.
- **`td-builder-live`** → `<RELEASE_ROOT>/.venv/Scripts/python.exe <RELEASE_ROOT>/MCP/live_server.py` —
  22 live tools; only with TouchDesigner open.

The command must be the **venv's python** (the interpreter `pip install -e ".[dev]"` ran in):
`<RELEASE_ROOT>\.venv\Scripts\python.exe` on Windows, `<RELEASE_ROOT>/.venv/bin/python` on
macOS/Linux — a bare `python` is the system interpreter and fails with `ImportError`.

Env: `PYTHONIOENCODING=utf-8`, `TD_BUILDER_ROOT=<RELEASE_ROOT>` (+ `TD_API_URL` for the live server).
No API key. Run `.venv/Scripts/python.exe scripts/check_deps.py` to verify your install, then confirm
with `get_server_info` (version `0.2.1`).

## Get better results
- Before a complex build, have the model call **`get_expert_prompt`** and follow it (experts:
  `td_designer`, `network_builder`, `td_glsl_expert`, `td_python_expert`, `ui_expert`, `critic`).
- Paste a primer from [`LLM/Pre-Prompts/README.md`](../../LLM/Pre-Prompts/README.md) into your chat
  (or add it to your Cursor rules) — builder / GLSL / live-session variants.
- The agent skills in [`Agents/td-builder-howto/SKILL.md`](../../Agents/td-builder-howto/SKILL.md)
  (live-TD gotchas) and [`Agents/td_network_analysis/SKILL.md`](../../Agents/td_network_analysis/SKILL.md)
  (`.toe` analysis) also work well as rules/context files.
