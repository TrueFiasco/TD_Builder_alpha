# GLSL Eval — State of the Suite (Review Document)

Read through and annotate. Four sections: **the prompts**, **marking
criteria**, **what we can reasonably automate**, **where the human is in the
loop**. Open decisions at the bottom.

---

## 1. The prompts

### Slot banks (in `cases.yaml > vars`)

| slot | options (first = default) |
|---|---|
| `theme` | `sci-fi`, `horror`, `dali_persistence`, `picasso_cubist` |
| `sim` | `boids_flocking`, `attractor`, `cloth` |
| `bug` | `version_not_first`, `uniform_redefinition`, `vec3_to_vec2`, `reserved_word` |
| `binding` | `vector_param`, `chop_array`, `texture_input`, `pop_buffer`, `feedback_buffer` |
| `stage` | `fragment`, `compute`, `vertex` |
| `render_fixture` *(MAT/POP)* | `closeup`, `instanced_far`, `from_scratch` |

### Drivers — binding-aware input data sources

| driver | shape | exercises | network it forces |
|---|---|---|---|
| `lfo` / `mousein` / `audio_rms` | scalar / vec2 | `vector_param` | CHOP → uniform |
| `chop_multisample` | `float[N]` | `chop_array` | multi-sample CHOP → array uniform |
| `noise_top` | texture | `texture_input` | interactive Noise TOP → sampler |
| `pop_points` | buffer | `pop_buffer` | source POP → GLSL POP buffer in |
| `feedback_state` | state buffer | `feedback_buffer` | Feedback TOP ↔ GLSL TOP ping-pong |

### The 11 starter cases (the spine — drafts, to be improved)

| id | section | op | difficulty | one-line intent |
|---|---|---|---|---|
| `kn_glsl_stage_roles` | knowledge | TOP | easy | which TD op runs `{stage}` shader + auto-uniform model |
| `bo_glsl_top_theme_color` | build_offline | TOP | easy | minimal `{theme}` build → export → import → render |
| `bo_glsl_top_driver_uniform` | build_offline | TOP | medium | `{driver}` CHOP chain → vector_param uniform |
| `bo_glsl_top_chop_array_lut` | build_offline | TOP | medium | multi-sample CHOP → array uniform as `{theme}` LUT |
| `bo_glsl_mat_vertex_displace` | build_offline | MAT | hard | vertex+pixel + Geo/Camera/Light/Render |
| `bl_glsl_top_blend_inputs` | build_live | TOP | medium | live create + Noise TOP → texture sampler |
| `bl_glsl_pop_sim_instanced` | build_live | POP | hard | `{sim}` POP compute + buffer + instanced geo |
| `fo_glsl_fix_bug` | fix_offline | TOP | medium | repair a `{bug}`-class GLSL error |
| `fl_glsl_fix_live` | fix_live | TOP | medium | live error-log-driven repair |
| `fc_creative_av_scene` | full_creative | TOP+MAT | hard | Dali/sci-fi-tier integration + .tox import-at-level |
| `bo_glsl_top_feedback_sim` *(growth)* | build_offline | TOP | hard | `{sim}` held across frames via feedback ping-pong |

### Pipeline tier (designed, not yet a case)

Composed stage-toxes; GLSL is the *focus* but not mandatory per stage. Each stage declares `glsl: required|optional|none` + `expected_tools`. Default shape: `gen_geo_instancing → render (TD render OR GLSL TOP) → postFX (GLSL)`. Keep to 1–2 pipeline cases; scored composite (per-stage subscores + final integrated render + fix_iterations/cost across the whole pipeline).

---

## 2. Marking criteria

### Per case (automated, deterministic)

| section | composite score = signals |
|---|---|
| `knowledge` | right operator(s) named + expected concepts/keywords present in answer |
| `build_offline` | built + imports at right level + `td_validate` clean + GLSL compiles 0 err + renders non-black + binding wired + `.parm` non-empty |
| `fix_offline` | validates + the specific `{bug}` defect removed + still renders the intent |
| `build_live` | built + right op + compiles 0 err + renders non-empty + binding wired |
| `fix_live` | error count → 0 + compiles + renders + project otherwise unchanged |
| `full_creative` | composite of the above across stages + integrated render |
| pipeline (planned) | per-stage subscore + final-render subscore + composition penalty if a stage's output isn't consumable by the next |

### Cross-cutting (every case, regardless of section)

| field | meaning |
|---|---|
| `terminal_score` | the section composite above (0..1) |
| `fix_iterations` | number of self-repairs the agent did before final candidate |
| `duration_s` | wall-clock to final |
| `cost_usd` / tokens | spend to get there (from `MetricsCollector`) |
| `human_score` *(optional)* | your override / spot-check column |

### Reporting

