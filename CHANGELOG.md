# Changelog

## 0.1.0-alpha — first packaged alpha

First installable/runnable/tryable packaging of the TD Builder system,
prepared from the post-demo development tree.

### Added
- `get_server_info` MCP tool (`{ok,data,meta}` envelope; confirms which copy
  is running) + startup `__file__` stderr banner.
- Single consolidated knowledge base bundle `KB/` (operators / graphrag /
  enhanced graph / vector_db + raw `sources/` + `manifest.json` + audit
  report + reproducible completeness proof).
- Consolidated package layout: `MCP/` (server launcher + TD WebServer asset),
  `core/` (engine surface), `tools/` (CLI launchers), `KB/`,
  `skills_expertise/`, `docs/` (README, PREREQUISITES, MODES, SETUP/,
  DEMO_WALKTHROUGH, KNOWN_ISSUES).
- `bootstrap.py` shared PYTHONPATH surface; `MCP/python/server.py` launcher;
  `pyproject.toml` with `td-validate`/`td-convert`/`td-build` console scripts.
- `MCP/COMM_LAYER.md` LLM-agnostic communication standard.
- Mode-1/Mode-2 portability: `spawn_engineer`/`spawn_expert` degrade
  gracefully with no API key (clean envelope, never block Mode-1).
- Per-client setup guides (ChatGPT Desktop = pass criterion, Claude Desktop,
  Cursor).

### Changed
- `OperatorRegistry` now loads the **enriched superset** KB (proven strict
  superset; +14,375 typed parameters) — strictly richer validation, zero loss.
- All KB loaders are bundle-aware (`KB/`) with legacy fallback.

### Removed (quarantined → recoverable; full backup at `C:\TD_Projects\`)
- ~549k files / ~34.9 GB of dev cruft, scratch, build artifacts, the retired
  TypeScript `network-editor-mcp` server (its TD asset retained), redundant
  KB stores (proven exact-dups/subsets), all tests, dev/KB-build scripts.

### Verified
- Server loads 37 tools, KB graph 37,526 nodes, vector search live, after
  every transformation (quarantine ×3, KBU, KB consolidation, layout).
- Live-TD end-to-end: TD 099.2025.32460, WebServer :9981,
  `mcp_webserver_base.tox`, `capture_op_viewer` returns real frames.
- KBU completeness proof D.1/D.4/D.6: ALL PASS (zero knowledge loss).

### Known limitations
See `docs/KNOWN_ISSUES.md` (G1 stale builder-schema tests, BASIC-mode build,
`find_similar_networks` W5.3 partial coverage). Alpha ships no test suite.
