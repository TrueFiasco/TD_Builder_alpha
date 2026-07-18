# Changelog

## Unreleased

### Added
- **`register_component` — register your own `.tox` components** (W7 user-components
  wave, PR #37). The 18th offline `td-builder` tool (offline surface **17 → 18**):
  registers user-authored `.tox` comps as searchable + buildable palette components
  via a prepare → author-summary → commit flow (`specs`/`directory`, `prepare`,
  `save_to_palette`, `folder`, `overwrite`, `confirm_shadow`), with incremental ingest
  into a per-user component store so first-party components are retrievable by KB search
  and usable by `td_build_project`. Also exposed as an offline CLI launcher. See
  `Tools/TOOLS.md` and `MCP/README.md`.

### Changed
- **W1 Honest Parsers** (defect board A1–A5 + KF1, remediation map ticket 10): the Δ7
  registration parsers no longer silently corrupt the parameter metadata the assistant
  builds from, and no KB consumer can create-on-open a stub vector store. (A1) the
  `.cparm`/`.parm` quote scanner understands TD's `\q` escapes — an escaped-quote default
  used to commit as a lone backslash with no warning (masterRadioMenu 'Menulabels'); the
  scanner is now single-sourced in `component_manifest.parm_quoted_fields` (the .cparm
  tokenizer binds to it). (A2) the `.parm` override seam re-splits quote-aware — a quoted
  constant with spaces used to commit truncated + quote-mangled (moviePlayer 'File'
  committed `"C:/Users/greg/Desktop/Media/VJ`); expression-preference (AM4) deliberately
  untouched. (A3) quoted multi-word page names ("Change Color", "X Units") are valid page
  candidates, and the degrade record carries `page` per spec. (A4) `_tail_rest_ok` parses
  the real tail grammar `[2 <menu-source-expr>] [<enable-expr>] [1 <help>]` — the leading
  2 is a MARKER, not a count; `tdu.ParMenu`/`op().par.x` dynamic menus (noise 'Format',
  masterRadioMenu 'Font'/'Value0') lost their whole par under the old exact-length
  reading. Unquoted literal `None` slot placeholders degrade loudly instead of committing
  the string 'None'. Measured across all 263 expanded shipped palette comps (9,134 pars):
  degraded pars 1,588 → 0, menu pars with tokens 1,091 → 1,418 (+327: 23% of real menu
  pars lost every token), verbatim menu tokens 16,025 → 21,298, warnings 1,671 → 149 (all
  honest loud degrades), ZERO pars lost anything they had before. (A5) a `palette` op's
  `parameters` are silently discarded by the builder while the Δ7 io-chunk text said to
  set them — the drop is now LOUD (build warning naming every dropped key, surfaced as
  `warnings` in both build-tool envelopes) and the chunk text routes value-setting to
  after the build; actually applying palette params stays future work (needs a live
  save+expand proof). (KF1) chromadb `PersistentClient` is create-if-missing at every
  one of the repo's 13 construction sites and holds the sqlite open read-write even for
  pure reads (filesystem RO attribute empirically refuted) — booting against an
  absent/empty store manufactured the ~188KB bare stub behind all 3 vector_db kills on
  the dev machine. New guard `search_docs.open_chroma_or_refuse` + stdlib read-only
  probes (`chroma_store_doc_count`, boot-side `mcp_server._vector_db_ro_doc_count`,
  mirroring `fetch_vector_db`'s contract) now front the server boot, `TDDocSearch`, the
  user-store read paths (`retrieval_stack`, `_open_user_collection(create=False)` — the
  latter also no longer mkdirs on read), and the four eval CLI probes; creators
  (ingest/reembed/user-store commit) keep creating. Guard test pins "opening a
  missing/empty store RAISES and creates NO file". New own-content fixture
  `quotefont.tox.dir` carries the real-TD shapes the old fixtures omitted (escaped
  quotes, multi-word quoted page, marker tail, expression-mode `.parm` override — board
  CM2), and `tests/engine/test_real_palette_parse.py` re-proves A1–A4 against the real
  TD 2025.32820 palette on machines that have it (skips elsewhere; nothing from the
  palette is committed).
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
- **User-store embedding-regime rewrite landmine** (ultra-audit A8/AN1 + board BM1;
  `kb_build/user_components.py`, remediation map ticket 04): `ingest_incremental`
  stamped the *current* KB regime into the store manifest unconditionally while
  re-upserting only the current call's components. After an embedding-regime change
  (a model re-pin, a normalize/query_prefix flip — the eventual KB re-embed), a single
  incremental re-commit would silently rewrite the manifest to the new regime and flip
  the boot guard (`retrieval_stack.py`'s three-field health check) from REFUSED back to
  ACCEPTED while every un-recommitted component kept **stale-regime vectors** — a store
  that reports healthy and returns geometrically wrong neighbours, invisible to every
  downstream check. **A8 fix (refuse-hard):** ingest now refuses a regime change
  *before any embed or write* — manifest byte-unchanged, zero upserts — with a message
  naming the runnable remedy. A regime change is authorised **only** for an explicit
  reindex (`allow_regime_change=True`) **and** only when the store holds zero vectors
  (the flag is independently verified against the store, never merely trusted); regime
  change is exclusively `reindex_all`'s job. `commit_specs` pre-checks under the lock so
  a refused commit never leaves the registry ahead of the store. **AN1:** `remove_component`
  now resolves the manifest regime all-or-nothing (preserve when complete, else the current
  regime as a unit) instead of pairing the stored `model_id` with a hardcoded
  `normalize=False`/`query_prefix=""` — no more synthesised mixed regime. **BM1:**
  `reindex_all` and `remove_component` — previously reachable only by hand-written Python
  importing a `kb_build` internal — now have a runnable surface via
  `kb_build/register_user_component.py --reindex-all` / `--remove NAME`, so the guard's
  refusal names a command that actually exists (and there is finally a supported
  un-register path). Red-first coverage: hermetic guard/AN1/CLI units
  (`tests/unit/test_regime_guard.py`) + end-to-end "silent-heal is dead" / authorised-reindex
  / remove-parity in the kb-full lane (`tests/retrieval_user/test_user_store.py`).
- **W2 Truth Surfaces — instruction-channel counts, labels, and paths regrounded**
  (defect-remediation map ticket 11). The numbers, labels, and paths the model reads
  now match reality: (1) the stale **`673` operator count** replaced with the **live-verified
  truth**, re-measured against TouchDesigner **099.2025.32820**'s own `families[]` registry:
  TD has **647** creatable operators (CHOP 165 · TOP 146 · SOP 112 · DAT 71 · COMP 40 ·
  MAT 13 · POP 100), and the KB documents **640** of them. `KB/operators.json`'s 663 entries
  are *not* a TD count — the set carries **23 fossils** (retired/renamed names such as
  `CUDA TOP`, `SVG TOP`, `Font SOP`, `Web DAT`, `Band EQ CHOP`) and is **missing 7** real ops
  (`textPOP`, `tracePOP`, `triangulatePOP`, `alembicoutPOP`, `tcpipDAT`, `freedinCHOP`,
  `stypeinCHOP`), so `663 − 23 + 7 = 647`. Instruction surfaces (the two `td_designer`
  prompts, the `td-builder-howto` and `td_network_analysis` SKILLs, root `README.md`,
  `DEMO_WALKTHROUGH.md`) now quote **647/640**; `eval/` internals keep **663** but say
  "KB entries", since that is the array the coverage code actually enumerates. The full
  census + fossil/hole lists are recorded in `eval/ground_truth/README.md`; reconciling the
  KB's *content* stays W3 Census Lock. The on-disk `metadata.total_operators: 673` is an
  untracked generated artifact whose writers already emit `len(operators)`, so a KB rebuild
  self-corrects it (no code change). (2) `eval/ground_truth/operator_types.json`
  relabeled honestly as a **wiki scrape with synthesized `td_create` tokens** — including
  5 never-real "phantom" POPs (Source/Attractor/Drag/Collision/Kill) — **not** a
  "live-TD capture", in its README and `eval/predicates.py`. (3) The `td_validate`
  pipeline's **"5-stage" name corrected to its real 7 stages** (adds `grounding` and
  `component-source`) across ~10 prompts/docs/CLI. (4) `MCP/README.md`'s offline
  enumeration now names all **18** tools (`register_component` was missing). (5) The
  retired standalone `tox_builder/builder.py` references updated to the current
  `MCP/server_core/meta_agentic/execution/tox_builder.py` in `docs/TOE_FORMAT_LEARNINGS.md`
  and two `Agents/expertise/*.yaml` files; the phantom `glsl_swarm.tox`
  `reference_implementation` dropped. (6) The dead `eval/build_gate/operator_ground_truth/`
  path claim corrected to the real untracked corpus at `New KB build/Resources/`, and
  `TD_USER_PALETTE_DIR` documented in `Config/SETTINGS.md`.
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
