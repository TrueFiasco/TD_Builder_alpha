# td-builder Eval Suite — Design Brief (v1, demo-ready)

## Context

`C:\TD_builder_alpha` is the `td-builder` v0.1.0-alpha MCP server: 37 tools
covering KB/retrieval, the 5-stage validator, format conversion, the offline
`.toe`/`.tox` builder, a live-TD bridge on `127.0.0.1:9981`, and an agentic
generation path (Mode 2). It has never had a real eval suite. A manual
acceptance checklist (`docs/ACCEPTANCE_TEST.md`) exists and is passing, but it
tells you "the surface works" — not "is it any good," not "did my change
improve anything," and not "where is it weakest."

This brief defines the eval suite that fills that gap. It is a **measurement
instrument** — every test emits a scalar score on a dataset, persists a
baseline, prints a ranked **worst-case backlog**, and reports the delta vs the
last baseline so the loop is *measure → change code → re-measure → keep the
baseline if better*. Pass/fail is not the model.

GLSL-in-TouchDesigner is the **headline focus area** because it's the highest-
value, hardest-to-fake capability (real shaders compile or they don't; real
renders happen or they don't), and we have a prior corpus (Dec 2024 "Dali"
basic_tests_1-10) to ground the failure catalogue. But the eval covers the
*whole* TD-builder surface, not only GLSL.

## Two operating modes

Calling these out at the top because they answer the most-asked question.

- **Mode 1 — Deterministic (no API key, no cost).** Measures KB recall,
  validator accuracy, format-conversion fidelity, offline builder parameter
  acceptance, live CRUD round-trip, live-TD diagnostics, fixed-input GLSL
  builds, error-message actionability. *This is the bulk of the eval.* Already
  runnable today via `tests/measure/`.
- **Mode 2 — Agentic (`ANTHROPIC_API_KEY` set, ~$0.05/case).** Adds
  evaluation of the system's *generation* capability: given a natural-language
  prompt, can the agent produce a correct network. Mode 2 is the *only* place
  where `fix_iterations` and `cost_usd` carry meaning, because that's the only
  place a self-correcting LLM loop runs.

Mode 1 stands alone — you can demo and improve the eval without ever setting
a key. Mode 2 layers on when you specifically want to measure agent quality
and efficiency.

## System under test — the 37 tools, organised

| surface | tools | measurable property |
|---|---|---|
| **KB / retrieval** | `hybrid_search`, `get_operator_info`, `query_graph`, `list_pop_operators`, `find_operator_examples`, `find_similar_networks`, `find_operator_combination`, `find_parameter_usage`, `get_parameter_detail`, `get_network_patterns` | recall@k, coverage %, MRR |
| **TD Python class docs** | `get_td_classes`, `get_td_class_details`, `get_td_module_help` | retrieval correctness on the Python class surface |
| **Validation** | `td_validate` (5-stage pipeline) | per-stage false-flag / miss rate on labelled good+bad corpus |
| **Format conversion** | `td_convert` | builder↔extended↔canonical round-trip field fidelity |
| **Offline build** | `td_build_project` (+ `NetworkBuilder`/`TOEBuilder` engine) | parameter-acceptance % vs `operator_ground_truth/` |
| **Expertise** | `get_expert_prompt`, `td_compact_expertise` | shape correctness, response cost |
| **Server identity** | `get_server_info` | contract correctness, token cost, actionability of errors |
| **Live-TD CRUD** | `create_td_node`, `update_td_node_parameters`, `delete_td_node`, `exec_node_method`, `execute_python_script` | P19-style round-trip; idempotent cleanup; project-unchanged guarantee |
| **Live-TD diagnostics** | `get_td_info`, `get_td_nodes`, `get_td_node_parameters`, `get_td_node_errors`, `get_cook_errors`, `get_python_exceptions`, `get_error_summary` | accuracy of returned state; graceful-fallback message quality when TD is down |
| **Live-TD capture** | `capture_top_output`, `capture_op_viewer`, `capture_network_layout`, `get_top_info` | image-non-empty, latency, metadata correctness |
| **Agentic (Mode 2)** | `spawn_engineer`, `spawn_expert` | generated-network quality (validity, operator/connection recall, fix_iterations, cost_usd) |
| **Cross-cutting** | every tool above | response tokens, latency p50/p95, error actionability, `compact=true` bloat delta |

