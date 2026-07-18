# Setup — ChatGPT Desktop

The servers speak plain MCP over stdio, so registration is the only step. **No API key needed.**

In ChatGPT Desktop's MCP settings, add two servers (replace `<RELEASE_ROOT>` with this folder's path):

- **`td-builder`** — command `<RELEASE_ROOT>/.venv/Scripts/python.exe`, args
  `<RELEASE_ROOT>/MCP/server.py` — 18 offline tools.
- **`td-builder-live`** — command `<RELEASE_ROOT>/.venv/Scripts/python.exe`, args
  `<RELEASE_ROOT>/MCP/live_server.py` — 22 live tools; add only when TouchDesigner is open.

The command must be the **venv's python** (where the quick start installed the deps):
`<RELEASE_ROOT>\.venv\Scripts\python.exe` on Windows, `<RELEASE_ROOT>/.venv/bin/python` on
macOS/Linux. A bare `python` is the system interpreter — no deps, `ImportError`, dead server.

Set env `PYTHONIOENCODING=utf-8` (and `TD_BUILDER_ROOT=<RELEASE_ROOT>` for relocatability;
`TD_API_URL=http://127.0.0.1:9981` for the live server). The full config shape is in
[`../../MCP/README.md`](../../MCP/README.md) / `MCP/claude_desktop_config.json`. Confirm with
`get_server_info` (version `0.2.1`).

## Get better results
- Before a complex build, ask the model to call **`get_expert_prompt`** and follow it (experts:
  `td_designer`, `network_builder`, `td_glsl_expert`, `td_python_expert`, `ui_expert`, `critic`).
- Paste a primer from [`LLM/Pre-Prompts/README.md`](../../LLM/Pre-Prompts/README.md) at the start of
  a session (builder / GLSL / live-session variants) — it teaches the verify-then-build workflow.
- For richer context, the guidance in [`Agents/td-builder-howto/SKILL.md`](../../Agents/td-builder-howto/SKILL.md)
  and [`Agents/td_network_analysis/SKILL.md`](../../Agents/td_network_analysis/SKILL.md) can be pasted
  into the conversation too.
