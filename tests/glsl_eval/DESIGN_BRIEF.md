# GLSL Eval Suite — Design Brief (v1, demo-ready)

## 1. Purpose

Measure and improve the **td-builder** system's ability to generate, debug,
build, and integrate **GLSL networks in TouchDesigner**.

This is a **measurement instrument**, not a pass/fail gate. Every run produces
a per-case score, a stored baseline, a delta vs the last run, and a ranked
**worst-case backlog** so a code change can be evaluated by *did the number
move, and where is it still weakest*.

## 2. System under test

- `td-builder` MCP server at `C:\TD_builder_alpha` (37 tools).
- The **agentic generation path** (`spawn_expert` / V2 strategy runner —
  Mode 2, requires `ANTHROPIC_API_KEY`).
- The **offline builder** (`NetworkBuilder` → `.tox`).
- The **live-TD bridge** on `127.0.0.1:9981` (`mcp_webserver_base.tox`).
- The KB / retrieval surface.

## 3. Scope — the test matrix

GLSL is the **focus**, not a quota. The matrix:

| dimension | values |
|---|---|
| **section** | `knowledge` · `build_offline` · `fix_offline` · `build_live` · `fix_live` · `full_creative` · *(pipeline — designed, not in v1 demo)* |
| **op** | GLSL TOP · GLSL Multi TOP · GLSL MAT · GLSL POP (+ Advanced/Copy/Select) · GLSL COMP |
| **shader stage** | fragment · compute · vertex |
| **binding** | `vector_param` · `chop_array` · `texture_input` · `pop_buffer` · `feedback_buffer` |
| **driver** *(binding-aware data source)* | scalar CHOP · multi-sample CHOP · interactive Noise TOP · POP points · Feedback ping-pong |
| **render_fixture** *(MAT/POP)* | `closeup` · `instanced_far` · `from_scratch` |
| **difficulty** | easy · medium · hard · *full_creative tier* |

## 4. Architecture — the per-case loop

```
prompt template
  -> slot fill (theme, driver, sim, bug, binding, stage, fixture)
  -> agent generates network spec + shader code
  -> build to .tox offline   (OR  create_td_node live)
  -> import .tox into /test in live TD
  -> capture errors:  GLSL compile + cook + python
  -> render output TOP -> output.png
  -> compute composite score (section-specific)
  -> log artifact folder + append row to review.md
  -> optional human_score column for spot-checks
```

Templated cases live in [`tests/glsl_eval/cases.yaml`](cases.yaml). The
execution + scoring + baseline/delta/worst-case primitive already exists at
[`tests/measure/`](../measure/) (`probe.py`, `harness.py`, `judge.py`).

## 5. Marking criteria (automated, deterministic)

### Per-section composite score

| section | score = signals |
|---|---|
| `knowledge` | right operator named + expected concepts/keywords present in answer |
| `build_offline` | built · imports at right level · `td_validate` clean · GLSL compiles · renders non-black · binding wired · `.parm` non-empty |
| `fix_offline` | validates · the specific `{bug}` class removed · still renders intent |
| `build_live` | built · right op · compiles 0 err · renders non-empty · binding wired |
| `fix_live` | error count → 0 · compiles · renders · project otherwise unchanged |
| `full_creative` | composite across stages + integrated render + `.tox` import-at-level |

### Cross-cutting per case (alongside `terminal_score`)

`fix_iterations` (self-repairs before final candidate) ·
`duration_s` · `cost_usd` (from `MetricsCollector`) ·
**`human_score`** *(optional, your column)*.

### What we capture from TD itself

GLSL compile log (`get_td_node_errors`), cook errors (`get_cook_errors`),
python exceptions (`get_python_exceptions`), rendered output
(`capture_top_output`), and structural validity (`td_validate` 5-stage).
Image non-empty via pixel-stat heuristic (mean luminance + variance).

## 6. What's automated vs. where the human is in the loop

**Automated.** Build invocation, import-at-level check, render capture, GLSL
compile pass/fail + error-class regex, structural validity, operator
existence vs. OperatorRegistry (no hallucinated ops), binding-wired
inspection, image-non-empty, retrieval-relevance, fix-iteration count, cost
& latency, defect-removed check on fix tasks.

**Human in the loop — three role tiers, pick what fits the day:**

1. **Calibrator + spot-checker** *(default)* — review the auto-generated
   `review.md` + open the populated `/test` in TD; fill `human_score` only
   for the cases you eyeball (usually the `full_creative` and the worst N
   from the backlog). Flag where auto-score disagrees with reality — those
   notes tighten future auto-scoring.
2. **Case author** — edit `cases.yaml` slots/banks; swap themes (Dali →
   Picasso), drivers (LFO → audio RMS), sims (boids → cloth), bug-to-fix.
3. **Review-log keeper** *(milestone only)* — reproduce the structured
   `bug_report_basic_tests.md` per-case write-up.

**Things automation should NOT decide for you.** Whether a render *visually
matches the artistic intent* (an optional multimodal judge can suggest;
human signs off). Architectural taste / idiomatic choice. Milestone
pass/fail.

## 7. Reporting