## Scope — the test matrix

The eval is structured along these dimensions. Cases live as templated
prompts so one case spawns many variants via slot overrides.

| dimension | values |
|---|---|
| **section** | `knowledge` · `validation` · `conversion` · `build_offline` · `fix_offline` · `build_live` · `fix_live` · `live_crud` · `agentic_generation` · `full_creative` · *(pipeline — designed, post-v1)* |
| **focus area** | GLSL (headline) · POP/instancing · audio-reactive · render-graph · UI panels · data-conversion (DAT/CHOP/SOP/TOP) |
| **op (when applicable)** | GLSL TOP · GLSL Multi TOP · GLSL MAT · GLSL POP (+ Advanced/Copy/Select) · GLSL COMP · the 670 non-GLSL ops via the registry |
| **shader stage** | fragment · compute · vertex |
| **binding** *(GLSL)* | `vector_param` · `chop_array` · `texture_input` · `pop_buffer` · `feedback_buffer` |
| **driver** *(binding-aware data source)* | scalar CHOP · multi-sample CHOP · interactive Noise TOP · POP points · Feedback ping-pong |
| **render_fixture** *(GLSL MAT/POP)* | `closeup` · `instanced_far` · `from_scratch` |
| **difficulty** | easy · medium · hard · *full_creative tier* |

## Per-case architecture

```
prompt template
  -> slot fill (theme, driver, sim, bug, binding, stage, fixture)
  -> [Mode 2 only] agent generates network spec + shader code
  -> build to .tox offline    (or  create_td_node live)
  -> import the .tox into /test in live TD  (build_offline cases)
  -> capture errors:  GLSL compile + cook + python
  -> render the designated output TOP -> output.png
  -> compute composite score for the section
  -> log artifact folder + append row to review.md
  -> optional human_score column for spot-checks
```

## Marking criteria

### Per-section composite score (automated, deterministic)

| section | score = |
|---|---|
| `knowledge` | right op named + expected concepts/keywords in answer; recall@k where applicable |
| `validation` | per-stage classification correctness on labelled good+mutated corpus |
| `conversion` | round-trip field-fidelity % on a corpus |
| `build_offline` | built · imports at right level · `td_validate` clean · GLSL compiles · renders non-black · binding wired · `.parm` non-empty |
| `fix_offline` | validates · the specific `{bug}` class removed · still renders intent |
| `build_live` | built · right op · compiles 0 err · renders non-empty · binding wired |
| `fix_live` | error count → 0 · compiles · renders · project otherwise unchanged |
| `live_crud` | create→update→read-back→delete; final existence check; project unchanged |
| `agentic_generation` | operator/connection recall + validity of produced network |
| `full_creative` | composite across stages + integrated render + `.tox` import-at-level |

### Cross-cutting per case (every section)

`terminal_score` (the composite above) · `fix_iterations` (Mode 2 only;
self-repairs before final candidate) · `duration_s` · `cost_usd` (Mode 2
only; from `MetricsCollector`) · response tokens · latency · error
actionability · **`human_score`** *(optional override column)*.

### What we capture from TD itself

GLSL compile log (`get_td_node_errors`), cook errors (`get_cook_errors`),
python exceptions (`get_python_exceptions`), rendered output
(`capture_top_output`), structural validity (`td_validate` 5-stage), and
network state (`get_td_nodes` / `get_td_node_parameters`). Image-non-empty
via pixel-stat heuristic (mean luminance + variance).

## Reporting

- **Artifact folder per case** —
  `tests/results/<run>/<case_id>/{prompt.txt, network.json, errors.txt, output.png, case.json}`
- **`review.md`** — one table per run: every case, its auto-score, its
  metrics (fix_iterations / cost), blank `human_score` column, links to
  artifacts.
