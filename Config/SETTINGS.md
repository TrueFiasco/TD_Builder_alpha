# Config — how to set up TD Builder

TD Builder is **key-free**: no API keys are required or used. Configuration is minimal.

## Files here
| File | What it does |
|---|---|
| `.env.template` | Copy to `.env` at the **release root** and edit if needed. Defines the embedding provider (local), KB paths, and performance knobs. |
| `search_config.json` | JSON defaults for the KB search stack (embedding provider/model, vector-db + graph paths, cache). Environment variables override these. |

## The knobs

```ini
# .env  (copy from .env.template, place at the release root)
EMBEDDING_PROVIDER=local            # local only — the shipped vector store was built with all-MiniLM-L6-v2
EMBEDDING_MODEL=all-MiniLM-L6-v2    # must match the store; do NOT switch to a cloud model
UNIFIED_VECTORDB_PATH=./KB/vector_db
GRAPH_DATA_PATH=./KB/knowledge_graph_enhanced.gpickle
# TD_BUILDER_ROOT=C:/path/to/this/release   # set to make the install relocatable
QUERY_TIMEOUT_MS=5000
CACHE_ENABLED=true
```

> **Why local-only?** The shipped vector store was embedded with `all-MiniLM-L6-v2`. Pointing the
> provider at a cloud model (Voyage/OpenAI) would embed queries in a different vector space and break
> search. Local embedding is the correct — and key-free — path.

## `TD_BUILDER_ROOT` (relocation)
Set `TD_BUILDER_ROOT` to this release folder's absolute path (in the MCP client config, see
`MCP/README.md`). The servers then resolve `KB/`, `Agents/`, etc. from there regardless of where you
run them from — so you can move/copy the folder anywhere.

## TouchDesigner endpoint (live server only)
`TD_API_URL` (default `http://127.0.0.1:9981`) — the WebServer DAT the live tools talk to.
