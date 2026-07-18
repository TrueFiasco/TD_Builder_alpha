# Changelog

## Unreleased

### Added
- **W3 Census Lock — the operator ground truth is now the live TouchDesigner
  census, by construction** (defect board GT1/GT5/GT7 + ND1, remediation map
  ticket 12). `eval/ground_truth/operator_types.json` was a **wiki scrape** that
  was wrong in *both* directions: it invented **13 operators that have never
  existed** (the known `Source/Attractor/Drag/Collision/Kill_POP` plus eight the
  census surfaced — `Add_POP`, `Velocity_POP`, `Analyze_DAT`, `Fuse_SOP`,
  `Mirror_SOP`, `Normals_SOP`, `Scatter_SOP`, `Gradient_TOP`), omitted **7 real
  ones**, carried **6 tutorial articles** (`Write_a_*`) as operators, and
  double-counted `FIFO_DAT`/`Fifo_DAT` — which is why its header said 685 while
  it held 684 distinct tokens. The harm was not a retrieval miss: a model asked
  to receive FreeD camera-tracking data found the retired `FreeD CHOP`, tried it,
  and got a node that would not create, while the operator that does the job
  (`freedinCHOP`) was invisible to it.
  The operator SET now comes from TouchDesigner's own `families[]` registry, so
  the ground truth is a **subset of reality by construction** — there is no step
  left that could invent an operator. New `scripts/capture_td_census.py` commits
  a versioned census snapshot (`eval/ground_truth/td_census.json`, 647 operators
  @ `099.2025.32820`, build id **inside** the JSON, plus each operator's
  inheritance chain); new `kb_build/gen_operator_types.py` joins it to
  TouchDesigner's shipped offline-help operator pages for display names and
  **aborts rather than synthesising** a name it cannot find. Neither script
  carries a TouchDesigner version: the capture records `app.installFolder` /
  `app.samplesFolder` from the running instance and the generator resolves the
  docs tree from the census, so **a TD upgrade is a re-invocation, not a code
  edit** (a test fails if a versioned path reappears in either file, and
  `provenance.help_tree_resolved_from` records which of the three resolution
  paths won). Receipts: capture
  647 = CHOP 165 / TOP 146 / SOP 112 / DAT 71 / COMP 40 / MAT 13 / POP 100; name
  join 647/647 with 0 unmatched and 0 ambiguous; diff `684 − 44 + 7 = 647`
  decomposing exactly into 13 phantoms + 6 guide pages + 21 fossils + 2 renames +
  the malformed `art-netDAT` + the legacy `geoCOMP`, with all 7 name changes
  norm-invariant and 0 family reassignments.
- **Mechanical census drift guard in CI** (board GT7). Today's drift — KB 663,
  eval 685, live TD 647 — was found **by hand**, in an audit; nothing was red.
  `scripts/census_guard.py` adds five checks over the committed snapshot:
  identity/self-consistency, per-family pins, census↔KB reconciliation **in both
  directions** (census−KB bounded by 7 named holes, KB−census exactly the 23
  named fossils — a fossil quietly vanishing is drift too), eval-GT ⊆ census, and
  count truth for all three numbers. Both allowlists carry **anti-rot** checks so
  they cannot accumulate dead entries. The red-green demonstration lives in CI
  rather than in a transcript: the negatives deepcopy the snapshot, mutate one
  thing, and assert the **specific** finding text, and `--self-test` reproduces
  the whole thing in memory with one command (6/6 mutations red, pristine
  snapshot green, doctored file → exit 1 with 4 findings). `scripts/docs_lint.py`
  gains an operator-count rule that pins the **phrase shape** rather than bare
  numbers — 647/640/663 are all legitimate in context, and a proximity rule would
  also fire on `636/636 operator tokens` and `Sweet 16 operators`; measured
  against all 56 scannable files it matches exactly the 5 real claims with zero
  false positives.