- **`baselines/<target>.json`** — promoted on `--promote` so the next run
  prints `delta = ...` and a ranked **worst-case backlog**.
- **Live TD project** — at run end, `/test/<case_id>/` is populated so one TD
  session contains every output for visual review.

## What's automated vs. where the human is in the loop

**Automated** — build invocation, import-at-level check, render capture,
GLSL compile pass/fail + error-class regex against the catalogue (`#version`,
`uniform redefinition`, `vec3 → vec2`, reserved-word), cook/python exceptions,
structural validity, operator/parameter existence vs. `OperatorRegistry`
(no hallucinated ops), binding-wired inspection, image-non-empty, retrieval-
relevance, fix-iteration count, cost & latency, defect-removed diff on fix
tasks, live-CRUD idempotent cleanup.

**Human in the loop — three tiers; pick what fits the day:**

1. **Calibrator + spot-checker** *(default)* — open `review.md` + the
   populated TD project at `/test/`; fill `human_score` for the cases you
   eyeball (typically `full_creative` + the worst N from the backlog). Flag
   where auto-score disagrees with reality.
2. **Case author** — edit `tests/glsl_eval/cases.yaml` slots/banks; swap
   themes (Dali → Picasso), drivers (LFO → audio RMS), sims (boids → cloth),
   bug-to-fix.
3. **Review-log keeper** *(milestone only)* — reproduce the structured
   `bug_report_basic_tests.md` per-case write-up.

**Things automation must NOT decide.** Whether a render *visually matches the
artistic intent* (optional multimodal judge can suggest; you sign off).
Architectural taste / idiomatic choice. Milestone pass/fail.

## Demo set — seven tests showing the breadth

D1–D4 are **already runnable today** via the existing `tests/measure/` suite
(Mode 1, no key). D5–D7 are the GLSL focus area; D5–D6 are Mode 1 once the
GLSL runner is wired; D7 is the Mode 2 headline.

| # | section / focus | case | mode | what it proves |
|---|---|---|---|---|
| **D1** | knowledge / retrieval | `hybrid_search` recall on sampled operators (existing `test_retrieval`) | 1 | the KB layer scores; current baseline ≈ 0.95 |
| **D2** | validation | `td_validate` on known-good + auto-mutated bad nets (existing `test_validator`) | 1 | per-stage classification; current baseline ≈ 0.67 |
| **D3** | offline build | builder param-acceptance vs `operator_ground_truth/` (existing `test_builder_params`) | 1 | the headline weakness — BASIC builder emits 0 params; current baseline **0.0** — the clearest improvement target |
| **D4** | live CRUD | P19-style create→update→read→delete on a Constant CHOP under `/test` | 1 | the live-TD path works; project unchanged afterwards |
| **D5** | GLSL · build_offline | `bo_glsl_top_theme_color` (theme=`sci-fi`) | 1 | minimal GLSL **build → import → render → score** end-to-end |
| **D6** | GLSL · fix_offline | `fo_glsl_fix_bug` (bug=`uniform_redefinition`) | 1 | fix-class scoring against a real catalogued GLSL error |
| **D7** | GLSL · full_creative | `fc_creative_av_scene` (theme=`dali_persistence`, driver=`audio_rms`) | 2 | the **headline** — revives the Dec-2024 Dali run; integrates GLSL TOP + MAT + audio; demonstrates `fix_iterations` + `cost_usd` + the worst-case backlog when the agent has to self-repair |

Together, D1–D7 exercise: KB, validator, conversion (implicit in D5/D7),
offline builder, live CRUD, GLSL build, GLSL fix-class, agentic generation
with cost accounting. That's the whole eval in one run.

## Implementation status (what exists, what's needed)

