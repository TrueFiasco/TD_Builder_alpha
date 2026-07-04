# CI — lane matrix, floors, and the build-gate disposition

Stood up by harness remediation **W1** (2026-07-04, design owner-approved).
Workflows: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (every
PR/push to `main`) and [`.github/workflows/kb-full.yml`](../.github/workflows/kb-full.yml)
(nightly 03:17 UTC + `workflow_dispatch`). Hosted runners only — **no
self-hosted** (pre-CLA public-PR RCE risk).

## Lane matrix

| Job | Trigger | Runner | Deps | KB | Runs | Gate |
|---|---|---|---|---|---|---|
| `docs-lint` | PR + push | ubuntu | none (stdlib) | – | `python scripts/docs_lint.py` | exit code |
| `hermetic` | PR + push | ubuntu **+** windows | `.github/requirements-light.txt` | **absent** (guard step enforces) | `pytest tests/engine tests/unit -m "not requires_kb" -q` | 0 failures + collection floor **53** |
| `engine-kb` | PR + push | windows | same light list | cached release fetch | `pytest tests/engine tests/unit -q` | 0 failures + collection floor **143** |
| `kb-full` | nightly + dispatch | windows | full `pip install ".[dev]"` | cached release fetch + HF model cache | acceptance+measure, then retrieval eval vs committed baseline | 0 failures + pass floor **22**; `scripts/ci_compare_eval.py` exit code |

**Runner rationale.** The repo is public (hosted minutes are free), so the
trade is fidelity vs queue time. Local truth is **Windows py3.11**, and the
committed `eval/baseline.json` numbers were measured on Windows — every
KB-touching lane runs `windows-latest`. The hermetic lane adds `ubuntu-latest`
as a fast canary for POSIX path regressions (the codebase is pathlib-only).
Python 3.11 only; a 3.13 forward-probe leg is a possible later addition, not
built (non-blocking jobs train ignored-red habits).

**Light deps as an import-hygiene canary.** `hermetic` and `engine-kb`
deliberately install `.github/requirements-light.txt` (pyproject minus
`sentence-transformers`/`chromadb`) instead of `pip install .`. W1's rehearsal
proved **all 143** engine+unit tests pass without the ML stack — if
engine/builder code ever grows a heavy import, these lanes go red. That
extends W0's de-hostage guarantee into CI. Corollary: a **new light
dependency added to pyproject must also be added to requirements-light.txt**
(drift fails loud as an ImportError in CI, never silent).

## Test partition (`requires_kb`)

Two mechanisms, both required:

1. `tests/conftest.py::pytest_collection_modifyitems` auto-marks any test
   using the `server`/`probe`/`live_server`/`live_probe` fixtures (the
   `server` fixture fails loudly without `KB/operators.json`).
2. Module-level `pytestmark = pytest.mark.requires_kb` in the 14 test files
   that read KB artifacts **directly** (offline `ToxBuilder`/
   `ToeBuilderBridge` builds resolve types against `KB/operators.json` at
   build time — fixture inspection cannot see that).

Enforcement is physical, not honor-system: the hermetic runner **has no
fetched KB and no ML deps**, so a mismarked test fails there loudly; it cannot
silently pass. Measured partition (2026-07-04, condition-2 reconciliation):
`tests/engine + tests/unit` collect **143** tests = **53 hermetic**
(9 engine + 44 unit) + **90 requires_kb**.

## Floors (silent-shrink guards)

| Floor | Value | Measured by | Meaning |
|---|---|---|---|
| hermetic collection | ≥ 53 | W1 rehearsal (53 passed, 90 deselected, light venv, no KB) | deselection can't quietly eat the lane |
| engine-kb collection | ≥ 143 | W1 rehearsal (143 passed in light venv, KB present) | whole engine+unit surface stays collected |
| kb-full acceptance passes | ≥ 22 | W1 rehearsal with TD down: **22 passed, 4 skipped, 0 failed** (26/26 with live TD locally) | live tests may skip; offline coverage may not shrink |

Raising a floor when tests are added is routine; **lowering one requires the
same review as changing a baseline** — say why in the PR, with receipts.
Failures are always loud regardless of floors (pytest exit codes gate first).