- **Per-case artifact folder**:
  ```
  glsl_eval/<run>/<case_id>/
    prompt.txt        the filled, concrete prompt
    network.json      what the system built
    errors.txt        GLSL compile + cook + python errors (empty = clean)
    output.png        the rendered TOP
    case.json         scores + metrics + provenance + slot choices
  ```
- **`review.md`** — one table per run: every case, its auto-score, its
  metrics (fix_iterations / cost), a blank `human_score` column, links to
  artifacts.
- **`baselines/<target>.json`** — promoted on `--promote` so the next run
  prints `delta=...` and a ranked **worst-case backlog**.
- **Live TD project** — at run end, `/test/<case_id>` is populated so a
  single TD session contains every output for visual review.

## 8. Demo set — five specific tests to show

A tight cross-section of the matrix. Each was chosen for what it *proves*
about the eval.

| # | case id | section | difficulty | what it demonstrates |
|---|---|---|---|---|
| **D1** | `kn_glsl_stage_roles` | knowledge | easy | sanity floor: retrieval/knowledge-layer scoring (instant; if this regresses, the KB is broken) |
| **D2** | `bo_glsl_top_theme_color` *(theme=`sci-fi`)* | build_offline | easy | the **end-to-end loop in miniature**: agent → build → import → render → score; should pass cleanly |
| **D3** | `bo_glsl_top_chop_array_lut` *(driver=`chop_multisample`, theme=`horror`)* | build_offline | medium | **binding-aware drivers** — a multi-sample CHOP drives a `chop_array` uniform; tests the array-binding path |
| **D4** | `fo_glsl_fix_bug` *(bug=`uniform_redefinition`)* | fix_offline | medium | **fix-task scoring** — repair a real catalogued GLSL error; verifies the error class is gone, not just "it builds" |
| **D5** | `fc_creative_av_scene` *(theme=`dali_persistence`, driver=`audio_rms`)* | full_creative | hard | the **headline**: revives the Dec-2024 Dali run; integrates GLSL TOP + MAT + audio; expected to need self-fixes — demonstrates the **fix-iterations / cost** measurement and the **worst-case backlog** |

Optional 6th if live-TD time allows: `bl_glsl_pop_sim_instanced`
*(sim=`boids_flocking`)* — POP buffer + instanced geo in live TD.

**What each demo case yields on screen / in artifacts:**

- D1 — score + which concepts were/weren't surfaced (KB hit list).
- D2 — `.tox` produced, imported into `/test/D2`, render captured, all green; ~10s.
- D3 — same loop + visible CHOP→array wiring inside `/test/D3`; harness
  asserts the array uniform is populated, no string-literal trap.
- D4 — `errors.txt` shows the seeded `redefinition` line gone; diff vs the
  broken input recorded.
- D5 — `output.png` of the Dali scene + `fix_iterations` count + `cost_usd`
  + (likely) one or two failure rows in the backlog with the exact GLSL
  error class. **This is the case where the *measurement* is most
  valuable** — it gets there, expensively, and we can show how much.

## 9. Prereqs for running the demo

- **TouchDesigner** running with `MCP/td-webserver/mcp_webserver_base.tox`
  imported (WebServer DAT on `127.0.0.1:9981`). The `/test` base COMP empty
  at start.
- **`ANTHROPIC_API_KEY`** set in the server env (Mode 2 — the agent does
  the generation + self-repair we're counting).
- **Interpreter**: `C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe`
  (the one with `mcp` + `chromadb` + `sentence-transformers`).
- `pip install -e ".[dev]"` (already configured in `pyproject.toml`).

## 10. Out of scope for v1 demo

- **Multimodal visual-intent judge** (opt-in stretch; offline pixel heuristic
  stands in).
- **Pipeline tier** (designed; not in v1 — the `full_creative` D5 case
  carries the integration story for now).
- **LLM-critique question generator** (planned; the 11 templated cases are
  hand-authored seeds, to be improved later by the generator).
- **Routine many-case full_creative runs** — one in the demo; broader sweep
  is a roadmap item once the loop is proven.

## 11. Roadmap

1. **v1 demo (today)** — run the five D1–D5 cases; produce artifacts +
   `review.md` + baseline.
2. Iterate cases.yaml against the worst-case backlog.
3. Add the **pipeline tier** (1 case: full Dali AV pipeline as 3 composed
   `.tox`).
4. Build the **question generator** with LLM critique/improve loop (planning
   prompt already drafted).
5. Add **multimodal visual-intent judge** as opt-in scorer.
6. Grow the case set toward broader coverage; track cost/fix-iteration
   trends across releases.

## 12. Files

- `tests/glsl_eval/DESIGN_BRIEF.md` — *this document*
- `tests/glsl_eval/cases.yaml` — the templated case spine (11 cases)
- `tests/glsl_eval/EVAL_REVIEW.md` — the analysis/review companion
- `tests/measure/` — the execution + scoring + baseline harness (already
  built, runnable)
- `pyproject.toml` — dev deps + pytest config
- Prior corpus the failure catalogue is drawn from:
  `C:\TD_Projects\META_AGENTIC_TOOL\output\old` (basic_tests_1-10, Dec 2024)
