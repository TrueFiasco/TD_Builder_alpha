# Changelog

## Unreleased

### Fixed
- **Offline builder no longer re-stubs hand-edited shader/script files on rebuild**
  (`toe_builder_bridge._write_docked_dats`): when a design authors no content for a docked
  file-backed DAT, an existing `shaders/*.glsl` (or `scripts/`/`tables/` file) is preserved
  instead of being overwritten with the stub — syncfile-authored operator edits survive a
  rebuild. A design that does carry `shader`/`content` still wins (design is source of truth).
  Regression tests: `tests/engine/test_builder_shader_field.py` (rebuild-preserve + design-wins).
- **GLSL TOP accepts the `content` field alias** for its pixel shader (previously only the
  POP/compute path took the alias; a TOP authored under `content` silently shipped the stub
  while the build reported SUCCESS).
- **GLSL TOP accepts dict-form `uniforms`** (`{"uScale": 1}`) like the POP path; previously it
  crashed the build with `AttributeError: 'str' object has no attribute 'get'`
  (`_build_glsl_parm`) after passing `td_validate`. Both forms now work on both families.
  Regression test: `tests/engine/test_builder_uniforms.py::test_glsltop_uniforms_dict_form`.
- **Missing-family type fallback warns loudly** (`logger.warning`, not just verbose log) when an
  ungrounded op type with no `family` defaults to `TOP:*` — the silent path behind the GAPS
  BUG-1 base-COMP symptom.
- **`Agents/td_network_analysis` skill wired in**: added the YAML frontmatter
  (`name: td-network-analysis`) that skill-aware clients need to register it — advertised in the
  docs since 0.1.1 but previously not loadable — plus a content-accuracy pass (POPs corrected to
  Point Operators with real operator names, completed `expand_toe_file` summary schema, real
  cross-skill integrations instead of nonexistent ones).
- Removed the skill's three orphaned `examples/` files (pre-`expand_toe_file` manual-parsing
  workflow, unverified benchmark figures); the worked example inside `SKILL.md` remains.

### Security
- **Load-time integrity check for KB pickles** (`MCP/server_core/kb_integrity.py`): the server no
  longer unpickles whatever sits in `KB/`. Both runtime unpicklers (`lexical_index/bm25.pkl`,
  `knowledge_graph_enhanced.gpickle`) hash the exact bytes before `pickle.loads` and require a match
  against `KB/kb_receipt.json` or the pinned `artifact_sha256` map now committed in
  `scripts/vector_db_release.json`. Non-matching or unreceipted files are **refused** and the server
  degrades loudly instead of loading them: BM25 refused → dense-only retrieval; graph refused →
  graph features off. This is defense-in-depth against a KB **corrupted through the distribution
  path** — a bad/substituted download (caught at fetch time by the zip sha256) or a poisoned build
  cache (caught here at load time, the cache being a separate trust domain from the committed pins).
  It is **not** protection against a local adversary who can already write `KB/` (they could forge
  the receipt too). `fetch_vector_db.py` pin-checks the extracted artifacts and writes the receipt;
  `kb_build`/`reembed`/`build_bm25`/`rebuild_graph` receipt their outputs; a new
  `scripts/receipt_kb.py` blesses (`--check` audits, `--print-pins` pins) an existing KB.
  `TD_BUILDER_TRUST_KB=1` bypasses verification with a loud warning (maintainer iteration only).
  **Upgrade note:** a KB fetched before this change verifies via the committed pins automatically;
  a KB you built yourself needs one `python scripts/receipt_kb.py` run.

## 0.2.0 — knowledge-base redesign + hybrid retrieval

A ground-up rebuild of the knowledge base and its search stack. The MCP tool surface is unchanged;
this release is about retrieval quality, build correctness, and a leaner, fully-offline bundle.

### Changed
- **KB rebuilt from condensed pointer chunks:** the vector store went from ~34,350 docs to **6,447**
  condensed chunks that hydrate from `operators.json` + Resources at query time (~110 MB → ~41 MB
  store). `operators.json` was **re-grounded against live TouchDesigner** (correct `.n` build tokens +
  parameter coverage).
- **Hybrid retrieval stack** (`MCP/server_core/search/retrieval_stack.py`): dense (`all-MiniLM-L6-v2`)
  + BM25 → RRF(k=60) → operator-aware router → cross-encoder rerank → calibrated score-floor + dedup.
- **Bundle is now offline end-to-end:** the cross-encoder reranker ships inside the bundle
  (`KB/models/ms-marco-MiniLM-L-6-v2/`), so first-run search needs no network/model download.
