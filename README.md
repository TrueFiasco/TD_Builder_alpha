# TD Builder — Alpha

A Python system for AI-driven generation, validation, and conversion of
TouchDesigner networks, exposed to LLM clients as an MCP server, plus live
TouchDesigner editing/feedback tools.

## What's in here

| Path | What it is |
|---|---|
| `MCP/python/server.py` | **The MCP server entry point** (thin launcher → `META_AGENTIC_TOOL/mcp_server.py`). 18 base tools + ~18 live-TouchDesigner tools when TD is reachable. |
| `MCP/td-webserver/mcp_webserver_base.tox` | **TD-side asset** — import into TouchDesigner to enable the live tools. WebServer DAT listens on `http://127.0.0.1:9981`. |
| `unified_system/` | The engine: lossless `.toe` parser, 5-stage validator, format converter, LOSSLESS/BASIC `.toe` builder. Backs the `td-validate` / `td-convert` / `td-build` CLIs. |
| `td-mcp/` | Dependency layer on the server's import path (agents, builder, config, knowledge_base, validation, schemas). |
| `kb_pipeline/` | Knowledge-base ingestion/embedding pipeline (rebuilds the vector store + graph). |
| `META_AGENTIC_TOOL/meta_agentic/` | Multi-agent strategy runner (V0–V6). Python-only — **not** exposed via MCP. |
| `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed.json` | Canonical knowledge base — 670 operator specs (31.8 MB). The single source of truth. |
| `KB/vector_db/` | Vector store for semantic search. **Not in git** — fetched on first install via `scripts/fetch_vector_db.py`. |

See [PREREQUISITES.md](PREREQUISITES.md), [MODES.md](MODES.md), and
[docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md).

## Quick start (Windows + PowerShell)

> **Prerequisites:** Python 3.11 (range `>=3.10,<3.14`), TouchDesigner 2023+
> (needed only for the live tools and final `.toe` collapse), `gh` CLI
> (`winget install GitHub.cli`) for the vector-DB download from a private
> release.

```powershell
# 1. Clone (accept the repo invite first, then `gh auth login`)
gh repo clone TrueFiasco/TD_Builder_alpha
cd TD_Builder_alpha

# 2. Create venv on Python 3.11
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install (single editable install with optional Anthropic + dev deps)
pip install -e ".[api,dev]"

# 4. Download the vector DB (~110 MB) from the latest release
python scripts/fetch_vector_db.py

# 5. Copy env template and (optionally) fill in your VOYAGE_API_KEY
Copy-Item .env.template .env
# If you don't have one, FALLBACK_TO_LOCAL=true uses the local sentence-transformers model

# 6. Verify the install
pytest unified_system/tests/        # expect 55 passing
python -c "from meta_agentic.execution.expert_executor import EXPERT_CONFIGS; print(list(EXPERT_CONFIGS.keys()))"
# Expect: ['creative_expert','cg_expert','critic','td_designer','td_glsl_expert','network_builder','summary_generator','td_python_expert']

# 7. Register the MCP server with your client
#    See docs/SETUP/claude-desktop.md (or chatgpt-desktop.md / cursor.md).
#    Point it at:  python MCP\python\server.py
```

> **First run heads-up:** the first time anything imports `sentence-transformers`
> it downloads ~1.5 GB of model weights. The vector-DB step adds ~110 MB. Plan
> for a ~5–15 minute first install on a fresh machine.

## Live TouchDesigner setup (optional but assumed for live tools)

The ~18 live-TD tools (`create_td_node`, `capture_op_viewer`, `execute_python_script`, …) talk to TouchDesigner over an HTTP WebServer DAT.

1. Open TouchDesigner 2023+.
2. Drag `MCP/td-webserver/mcp_webserver_base.tox` into your project.
3. Confirm its WebServer DAT is listening on `http://127.0.0.1:9981` (override with the `TD_API_URL` env var if you need a different port).
4. Without this, the live tools return a clear "TouchDesigner not running" message and the rest still work.

## Modes (key-free vs. Anthropic API)

- **Mode 1 (default, key-free)** — everything except `spawn_engineer` / `spawn_expert` works without any API key.
- **Mode 2 (Anthropic API)** — set `ANTHROPIC_API_KEY` to enable agent-spawning tools.

See [MODES.md](MODES.md).

## Run the tests

```powershell
pytest unified_system/tests/          # 55 real tests: parser, validator, converter, round-trip
```

## Known limitations

- `find_similar_networks` — pattern coverage is partial (deferred item W5.3).
- BASIC-mode `.toe` building (networks built from scratch with no parsed source) emits parameter-format errors; LOSSLESS round-trip is solid.
- The multi-agent strategy runner (`meta_agentic/`) is Python-only; it is not reachable through the MCP tools.
- `spawn_engineer` / `spawn_expert` require an Anthropic API key (Mode 2). Everything else runs key-free.