| component | status | path |
|---|---|---|
| In-process probe + cross-cutting metrics | **done** | `tests/measure/probe.py` |
| Baseline/delta/worst-case harness primitive | **done** | `tests/measure/harness.py` |
| Optional LLM rubric scorer (fuzzy targets) | **done** | `tests/measure/judge.py` |
| Builder param-acceptance target (D3) | **done, baseline promoted at 0.0** | `tests/measure/test_builder_params.py` |
| Retrieval recall target (D1) | **done, baseline promoted at 0.95** | `tests/measure/test_retrieval.py` |
| Validator accuracy target (D2) | **done, baseline promoted at 0.67** | `tests/measure/test_validator.py` |
| Crosscut tokens/latency/actionability | **done** | `tests/measure/test_crosscut.py` |
| Aggregate "everything at once" runner | **done** | `tests/measure/test_measure_all.py` |
| Live CRUD round-trip target (D4) | **done** | `tests/measure/test_live_crud.py` |
| GLSL eval runner (D5–D6) — build, import, render, error capture | **done** | `tests/glsl_eval/runner.py` |
| GLSL eval tests (D5/D6) | **done** | `tests/glsl_eval/test_glsl_demo.py` |
| Templated GLSL cases (11 seeds) | **done, draft** | `tests/glsl_eval/cases.yaml` |
| GLSL-eval review companion | **done** | `tests/glsl_eval/EVAL_REVIEW.md` |
| LLM-critique question generator | designed, planning prompt drafted | future |
| Pipeline tier (composed stage-toxes) | designed | post-v1 |
| Multimodal visual-intent judge | designed | post-v1, opt-in |

## Prereqs

- **TouchDesigner** running with `MCP/td-webserver/mcp_webserver_base.tox`
  imported (WebServer DAT on `127.0.0.1:9981`), `/test` base COMP empty at
  start. *Required for D4–D7.*
- **`ANTHROPIC_API_KEY`** — *only* needed for Mode 2 (D7). Everything else
  runs without it.
- **Interpreter**:
  `C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe`
  (the one with `mcp`, `chromadb`, `sentence-transformers`).
- `pip install -e ".[dev]"` — already configured in `pyproject.toml`.

## Out of scope for v1

- Multimodal visual-intent judge (opt-in stretch; offline pixel heuristic
  stands in).
- Pipeline tier (designed; one full_creative case carries the integration
  story for v1).
- LLM-critique question generator (planning prompt drafted; cases are
  hand-authored seeds for now).
- Broad sweep of `full_creative` (one case in v1 demo; growth later).

## Roadmap

1. **v1 demo (today)** — run D1–D6 (Mode 1); show D7 narrated or live if
   `ANTHROPIC_API_KEY` is available.
2. Iterate `cases.yaml` against the worst-case backlog.
3. Pipeline tier (1 case): full Dali AV pipeline as 3 composed `.tox`.
4. LLM-critique question generator (improve seeds, then expand).
5. Multimodal visual-intent judge (opt-in).
6. Cost/fix-iteration trend tracking across releases.

## Verification (how to validate the eval *itself*)

- D1–D4 already pass today; re-running them must reproduce the promoted
  baselines within tolerance.
- D5 against a LOSSLESS-mode build of a known shader must score ~1.0 (sanity
  floor); BASIC well below (the gap to improve — matches D3's signal).
- D6 against the seeded `uniform_redefinition` fixture must remove the exact
  error class before the test scores; introducing a new error fails the
  defect-removed check (catches "fixed the symptom not the cause").
- D7 wall-clock and `cost_usd` must agree with `MetricsCollector` to within
  rounding; `fix_iterations` must equal the count of
  `build_failure + validation_error + phase_reopen` events.

## How to run

```powershell
$PY = "C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe"
cd C:\TD_builder_alpha

# Mode 1 — everything offline-deterministic (no key)
& $PY -m pytest tests/measure -m "not mode2" -s                 # D1-D4
& $PY -m pytest tests/glsl_eval -m "not mode2" -s               # D5-D6

# The full demo, one command:
& $PY -m pytest tests/measure tests/glsl_eval -m "not mode2" -s

# Mode 2 (optional; needs key + costs ~$0.05/case)
$env:ANTHROPIC_API_KEY = "sk-..."
& $PY -m pytest tests/glsl_eval -m mode2 -s                     # D7

# Promote new numbers as baselines only when a change improved them
& $PY -m pytest tests/measure tests/glsl_eval -s --promote
```
