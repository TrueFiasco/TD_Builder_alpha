# Setup — ChatGPT Desktop (alpha pass-criterion client)

ChatGPT Desktop is the **hard compatibility target** for the alpha: a
non-Anthropic client that must work. The server speaks plain MCP over stdio, so
no code changes are needed — only registration.

## 1. Enable MCP / connectors

ChatGPT Desktop exposes MCP servers under **Settings → Connectors / Developer
(MCP)**. Enable developer/MCP mode if it is gated behind a toggle.

## 2. Add the server

Add a local (stdio) MCP server with:

- **Command:** full path to Python 3.11, e.g.
  `C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe`
- **Arguments:** `C:\TD_builder_pre_alpha\META_AGENTIC_TOOL\mcp_server.py`
- **Environment:**
  - `PYTHONPATH = C:\TD_builder_pre_alpha;C:\TD_builder_pre_alpha\td-mcp;C:\TD_builder_pre_alpha\META_AGENTIC_TOOL`
  - `PYTHONIOENCODING = utf-8`
  - `PYTHONUTF8 = 1`
  - (Mode 2 only) `ANTHROPIC_API_KEY = sk-...`

If ChatGPT Desktop uses a JSON config rather than a form, the shape matches the
[Claude Desktop guide](claude-desktop.md) `mcpServers` block — reuse it verbatim.

## 3. Restart and verify

Restart ChatGPT Desktop. Ask it to call **`get_server_info`** and confirm
`script_path` points at `C:\TD_builder_pre_alpha\...`. Then run the
[demo walkthrough](../DEMO_WALKTHROUGH.md) — it is written to be client-neutral.

## Notes / known constraints

- ChatGPT Desktop's MCP support is newer than Claude Desktop's; if a tool that
  returns an **image** (`capture_op_viewer`, `capture_top_output`) renders
  poorly, fall back to the text tools — image-return shape normalization is
  tracked for the alpha communication layer.
- Tools with very long descriptions may be truncated in the picker; functionality
  is unaffected.
- No API key is required for Mode 1 (everything except `spawn_engineer` /
  `spawn_expert`).
