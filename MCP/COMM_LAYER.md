# MCP Communication Layer (alpha standard)

TD Builder ships **two** MCP servers (Python, stdio): the offline `td-builder`
(17 key-free tools) and the live `td-builder-live` (19 tools for a running
TouchDesigner). This document is the contract every tool conforms to so the
servers are portable across MCP clients (Claude Desktop, ChatGPT Desktop,
Cursor, Cline, Continue, …) and LLM-agnostic (plain MCP + JSON-Schema; no
Anthropic/OpenAI-specific shapes).

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
- Missing running TouchDesigner → live tools return a clear text message
  ("TouchDesigner not running … import mcp_webserver_base.tox … port 9981"),
  never an unhandled exception.
- Unknown tool name → `{"ok": false, "error": {"message": "Unknown tool …"}}`.

## Key-free by design
This release has **no API key and one mode**. KB search uses a local embedding
model (all-MiniLM-L6-v2); there are no cloud providers and no agent-spawning
tools. Every offline tool works with no credentials of any kind.

## Conformance status (alpha)
- `get_server_info` — full envelope (reference).
- KB/build/validate/convert tools — structured JSON payloads; envelope
  wrapping is being rolled out, payload content is stable.
- Live-TD tools — markdown/image + graceful no-TD text fallback (verified).
- Known-limitation tools documented in `../docs/KNOWN_ISSUES.md`.