- **`register_component` — register your own `.tox` components** (W7 user-components
  wave, PR #37). The 18th offline `td-builder` tool (offline surface **17 → 18**):
  registers user-authored `.tox` comps as searchable + buildable palette components
  via a prepare → author-summary → commit flow (`specs`/`directory`, `prepare`,
  `save_to_palette`, `folder`, `overwrite`, `confirm_shadow`), with incremental ingest
  into a per-user component store so first-party components are retrievable by KB search
  and usable by `td_build_project`. Also exposed as an offline CLI launcher. See
  `Tools/TOOLS.md` and `MCP/README.md`.

### Changed
- **CI collection floors raised to measured actuals** (W3 Census Lock): hermetic
  **431 → 559**, engine-kb **581 → 728**. Itemised: the pre-wave actuals on
  `4f17520` were already 468/623, so **+37/+42 was drift** that landed with
  PR #49/#50 and the floors had not caught up; **+91/+105 is this wave** (91
  hermetic census/guard/backfill/expertise tests, plus the 14 `requires_kb` guard
  tests which only the engine-kb lane collects). Raising a floor is routine per
  `docs/CI.md`; the pre-existing drift is disclosed rather than folded silently
  into the new number.
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
- **`python_class` backfilled from the census; 24 wrong values repaired**
  (board GT5). 164 of 663 KB operators carried no `python_class`, 73 of them
  POPs — never a fact about TouchDesigner, since every one of those operators
  HAS a class. It was a mirror artifact: the KB harvested class names from
  offline-help **class pages**, and that mirror ships under half the pages it
  references (1,442 `*_Class` names referenced, 656 shipped; 104 of the missing
  are POP classes). Nulls **164 → 14**, the remaining 14 being exactly the
  fossils, which stay null because a non-creatable operator has no class to
  derive. The 24 populated-but-wrong values were arbitrated by **instantiating
  each operator in live TouchDesigner** and reading `type(n).__name__` — all 24
  returned `type(n).__name__ == OPType == n.OPType` with the family matching.
  That method mattered: for `Alembic In POP` the offline-help page title
  `alembicPOP Class` **contradicts** the live class `alembicinPOP`, so
  documentation would have talked us into keeping the wrong value. The rest were
  wiki-parse debris (`'send MIDI messages'`, `'points'`, `'Par'`,
  `'<code>.sendOSC()</code>'`, `PanelCOMP_Class` on a DAT). Overwrites are
  allowlist-gated, so a future operator whose class genuinely diverges from its
  OPType is **reported, not clobbered**. NOTE `KB/operators.json` is generated
  and untracked, so this ships a source-side derivation; it reaches the artifact
  at W7c's rebuild.
- **The ground truth had two copies and CI read a different one than you did**
  (board GT1 follow-on). `eval/ground_truth/operator_types.json` is tracked, but
  every local default resolved a byte-identical untracked twin in the main-tree
  corpus while CI passed the tracked file explicitly. They agreed only by being
  identical — regenerating either would have made local eval runs and CI grade
  against different ground truth with nothing red. Every resolver now prefers the
  tracked file via `paths.operator_types_path()`, including `kb_build/common.py`,
  a reader nobody had flagged and the one that feeds create-token resolution.
  `params/` and `tox_expanded/` still resolve from the corpus (they are live-TD
  captures, ~31 MB); the trap where `tool_coverage.py` derived
  `params_dir = gt_types.parent/"params"` is closed, since that would now point
  at a directory which does not exist.
- **Fabricated operators removed from the agent-facing expertise YAML**
  (board GT1 follow-on; prompt-side, unchunked, so no re-embed). Dropped 7
  invented POP entries from `Agents/expertise/td_operators.yaml` (the
  `python_class: ''` giveaway) and deleted the `particle_system` design pattern
  from `td_network_patterns.yaml`, whose **four** operator types and container do
  not exist — it shipped a guaranteed-to-fail network at `confidence: 0.8`. Not
  repaired: inventing a replacement repeats the original sin. The new
  creatability test then caught four more wrong tokens in unrelated patterns, so
  **5** design patterns were unbuildable rather than 1; those are repaired as
  spellings of operators that do exist (`geoCOMP` → `geometryCOMP`,
  `choptosopSOP` → `choptoSOP`, `sliderCHOP`/`buttonCHOP` →
  `sliderCOMP`/`buttonCOMP`).
- **`eval/agent_eval` documented the validation pipeline as 5 stages; it has 7**
  (board ND1). Re-verified at fix time — `MCP/engine/validation/pipeline.py`
  appends 7. Three different numbers were in circulation, so the sweep is
  deliberately not uniform: four present-tense "5-stage" claims and
  `baseline.json`'s "current main runs 6 stages" are corrected to 7, while
  `identity.py`'s and `README.md`'s "s01-s09 on a 4-stage pipeline, s10-s14 on a
  6-stage one" are **left as history** and annotated — rewriting them to 7 would
  replace one false statement with another. The pipeline's `2.5`/`3.5` stage
  labels are why the count keeps being under-read. `mcp_server.py:1600` still
  says 5-stage and is left for W4, whose slot that file is.
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
