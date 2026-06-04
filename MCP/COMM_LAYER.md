# MCP Communication Layer (alpha standard)

The TD Builder alpha ships **one** MCP server (Python, stdio). This document
is the contract every tool conforms to so the server is portable across MCP
clients (Claude Desktop, ChatGPT Desktop, Cursor, Cline, Continue, …) and
LLM-agnostic (plain MCP + JSON-Schema; no Anthropic/OpenAI-specific shapes).

## Transport & protocol
- stdio, Model Context Protocol. No client-specific extensions.
- Tool inputs are plain JSON Schema (`inputSchema` on each `Tool`).
- `stdout` is the JSON-RPC channel only. All diagnostics go to `stderr`
  (the server redirects stray prints to stderr during import; see
  `mcp_server.py` stdout guard).

## Response envelope
Tools SHOULD return their payload as `TextContent` with this JSON shape:

```json
{
  "ok": true,
  "data": { "...": "tool-specific result" },
  "error": null,
  "meta": { "tool": "<name>", "server": "touchdesigner-mcp-server" }
}
```

On failure:

```json
{
  "ok": false,
  "data": null,
  "error": { "message": "human-readable", "hint": "actionable next step" },
  "meta": { "tool": "<name>", "server": "touchdesigner-mcp-server" }
}
```

Reference implementation: the `get_server_info` tool returns exactly this
envelope (`{ok,data,meta}`) and is the canonical example.

Image-returning tools (`capture_op_viewer`, `capture_top_output`) return an
`ImageContent` block plus a short `TextContent` status line — clients that
cannot render images still get the status text. (Legacy tools that predate
this spec return bare text/markdown; they remain functional and are migrated
opportunistically — see "Conformance status".)

## Error / no-dependency conventions
- Missing running TouchDesigner → tools return a clear text message
  ("TouchDesigner not running … import mcp_webserver_base.tox … port 9981"),
  never an unhandled exception.
- Missing API key (Mode 1) → API-coupled tools (`spawn_engineer`,
  `spawn_expert`) return an envelope with
  `error.message = "requires an API key (Mode 2)"` and a `hint` pointing at
  `docs/MODES.md`. They never crash the server or block Mode-1 tools.
- Unknown tool name → `{"ok": false, "error": {"message": "Unknown tool …"}}`.

## Modes (see ../docs/MODES.md)
- **Mode 1 (no key):** every tool except `spawn_engineer`/`spawn_expert`.
- **Mode 2 (BYO key):** set `ANTHROPIC_API_KEY` (or provider key) in the
  server `env`; the two agentic tools activate. No provider SDK is imported
  unless a key is present.

## Conformance status (alpha)
- `get_server_info` — full envelope (reference).
- KB/build/validate/convert tools — structured JSON payloads; envelope
  wrapping is being rolled out, payload content is stable.
- Live-TD tools — markdown/image + graceful no-TD text fallback (verified).
- Known-limitation tools documented in `../docs/KNOWN_ISSUES.md`.
