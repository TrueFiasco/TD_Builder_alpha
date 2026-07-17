# Changelog

## Unreleased

### Changed
- **Agent-eval W7 re-bless** (v0.2.1 precondition B; defect-remediation map ticket 01):
  the committed `eval/agent_eval/baseline.json` now carries the **18-tool** offline
  identity (`register_component`, PR #37), clearing the Lane R `--compare` / nightly
  kb-full refusal on `tool_inventory_hash` 17→18. Partial n=5 recapture (MERGES with
  the prior baseline per PR #44) of **s05/s09/s10** (re-sampled + re-blessed, the
  documented W7 command) and **s19–s21** (stats-only — their PR #37-era 18-tool traces
  and the queued `review/` registration ledger are left intact; the rider only owes
  them the baseline numbers gate membership is earned from). The other **11** scenarios
  are reused verbatim, with the reuse + identity drift disclosed in
  `_provenance.partial_recapture_model-20260717-232224`. All 30 model trials PASS,
  spend **$7.14**; **gate set 7→11** (s09 promoted 0.6→5/5; s19/s20/s21 earned at n/n).
  `scenario_set_version` 1.0.0→1.1.0. New **`user_store`** hard-identity field
  (decision ⑥): `"absent"` for a hermetic (pinned-empty) run, else a content sha —
  a dirty user store now refuses `--compare` instead of silently measuring KB ∪
  user-store under a KB-only identity (`eval/agent_eval/tests/test_user_store_identity.py`).
  Also folds in the Δ6c sanctioned-reuse README note; the stale s18 `_provenance`
  sentence was already corrected upstream (PR #42).
- **CI test-hardening** (2026-07-16 integrity-audit backlog + owner's P19 directive):
  collection floors raised to measured actuals (hermetic 93→431, engine-kb 195→581 —
  frozen since W3b while the suites quadrupled; docs/CI.md's tables were staler still at
  87/185); the two orphaned suites now run in lanes (`tests/test_feedback_spine.py` →
  `tests/unit/` so the PR lanes collect its 38 tests structurally; `tests/retrieval_user`
  — the W7 server round-trip coverage that ran in NO lane while the 40-defect W7 cluster
  shipped — is now a hard kb-full gate with pass floor 12); the `requires_kb` automark
  narrowed to `server`/`probe` (the live fixtures import no KB artifacts); P19's live-CRUD
  branch is explicit opt-in (`TD_ACCEPT_LIVE=1`) and runs in a throwaway uuid-named
  sandbox container with teardown in `finally` — a reachable :9981 is no longer treated
  as consent to mutate the open project.
- **Single-source hygiene bundle** (architecture-review candidate 9, owner-directed): four
  facts that had to agree in N places, previously held together by comments, now have seams
  or enforcement tests. (1) **Root resolution**: `mcp_server.py` and `config/__init__.py`
  import `REPO_ROOT`/`KB_ROOT` from `paths.py` instead of re-deriving them with private
  `parents[N]` walks (the `param_name_resolver` `parents[3]` bug's failure shape); drift
  pinned KB-free in `tests/engine/test_root_resolution.py` (runtime equality for config,
  AST guard + layout assertion for the server; `TD_BUILDER_ROOT` is now read in exactly one
  place among the server root resolvers — mcp_server/config; two pre-existing readers
  remain in `feedback.py`/`server_instructions.py`, tracked for a follow-up). (2) **Auth constants**: the `TD_API_TOKEN`/`TD_API_TOKEN_FILE` + default-token-path
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
- **Acceptance probe blind to the live client's error strings**
  (`tests/measure/probe.py`): `"TD Error: …"`, `"TD Error (401): …"`, `"Failed: …"` and
  `"Failed to get X: …"` all scored `ok=True`, so `assert r.ok` was toothless against
  them. The classifier now flags those prefixes; the fix immediately exposed P17 passing
  vacuously against a TD project lacking `/project1/out1` (now an explicit skip), and
  `test_live_auth.py`'s docstring no longer documents the 401-blindness as current fact.
- **Truncated KB downloads now say so** (`scripts/fetch_vector_db.py`): the zip size is
  checked against the manifest's `size_mb` before hashing, so a partial download reports
  "truncated/partial download — delete and retry" instead of a SHA256 mismatch that reads
  as tampering (bit us twice on 2026-07-16, and again — caught by the new check — during
  this change's verification).
- **Empty-vector-store skip trap** (`tests/retrieval_user/test_user_store.py`): the module
  gate probes the `td_unified` collection's doc count (same read-only sqlite probe as
  `scripts/check_deps.py`) instead of `vector_db/` dir existence — a present-but-empty
  store (the chromadb create-on-open stub trap) now skips with an accurate reason instead
  of erroring inside the fixtures, and trips the kb-full pass floor instead of vanishing.
- **`live_server` fixture masked import regressions as skips** (`tests/conftest.py`): only
  a missing third-party dependency skips now; a first-party module failing to import, or
  any other load error, fails loudly (matching the offline `server` fixture's posture).
- **Stale tool-count comments** in `MCP/live_server.py` ("21 tools") and
  `MCP/live_client/td_live_client.py` (section headers 7/12/13): actual is 22 = 8
  visual-feedback + 14 CRUD/session.
- **Nightly kb-full lane restored** (`.github/workflows/kb-full.yml`, `eval/agent_eval/tests/test_scorer.py`):
  the three artifact-collapse scorer self-tests now self-skip on TD-free machines (hosted runners have no
  `toecollapse`, so the scorer step failed on every scheduled run since 2026-07-05 and silently suppressed
  Lane R — the replay gate, including its `--compare`, never executed on the schedule); Lane R now runs
  under `if: ${{ !cancelled() }}` so a red scorer step can never suppress it again.
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
- **Two MCP servers** instead of one: `td-builder` (offline, **16 key-free tools**) and
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