- `scripts/check_deps.py` now verifies the Phase-2 artifacts (`lexical_index/bm25.pkl`, the bundled
  reranker) instead of the removed `graphrag.json`.
- Version bumped to **0.2.0** (`pyproject.toml`, `SERVER_VERSION`, acceptance test).

### Added
- `KB/lexical_index/bm25.pkl` — BM25 lexical index for hybrid retrieval.
- `KB/models/ms-marco-MiniLM-L-6-v2/` — bundled cross-encoder reranker.
- `KB/sources.lock.json` — build provenance (pinned source revisions).
- `kb_build/` pipeline (condensed-chunk ingest + Phase-2 artifact builders) and an `eval/` harness
  (search-ranking, coverage, and build-correctness gates).

### Removed
- `KB/graphrag.json` (~58 MB): its chunks now live as condensed pointer chunks in `vector_db/`.

### Fixed
- **Build-correctness gate:** the KB now provably builds valid TouchDesigner (token-exact operator
  build tokens + parameter maps), fixing 64 wrong `.n` tokens and dropped parameters in the core builder.

### Verified
- Search-ranking, coverage, and build-correctness eval tiers green; offline-built `.tox` imports
  validated in live TouchDesigner.

## 0.1.1 — key-free, consolidated, two-server release

A large consolidation/refactor of the 0.1.0 alpha into a clean, key-free public release.

### Changed
- **Two MCP servers** instead of one: `td-builder` (offline, **17 key-free tools**) and
  `td-builder-live` (**19 live-TD tools**). Splitting the live tools out keeps offline sessions from
  carrying ~19 unused tool schemas in context.
- **Six-folder layout:** `MCP/` (`server.py` + `live_server.py` + `server_core/` + `engine/` +
  `live_client/` + `td-webserver/`), `KB/`, `Agents/` (experts/expertise/skills — the server reads
  them here), `Config/`, `LLM/Pre-Prompts/`, `Tools/`. (`unified_system` → `MCP/engine`;
  `META_AGENTIC_TOOL` → `MCP/server_core`.)
- **KB search is local-only / key-free:** forced `EMBEDDING_PROVIDER=local` (`all-MiniLM-L6-v2`,
  matching the shipped vector store). This also **fixes a latent bug** where the `voyage` default
  would dimension-mismatch the local store and break search.
- `fetch_vector_db.py` now downloads over **public HTTPS** (no `gh` CLI / GitHub account needed).
- All shipping paths resolve via `__file__` / `TD_BUILDER_ROOT` — the folder is relocatable.

### Removed
- The **V0–V6 Python multi-agent strategy runner** (never reachable via MCP) and everything that only
  served it (13 execution modules, `compaction`/`concurrency`/`history`/`meta` self-improvement infra,
  `creative_expert` + `cg_expert`).
- **All external-API surface:** `spawn_engineer` / `spawn_expert` / `td_compact_expertise` tools, the
  `AgentWithTools` class, the `anthropic` dependency, and the cloud embedding-provider options
  (Voyage/OpenAI/Cohere). `mcp_server.py` shrank ~2230 → ~1750 lines.
- The legacy `td-mcp/` server, the `core/` stub, the `kb_pipeline/` build tool, all dev scripts,
  internal reports/`CLAUDE.md` files, `.bak`s, the benchmark test suite, and `MODES.md` (only one
  mode — key-free — remains).

### Fixed
- `find_operator_examples` no longer crashes when called with `operator_name` (now accepts both
  `operator`/`operator_name`).
- `find_parameter_usage` no longer crashes when `parameter_name` is omitted.

### Added
- `expand_toe_file` tool — expand a `.toe`/`.tox` (via `toeexpand`) and parse it offline to a
  node/connection **summary** (non-default params with value + mode) or the **full** lossless JSON;
  powers the `td_network_analysis` skill.
- `scripts/check_deps.py` — verifies Python version, runtime packages, and KB presence.
- Authored docs throughout: per-folder READMEs, `Tools/TOOLS.md`, `Config/SETTINGS.md`,
  `LLM/Pre-Prompts`, the two-server client-config template.

### Verified
- 22-check acceptance + smoke gate green from the release folder *and* from a relocated copy.
- Two servers load 16 (offline) + 19 (live) tools; live tools validated against TouchDesigner
  099.2025 (WebServer DAT on :9981).

### Known limitations
- BASIC-mode `.toe` building emits parameter-format warnings (LOSSLESS round-trip is solid).
- `td_build_project(palette=…)` is a known-broken path (deferred).
- C++/shared-memory `wiki_supplemental` guides deferred to V0.2.
