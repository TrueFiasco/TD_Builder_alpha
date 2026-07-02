# Config — how to set up TD Builder

TD Builder is **key-free**: no API keys are required or used. Configuration is minimal, and there
is **one config story**. Precedence, highest first:

1. **Environment variables** — e.g. the `"env"` block of your MCP client config (see `MCP/README.md`).
2. **`.env` at the release root** — copy `Config/.env.template` there and edit.
3. **`Config/search_config.json`** — JSON defaults for the search stack.
4. Code defaults (identical to the shipped files above).

These are the locations the code actually loads (`MCP/server_core/config/__init__.py`); a legacy
`.env` / `search_config.json` under `MCP/server_core/` is still honored as a fallback, but don't
put new config there.

## Files here
| File | What it does |
|---|---|
| `.env.template` | Copy to `.env` at the **release root** and edit if needed. |
| `search_config.json` | JSON defaults for the KB search stack. Environment variables / `.env` override it. |

## The knobs

```ini
# .env  (copy from Config/.env.template, place at the release root)
EMBEDDING_PROVIDER=local            # local only — this release has no cloud providers
EMBEDDING_MODEL=all-MiniLM-L6-v2    # must match the store; KB/manifest.json is authoritative
UNIFIED_VECTORDB_PATH=KB/vector_db  # relative paths resolve against the release root
GRAPH_DATA_PATH=KB/knowledge_graph_enhanced.gpickle
# TD_BUILDER_ROOT=C:/path/to/this/release   # set to make the install relocatable
```

> **Why local-only?** The shipped vector store was embedded with `all-MiniLM-L6-v2`. A different
> query embedder would embed queries in a different vector space and break search — so the KB's own
> `KB/manifest.json` is authoritative for the model, and an `EMBEDDING_MODEL` that disagrees with it
> makes semantic search fail loudly at load instead of returning garbage. Local embedding is the
> correct — and key-free — path.

## `TD_BUILDER_ROOT` (relocation)
Set `TD_BUILDER_ROOT` to this release folder's absolute path (in the MCP client config, see
`MCP/README.md`). The servers then resolve `KB/`, `Agents/`, `Config/`, and the root `.env` from
there regardless of where you run them from — so you can move/copy the folder anywhere.

## TouchDesigner endpoint (live server only)
`TD_API_URL` (default `http://127.0.0.1:9981`) — the WebServer DAT the live tools talk to.

## Debug/dev switches (env only, rarely needed)
- `RS_DISABLE=1` — bypass the Phase-2 hybrid retrieval stack (dense-only search).
- `EMBEDDING_ALLOW_MISMATCH=1` — allow an `EMBEDDING_MODEL` that disagrees with `KB/manifest.json`
  (search quality will be garbage; for experiments only).