- Per-case JSON + a `review.md` table.
- Aggregate score per section + per binding + per difficulty (existing `by_group` in `harness.py`).
- Delta vs last promoted baseline + ranked **worst-case backlog**.
- Per-run TD project left populated: `/test/<case_id>/` outputs to eyeball.

---

## 3. What we can reasonably automate

Concrete signals + the source that provides them:

- **Build invocation** — `NetworkBuilder` (offline) / `td_build_project` (tool) / `create_td_node` (live).
- **Import-at-correct-level** — execute_python_script in `/test`; verify produced operator paths match expected.
- **Render capture** — `capture_top_output` → PNG saved to artifact folder.
- **GLSL compile pass/fail + error class** — `get_td_node_errors`; regex-match the catalogue (`#version`, `redefinition`, `vec3 → vec2`, reserved-word).
- **Cook errors / python exceptions** — `get_cook_errors`, `get_python_exceptions`.
- **Structural validity** — `td_validate` 5-stage pipeline.
- **Operator/parameter exists** — `OperatorRegistry` lookup (no hallucinated ops).
- **Binding wired** — inspect the produced network: page params present, CHOP/TOP/POP input connected, no double-declared uniforms.
- **Image non-empty** — pixel stats on captured PNG (mean luminance, variance) to detect all-black / all-static.
- **Retrieval-relevance** (knowledge) — operator-presence + keyword match in `hybrid_search` results.
- **Fix-iteration count** — from `MetricsCollector` troubleshooting events (`build_failure`, `validation_error`, `phase_reopen`).
- **Cost / latency** — `TokenUsage.estimated_cost_usd`, wall-clock.
- **Defect-removed check (fix tasks)** — diff the specific seeded error class is no longer in `get_td_node_errors`.

**Stretch (opt-in, LLM-assisted, still deterministic-fallback):**

- **Visual-intent match** — multimodal LLM scores how well the render fits the `{theme}` (e.g. does this look Dali-melting-clock-ish). Cheap rubric; offline fallback = pixel/histogram heuristic.
- **GLSL code quality** — rubric: uses TD auto-uniforms, no redundant declarations, readable, no obvious perf antipatterns.
- **Prompt sanity / seed improvement** — the planned generator's critique/improve stage (already specced).

---

## 4. Where the human is in the loop

Roles, from minimal to maximal — pick the level that matches the time you'll actually spend.

### Minimum (recommended default): **calibrator + spot-checker**

- After a run, open `review.md` + the populated TD project at `/test/`.
- Fill `human_score` for the **cases you choose to eyeball** — not all of them. Likely the `full_creative` cases and a few `build_*` worst-cases.
- Flag any case where auto-score disagrees with reality (high auto-score but visually wrong, or low auto-score but actually fine). These calibration notes tighten the auto-score over time.

### Medium: **case author**

- Edit `cases.yaml` slots / banks to iterate prompts (swap `dali_persistence` → `picasso_cubist`, `boids_flocking` → `cloth`, change the `{bug}` to repair).
- Approve / reject seeds the planned generator wants to add or rewrite.

### Maximal: **review log keeper**

- Reproduce `bug_report_basic_tests.md`-style per-case notes (root cause routed to agent/KB/tool/build — PETER/KYLE/TERRY-style) for the runs that matter.
- This is high-effort; reasonable only for milestone runs (post-merge, big refactor).

**Things automation will NOT decide for you and HITL must own (recommended):**

- Whether a render *visually matches the artistic intent* (the multimodal-judge can suggest; you sign off).
- Architectural taste / idiomatic choice (e.g. did it use GLSL POP correctly vs. a contrived CHOP workaround).
- Final pass/fail for milestone reviews — the auto-score and backlog are the dashboard; you make the call.

---

## 5. Open decisions (mark these as you read)

- [ ] Visual-intent **multimodal LLM judge**: in v1, or grow into?
- [ ] **Pipeline tier**: 1 case in v1 (e.g. the Dali AV pipeline), or defer entirely?
- [ ] **Cases per run**: routine ~10 / full ~30+ — what feels right?
- [ ] **Live-TD always on**, or accept offline-only runs (skip `build_live` / `fix_live` / `full_creative` then)?
- [ ] **Generator with LLM critique** built now, or only after the loop is proven manual-first?
- [ ] **Human-score scope**: every case, or just `full_creative` + worst N?
- [ ] **Anything in §1–§4 missing or wrong** for what you actually want to learn from a run?

---

## Files this review covers

- `tests/glsl_eval/cases.yaml` — the 11-case templated spine
- `tests/measure/` — the existing execution harness (probe, baselines, deltas, worst-cases)
- The planning prompt for the GLSL question generator (in chat; not yet a file)
- Prior corpus the failure catalogue is drawn from: `C:\TD_Projects\META_AGENTIC_TOOL\output\old` (basic_tests_1-10, Dec 2024)
