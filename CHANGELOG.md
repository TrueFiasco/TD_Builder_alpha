# Changelog

## Unreleased

### Changed
- **Single-source hygiene bundle** (architecture-review candidate 9, owner-directed): four
  facts that had to agree in N places, previously held together by comments, now have seams
  or enforcement tests. (1) **Root resolution**: `mcp_server.py` and `config/__init__.py`
  import `REPO_ROOT`/`KB_ROOT` from `paths.py` instead of re-deriving them with private
  `parents[N]` walks (the `param_name_resolver` `parents[3]` bug's failure shape); drift
  pinned KB-free in `tests/engine/test_root_resolution.py` (runtime equality for config,
  AST guard + layout assertion for the server; `TD_BUILDER_ROOT` is now read in exactly one
  place). (2) **Auth constants**: the `TD_API_TOKEN`/`TD_API_TOKEN_FILE` + default-token-path
  mirror across `td_live_client.py` and td-webserver `utils/auth.py` is now test-enforced
  (`tests/unit/test_live_auth_unit.py`). (3) **Validation stack**: the
  `OperatorRegistry → FormatConverter → ValidationPipeline` trio, previously copy-pasted at
  five sites, is constructed only by the new engine seam
  `MCP/engine/api/validate.py::build_validation_stack()` (light-deps import and
  KB-`FileNotFoundError` propagation pinned in `tests/engine/test_validation_stack_seam.py`).
  (4) **Eval identity**: CI Lane R now runs `--compare` against the committed baseline
  (advisory; the refusal machinery previously never executed in CI), and the identity block
  gains a soft-warn tier — `engine_code_hash` warns (never refuses) when engine code drifted
  since the baseline, closing the `server_version` blind spot — plus an informational,
  never-compared `git_sha` (`eval/agent_eval/tests/test_identity_tiers.py`).

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

### Removed
- **Dead-weight sweep 2026-07** (11 audited items; manifests in `quarantine/README.md` →
  `deadweight_2026_07/`). Quarantined: the broken upstream OpenAPI codegen pair
  (`genHandlers.js` + mustache template — `generated_handlers.py` is hand-maintained, and the
  four comments describing it as live codegen are reworded), the superseded Track-D grounding
  prototype (ending the `GroundingValidator` name collision; `build_gate` no longer generates a
  stale "Deferred" claim for the validator that shipped in W3a / PR #13), the never-wired
  `lossless_writer.py` (manifest carries its `.parm`-quoting revival hazard), and the
  never-referenced `lossless_v2.schema.json` (accurate at quarantine time; wire-in revisit noted).
  Deleted in place: the orphaned `execute_tool_for_agent` shadow dispatcher (absence pinned), the
  provably-broken legacy `HybridGraphRAG` server fallback — a broken `unified_search` import now
  fails loudly, while `hybrid_search.py` itself stays as the eval harness's frozen A/B baseline —
  the dead-on-arrival `build()` wrappers in `kb_build`, the `Agents/experts/__init__.py` duplicate
  roster (single owner: `AVAILABLE_EXPERTS` in `mcp_server.py`), a leaked absolute worktree path in
  `rebuild_graph.py`, and the `ControllerManager`/`ModuleFactory` ceremony in the TD-side webserver
  script (collapsed to a direct controller call; disk-delivered, no `.tox` rebuild — live TD picks
  it up after the install tree fast-forwards and the webserver DAT reloads).
  `MCP/server_core/search/__init__.py` is reduced to a package marker, and the
  `docs/KNOWN_ISSUES.md` "connect in or remove" trio entry is resolved. Revived:
  `td_validate_expanded` is now launchable (`Tools/offline Builder tools/td_validate_expanded.py`)
  — it audits an expanded `.toe/.tox.dir` against its `.toc`, the integrity check the lossless
  parser silently swallows — with a README row and smoke test.

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
