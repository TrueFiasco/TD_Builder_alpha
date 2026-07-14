# MCP Communication Layer (alpha standard)

TD Builder ships **two** MCP servers (Python, stdio): the offline `td-builder`
(17 key-free tools) and the live `td-builder-live` (22 tools for a running
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
This release has **no cloud API key and one mode**. KB search uses a local
embedding model (all-MiniLM-L6-v2); there are no cloud providers and no
agent-spawning tools. Every **offline** tool works with no credentials.

The **live** `td-builder-live` server is the one exception: because its TD-side
WebServer DAT is reachable over the network, it uses a **local shared-secret
token** (not a cloud key) to authenticate requests. See below.

## Live-server security / auth
The live tools talk to a **WebServer DAT** inside TouchDesigner (default
`http://127.0.0.1:9981`). That DAT **binds all network interfaces and cannot be
restricted to loopback**, so without auth anyone on the same LAN (a venue or
studio Wi-Fi) could reach `execute_python_script` — unauthenticated remote Python
execution. The shared-secret token is the practical control.

**Scheme.** Every request must carry `Authorization: Bearer <token>`; the
controller verifies it (constant-time) **before routing** and returns **401**
otherwise. Exactly one route is open without a token — `GET /api/td/server/td`
(server identity/health) — so "is TD up?" stays graceful. CORS is locked down:
the former `Access-Control-Allow-Origin: *` is removed, so a browser cannot read
cross-origin responses or complete a preflight for the `Authorization` header.

**Token lifecycle.**
- **Storage:** `~/.td_builder/api_token` (per-user home dir). On first boot TD
  generates a random token there if none exists and prints only the *path* (never
  the value) to the textport.
- **Resolve order (both TD and client):** `TD_API_TOKEN` env → `TD_API_TOKEN_FILE`
  env (path override) → the default file above.
- **Same machine:** zero config — the client reads the same file automatically.
- **Remote client (client and TD on different machines):** copy the token *value*
  from the TD machine's `~/.td_builder/api_token` and set `TD_API_TOKEN` in the
  MCP client config's `env` block. (You could also point both at a shared
  `TD_API_TOKEN_FILE`.)
- **Rotation:** delete the token file (and clear any `TD_API_TOKEN` env), then
  **restart TouchDesigner** — the TD-side token is cached in-process for the
  session. Update the client to match.

**Residual risks / limits (this release).**
- **Plaintext HTTP.** The token and all payloads travel unencrypted. On an
  untrusted LAN, tunnel it (SSH/VPN) or keep everything on `127.0.0.1`. **TLS is
  out of scope this release** — token auth is the control, not confidentiality.
- **Screenshare leak.** Only the token *path* is printed on generation, never the
  value; still, treat `~/.td_builder/api_token` as a secret.
- **File permissions.** `chmod 600` is applied on POSIX only; on Windows the file
  is protected by the per-user `%USERPROFILE%` ACLs, not a mode bit.
- TouchDesigner's WebServer DAT has a native `password` parameter, but the
  header/Bearer scheme was chosen instead: it works uniformly across MCP clients
  and needs no per-DAT UI configuration.

**Debug logging** is OFF by default (`TD_API_DEBUG=1` to enable); response bodies
(which include multi-MB base64 captures) are never logged.

## Conformance status (alpha)
- `get_server_info` — full envelope (reference).
- KB/build/validate/convert tools — structured JSON payloads; envelope
  wrapping is being rolled out, payload content is stable.
- Live-TD tools — markdown/image + graceful no-TD text fallback (verified).
- Known-limitation tools documented in `../docs/KNOWN_ISSUES.md`.