## KB caching

Both KB lanes restore **exactly the fetched artifacts** (the release-zip
contents list from `scripts/vector_db_release.json`) via `actions/cache`,
keyed `kb-v1-${{ hashFiles('scripts/vector_db_release.json') }}` — the pinned
sha256 lives in that file, so publishing a new KB release rotates the key
automatically. Never cache the whole `KB/` directory: tracked KB files
(`palette_components.json`, `docked_dats.json`, `manifest.json`) must come
from the checkout, or a stale cache could shadow a committed registry change.

On cache miss, `python scripts/fetch_vector_db.py` downloads the public
release asset and **sha256-verifies before extracting**; on cache hit its
idempotency probe skips the download. **Trust note: cache-hit content is not
re-verified** — it originated from a verified fetch, but nothing re-checks it
at restore or load time. Work item **2d** (pickle/load-time trust boundary:
`retrieval_stack.py` bm25.pkl, `enhanced_graph_query.py` gpickle) closes that
residual when it lands.

The kb-full lane additionally caches `~/.cache/huggingface`: the MiniLM query
encoder downloads from HuggingFace on the first run only (the cross-encoder
reranker ships inside the KB at `KB/models/`). A HF outage only hurts a cold
cache — loud, healed on the next run.

## Retrieval-eval gate (kb-full)

`run_eval.py` has no pass/fail semantics of its own. **W2c fixed the
baseline-overwrite wart**: `--out` no longer defaults onto the committed
`eval/baseline.json` (writing it is now the explicit `--write-baseline` opt-in),
so the `--out`/`--stage-dir` redirect + `git status` guard below are now
belt-and-braces rather than load-bearing. The lane therefore:

1. runs `python eval/run_eval.py --backend enhanced --repeats 3` (median of 3
   subprocess trials) with `--out`/`--stage-dir` pointed at `$RUNNER_TEMP` —
   zero repo writes, enforced by a `git status --porcelain` guard step;
2. passes `--gt-types eval/ground_truth/operator_types.json` — the
   name-integrity gate **hard-requires** that file (`eval/predicates.py`
   `GroundTruth.__init__` reads it unconditionally) and its default path is
   the untracked main-tree corpus, absent on CI. See
   [`eval/ground_truth/README.md`](../eval/ground_truth/README.md) for
   provenance: the main-tree corpus stays authoritative; the committed file is
   a pinned snapshot (TD build `0.99.2025.32460`);
3. gates with `python scripts/ci_compare_eval.py eval/baseline.json
   <candidate>`: aggregate recall@5/MRR/nDCG@10 may drop ≤ **0.02**,
   per-category metrics ≤ **0.05** (one flipped query in an n=12 category
   moves recall by 0.083), name-integrity violation counts and negative-query
   abstention are **strict** (no worse than committed). Rationale and the
   knobs live at the top of that script; the committed baseline's
   median-of-3 band is degenerate (deterministic capture), so the tolerances
   are pure headroom for runner-vs-local float drift.

## Build-gate disposition (owner-approved 2026-07-04): local pre-merge invariant

The three considered options were (a) publish the ground-truth corpus as a CI
artifact, (b) commit a minimal subset, (c) keep the full gate local.
**Decision: (c)** — because the gate is TD-bound, not corpus-bound:

> Track A shells out to TouchDesigner's own binaries per operator:
> [`eval/build_gate/track_a_offline.py:146-147`](../eval/build_gate/track_a_offline.py)
> runs `subprocess.run([str(toeexpand), str(tox_copy)], ...)`, and its
> docstring ([`:5-10`](../eval/build_gate/track_a_offline.py)) defines the
> round-trip as "collapse to a real `.tox`, expand it with TD's REAL
> `toeexpand`" — the collapse step needs TD's `toecollapse` the same way
> (`build_and_expand`, [`:114-156`](../eval/build_gate/track_a_offline.py)).

TouchDesigner cannot be installed on hosted runners and self-hosted runners
are banned pre-CLA, so **publishing the ~31 MB corpus buys zero CI capability**
while adding a Derivative-permission exposure and per-TD-pin re-publication
churn. Therefore:

- The full gate (`py -3.11 eval/build_gate/track_a_offline.py --all` +
  `build_gate.py`; thresholds token-exact ≥ 0.97 / offline pass ≥ 0.90 /
  live ≥ 0.95) **remains a local pre-merge invariant for builder-touching
  changes** — it is item 3 of the program's standing invariants.
- **Risks, stated:** it relies on merge discipline; there is no automated
  backstop between local runs. Mitigations: the `engine-kb` lane exercises
  the builders' KB-grounded paths on every PR (coarse but automatic), and the
  gate stays in the merge checklist of every wave brief.
- **Narrow rider:** `eval/ground_truth/operator_types.json` (60 KB) is
  committed **for the eval lane's name-integrity input, not for the build
  gate** — owner sign-off 2026-07-04; it is a strict subset of the already
  published release `operators.json`.
- **Revisit trigger:** CLA landing *plus* a TD-licensable headless runner
  story. Until both, the disposition stands.

## TD-dependence and CI (what skips where)

`paths.resolve_td_tool()` returns `None` when TouchDesigner is absent, and
the TD-bound tests carry explicit guards (`tests/engine/test_build_mode.py`
was written anticipating "a TD-free CI lane"). On hosted runners the 5
`skipif`-guarded tests (`test_external_tox_manifest.py` ×3,
`test_register_user_component.py` ×2) skip, plus in-test collapse assertions
in `test_build_mode.py`/`test_import_isolation.py` downgrade gracefully.
W1's local rehearsal ran with TD installed (143 passed, superset behavior);
**the skip variant is confirmed at bring-up** (below). Acceptance P13/P14 are
collapse-tolerant by design (no-error-envelope + pre-collapse `.dir`
assertions); the live-tool tests (P10/P16–P19) *pass* on graceful degradation
when TD is down — measured locally: 22 passed / 4 skipped (the skips are
`test_live_auth.py`, which needs the live server).

## §Bring-up (post-push; owner/orchestrator — workflows only execute on origin)

1. Push `main` (workflows land) → the `push` run of **CI** must go green.
2. Open a **no-op PR** (whitespace/docs touch) → all three CI jobs green.
3. Open the **seeded PR** (see the W1 report's seeded-failure transcripts for
   the exact seeds: a builder break + a docs "18 tools" edit) → `hermetic`,
   `engine-kb` and `docs-lint` must all go **red**. Close without merging.
4. `gh workflow run kb-full.yml` on `main` → green. First run is the cold-
   cache run (KB download ~122 MB + MiniLM download); verify caches saved.
5. `gh workflow run kb-full.yml --ref <seeded-branch>` → **red** (dispatch on
   a non-default ref is this lane's seeded-failure vehicle).
6. Confirm the engine-kb run shows the expected TD-absent skip pattern
   (~138 passed / 5 skipped) and the kb-full acceptance floor holds at 22.
   If a runner-specific skip is discovered and judged legitimate, tune the
   floor **with receipts** in the tuning commit.

Until step 1 happens, everything above is proven only by local rehearsal
(same commands, same env shape); the Actions plumbing itself — cache
save/restore, runner images, the HF download — is the unproven remainder.

## Extension points (documented, deliberately not built)

- **Agent-eval Lane R** (work item 2c, `eval/agent_eval/`): **LANDED** — runs in
  `kb-full.yml` as a follow-on step (`--lane replay`), advisory
  (`continue-on-error: true`) at bring-up, key-free and deterministic. Promotion
  to blocking is a documented one-line flip once green twice; see
  `eval/agent_eval/README.md` "CI placement & promotion path". Lane M
  (model-in-the-loop) stays out of CI by design (D-F). No `ANTHROPIC_API_KEY`
  secret is needed — Lane R uses no key, and Lane M runs on the maintainer
  machine on the subscription.
- **3b drift lint:** the non-negotiables section of
  `scripts/docs_lint_rules.json` ships with severity `off` entries naming
  today's duplicated MUST/NEVER rules; 3b single-sources them and flips
  severities — no lint-code change needed.
- **2c run_eval fix:** **LANDED** — `--out` no longer defaults onto the committed
  baseline (`--write-baseline` is the explicit opt-in); the kb-full redirect keeps
  working and is now belt-and-braces rather than load-bearing.
