# Alpha Comparison Report

Before = original development tree (`C:\TD_Projects\`, ≈ pre_alpha baseline).
After  = packaged alpha (`C:\TD_builder_alpha\`).

## Footprint

| Metric | Before (dev tree) | After (alpha) | Δ |
|---|---|---|---|
| Files | ~608,766 | 39,587 | −94% |
| Size | ~36.9 GB | 1.68 GB | −95% |
| Quarantined (recoverable, `_out_of_scope/`, full backup at `C:\TD_Projects\`) | — | 549k files / 34.9 GB | — |

## MCP tools (before/after accounting)

| | Before | After |
|---|---|---|
| MCP servers | 2 nominal (Python active; TypeScript `network-editor-mcp` already archived/retired) | **1** (Python, stdio) |
| Connected tools | 37 (18 base + 19 TD-Live) | **37** (same surface) |
| Added | — | `get_server_info` (was added during prep; counted in the 37) |
| Removed/merged | TypeScript server retired *before* this work (its TD asset `mcp_webserver_base.tox` retained) | no tool removed/merged — single server already canonical |

No tool behaviour regressed. `OperatorRegistry` now reads the enriched
superset KB → validation gained 14,375 typed params (strictly richer).

## Knowledge base

| | Before | After |
|---|---|---|
| Operator JSON | 3 variants + 2 exact root/td-mcp dups | 1 `KB/operators.json` (enriched superset) |
| GraphRAG / graph | `td_graphrag.json` + 2 dups, 3 graph pickles/json | `KB/graphrag.json` + `KB/knowledge_graph_enhanced.gpickle` |
| Vector DBs | 5 (1×34,350 + 3×1,869 + 1×20,477 intermediate) | 1 `KB/vector_db/` (34,350, `td_unified`) |
| Raw source corpora | scattered across META/td-mcp/kb_pipeline | `KB/sources/` (8 unique corpora) |
| Provenance/proof | none | `KB/manifest.json`, `KBU_REPORT.md`, `KBU_COMPLETENESS_PROOF.txt`, `run_completeness_proof.py` |

**Zero knowledge loss** — completeness proof D.1/D.4/D.6 ALL PASS (every
quarantined store proven exact-dup or strict subset of the retained bundle).

## Behaviour changes
- None functional. Server verified after **every** transformation:
  `tools=37, get_server_info=True, td_live=True, kg=37526,
  hybrid=UnifiedSearchAdapter`.
- `OperatorRegistry` → enriched superset (richer, proven superset).
- New `get_server_info`; new no-API graceful fallback for `spawn_*`.

## Test results
- Pre-packaging baseline: **51 passed / 7 failed / 12 skipped**
  (the 7 failures pre-existing — stale builder-schema tests, G1 — not
  regressions; identical before and after every quarantine round).
- Alpha ships no test suite (by decision). Dev pytest still runnable from
  `_out_of_scope/`.

## Client compatibility matrix

| Client | Mechanism | Status |
|---|---|---|
| Claude Code (this session) | stdio, auto-registered `td-builder-prealpha` | ✅ verified (get_server_info, KB tools, live-TD capture) |
| Claude Desktop | `claude_desktop_config.json` (`td-builder-alpha` registered) | ✅ config valid; launcher verified (fresh import 37 tools) |
| ChatGPT Desktop (**pass criterion**) | `docs/SETUP/chatgpt-desktop.md` | ⏳ user step — plain stdio/JSON-Schema, no client-specific shapes (COMM_LAYER conformant) |
| Cursor / Cline / Continue | `docs/SETUP/cursor.md` (same `mcpServers` shape) | ➖ nice-to-have, same mechanism |
| Live TouchDesigner | WebServer DAT :9981 via `MCP/td-webserver/mcp_webserver_base.tox` | ✅ verified end-to-end (TD 099.2025.32460) |

## Mode verification
- **Mode 1 (no key):** all non-agentic tools work; verified.
- **Mode 2 (key absent):** `spawn_engineer` → clean
  `{ok:false,error:{message:"requires an API key (Mode 2)",hint:…}}`
  envelope (verified `GUARD_OK`); never crashes, never blocks Mode-1.
