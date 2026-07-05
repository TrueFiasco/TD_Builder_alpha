# Agent eval — end-to-end (NL prompt → tool calls → valid `.tox`)

The model-in-the-loop gate. Everything else in `eval/` measures a *layer*:
`run_eval.py` measures retrieval (frozen-78), `build_gate/` measures builder
correctness (token-exact vs live TD). **This** measures the product's actual
behavior: a natural-language prompt driven through real tool-call sequences to a
validated offline artifact. Design of record:
[`../TD_builder audit/AGENT_EVAL_DESIGN.md`](../TD_builder%20audit/AGENT_EVAL_DESIGN.md)
(work item 2c of the harness remediation program).

Scope is **offline only** — hosted runners have no TouchDesigner. The live halves
of the manual suites (the 12-tox ladder Phases 3–5, Penrose P10–P12: import, cook
errors, live captures, round-trip-from-live) stay manual and authoritative for
live GO/NO-GO. This harness automates the offline halves: KB grounding, tool-call
discipline, offline build, out-of-band validation, artifact correctness.

## Two lanes — and the honesty rule

| Lane | Flag | Measures | Determinism | Auth | Runs |
|---|---|---|---|---|---|
| **agent-gate** | `--lane model` | the model choosing tool calls against the real stdio server (the missing thing) | none (sampling → statistics, §"Baseline") | maintainer Claude **subscription** (D-A) | maintainer machine, scheduled + pre-release |
| **replay-gate** | `--lane replay` | tool contract + KB + builder under blessed, frozen call patterns | **full** (fixed trace + fixed code + fixed KB) | none | every CI run, local pre-merge |

**Honesty rule (load-bearing):** a green **replay-gate is never "agent eval
passing."** It certifies harness integrity (the tools, KB and builder still
produce valid artifacts under a realistic call pattern); it does **not** measure
the model. Reports name the two lanes distinctly. A green replay-gate with a red
agent-gate is precisely the signal *"code fine, model path changed"* — start
regression triage at the replay lane (below).

## Quick start

```bash
# deterministic replay-gate (CI / pre-merge) — key-free, minutes-fast
py -3.11 eval/agent_eval/run_agent_eval.py --lane replay

# agent-gate, gate-eligible set, k=1 + escalation (needs the logged-in CLI)
py -3.11 eval/agent_eval/run_agent_eval.py --lane model

# weekly full sweep (all 14 scenarios, k=3)
py -3.11 eval/agent_eval/run_agent_eval.py --lane model --all --k 3

# baseline capture (n=5) → writes baseline.json + gate/aspirational split
py -3.11 eval/agent_eval/run_agent_eval.py --lane model --capture-baseline --n 5

# one scenario, during tool/KB development
py -3.11 eval/agent_eval/run_agent_eval.py --lane model --scenario s05_palette_audio

# promote a passing model run's tool sequences to blessed replay traces
py -3.11 eval/agent_eval/run_agent_eval.py --bless <run-id>

# diff a sweep against the committed baseline (refuses on identity drift)
py -3.11 eval/agent_eval/run_agent_eval.py --lane replay --compare eval/agent_eval/baseline.json
```

Exit codes: `0` clean, `1` a gate scenario is red (FAIL), `2` the sweep itself is
suspect (≥1 ERROR, or a spend/rate abort), `3` `--compare` refused on identity
drift.

## What's here

```
run_agent_eval.py   THE one command (both lanes, capture/compare/bless)
score.py            deterministic scorer — assertion vocabulary, verdict taxonomy,
                    out-of-band ValidationPipeline, connection barrier (R-3)
identity.py         shared environment-identity stamp (also imported by run_eval.py, §8)
inproc.py           in-process server bridge for Lane R (tests/measure probe pattern)
config.json         model pin (D-B), budgets, k/n, spend cap
guidance.md         canonical injected guidance (D-C; hashed into identity)
mcp.eval.json.tmpl  strict per-run MCP config template
scenarios/          s01…s14 (schema below)
fixtures/           make_fixtures.py → text.tox (generated/, gitignored)
traces/             blessed replay traces (calls-only JSONL, committed)
baseline.json       committed after an n=5 capture
runs/               gitignored: <run-id>/<scenario>/{transcript.jsonl, work/, score.json}
tests/test_scorer.py  seeded scorer acceptance tests (KB-free)
```

Human-readable reports stage to `New KB build/Output/agent_eval/` (the established
staging convention); the only committed products are `baseline.json`, `scenarios/`,
`traces/`, `config.json`, `guidance.md`.

## Scenario schema

One JSON per scenario (`scenarios/sNN_<slug>.json`). Expectations bind to **stable
identity, not instance names** — the model names its own nodes, so assertions are
type-level (op presence by `family:base_type`, wires by type-adjacency, params by
code + mode + value). Assertion vocabulary (closed set, in `score.py`):

- `trace`: `tool_called`, `tool_not_called`, `call_order`. Tool refs accept the
  **alias `kb_lookup_any`** (R-2: the **exact 10** knowledge-retrieval tools —
  `hybrid_search, get_operator_info, query_graph, list_pop_operators,
  find_operator_examples, find_operator_combination, find_parameter_usage,
  find_similar_networks, get_parameter_detail, get_network_patterns`; it
  deliberately EXCLUDES `get_expert_prompt` and `get_server_info`) or an
  any-of list.
- `artifact`: `tox`/`toe` (existence + expanded `.dir`), `ops_present`/`ops_absent`
  (type + min-count), `wires` (type-adjacency), `params` (code/mode/value/
  value_contains/value_re), `parm_line_re`, `network_has` (block/regex),
  `n_file` (first_line/re/not_re), `work_file_re` (file-backed shaders beside
  the artifact), `min_total_ops`, `min_families`, `absent`.
- `response` (model lane only): `must_match` / `must_not_match` over the
  assistant text.
- `validate`: `"PASS"` runs the 5-stage `ValidationPipeline` **out-of-band** on
  the built design (we do NOT trust the agent's own `td_validate` — whether it
  *called* it is a separate trace assertion). `null` skips it (used where the
  design crosses a palette/external_tox placeholder boundary the validator can't
  see inside — see the scenario `notes`).
- `writes_confined` (implicit, always on): all builds must pass `output_dir`
  under the run dir.

## Verdicts (taxonomy is load-bearing)

| Verdict | Meaning | Counts toward pass-rate |
|---|---|---|
| PASS | gate satisfied | yes |
| FAIL | gate violated by model/product behavior | yes |
| ERROR | harness fault: CLI crash, timeout/budget, spend cap, **no MCP connection evidence** (R-3), disallowed-tool leak | **excluded** (>0 flags the sweep) |
| SKIP | precondition absent (`requires`, or replay lane with no blessed trace) | excluded |

`ERROR ≠ FAIL` is the anchor for telling harness regression from model variance: a
dead/never-connected server must never read as "the model regressed."

### R-3 — the connection barrier

A headless `claude -p` run can exit normally with the MCP server **never
connected** (proven on CLI 2.1.19x: normal exit, complete transcript, zero tool
calls). The scorer requires **positive** connection evidence before evaluating any
assertion: a stream-json `init` event listing `td-builder` as `connected`, **or**
≥1 successful `td-builder` tool result. Absent → **ERROR**, never FAIL. The replay
lane mirrors this with a mandatory `get_server_info` preamble.

### R-1 — budgets & turns

The pinned CLI (2.1.81, re-verify at pilot via the `cli_version` in the identity
block) has **no `--max-turns`**. Budgets are enforced as a **per-scenario
wall-clock timeout** + a **sweep-level spend cap** (`config.json`); exceeding
either books **ERROR**. Turn counts are **scored post-hoc** from the stream-json
transcript (always countable, even on a truncated stream).

## Baseline, gate set, and regression triage

- **Capture** runs each scenario `n=5` (fresh `claude -p` per trial). `baseline.json`
  records per-scenario pass-rate, failure fingerprints, and median advisory metrics.
- **Gate set** = scenarios at **5/5** in the capture; everything else is
  **aspirational** (tracked, reported, never blocks). A scenario promotes to the
  gate only via a fresh 5/5 capture; it demotes only by an owner decision recorded
  in the changelog below.
- **Routine sweeps**: gate set at **k=1 with escalation** — a FAIL triggers 2
  reruns, red iff <2-of-3 pass. **Pre-release**: straight k=3, m=2, full set.
- **Triage order**: (1) replay-gate first — if red, the regression is in
  code/KB/tool-contract; fix that, ignore the model lane. (2) ERROR vs FAIL. (3)
  assertion fingerprints — same assertion across reruns = systematic; different =
  variance. (4) escalation reruns as the significance test.

## Versioning & identity

Every result and baseline embeds an identity block:
`{scenario_set_version, model_id, cli_version, server_version, kb_manifest_version,
kb_sha, tool_inventory_hash, guidance_hash}`. `--compare` **refuses** on any
mismatch (`--allow-identity-drift` overrides, marking the report NON-COMPARABLE).

- **Tool-surface changes** (later waves touch `mcp_server.py`'s 17-tool list):
  `tool_inventory_hash` flips → re-bless traces + re-capture, bump
  `scenario_set_version` minor. **Every wave that edits the tool list must budget
  an agent-eval re-bless** (the program already serializes `mcp_server.py`
  one-toucher-per-wave — add re-bless to that wave's acceptance).
- **KB rebuilds**: artifact assertions survive (stable identities); model behavior
  shifts → re-capture on any `kb_manifest_version` change; re-bless traces only if
  envelope shapes changed materially.
- **Model pin (D-B)**: `config.json.model_id` is the exact dated Sonnet snapshot,
  resolved at setup. A pin change is a deliberate re-baseline event.
- **Guidance (D-C)**: `guidance.md` is today's shipped skill text, distilled;
  its sha256 is in the identity block, so a 3b/D2 swap forces a visible re-capture.
- **Trace blessing**: `--bless <run-id>` promotes a PASSing model run's tool
  sequence to `traces/sNN.jsonl` — **calls only** (tool + args, `{{RUN_DIR}}`-
  templated). Result envelopes are deliberately NOT committed (replay re-executes;
  storing them would leak KB-derived, wiki-licensed text into a repo that commits
  no KB content).

## Auth (D-A) — subscription only, no API key

Lane M uses the maintainer's logged-in Claude CLI. The runner **actively strips**
`ANTHROPIC_API_KEY` (and other credential/model-override env vars) from the
subprocess environment — there is no API-key path anywhere in this harness, and
the shipped product stays key-free. Lane M **never runs on fork PRs or hosted CI**.

## CI placement & promotion path

Lane R joins **`kb-full.yml`** as a follow-on step (the same cached-KB windows
runner the retrieval eval already uses), **advisory at bring-up**
(`continue-on-error: true`) exactly as every kb-full lane started. It runs the
blessed traces in-process and scores with the same validator.

**Promotion to blocking** (a one-line flip once proven): after Lane R is green on
hosted runners on two consecutive `kb-full` runs, remove `continue-on-error: true`
from the "Agent-eval Lane R" step. It is safe to make pre-merge-blocking because it
is deterministic and key-free; when Wave-1's KB-restore lane is on the fast `ci.yml`
path (it currently lives in `kb-full`), Lane R can move there to gate every PR.
Lane M stays out of CI **by design** (D-F: scheduled runs live on the maintainer
machine — nightly gate-set k=1+escalation, weekly full k=3).

## Release procedure (D-E) — agent-gate capture is REQUIRED before tagging

Before tagging any post-remediation release:

1. Run a fresh **full capture**: `run_agent_eval.py --lane model --capture-baseline
   --n 5` (or `--lane model --all --k 3` for a gate check without re-baselining).
2. The gate set must be **green**. A red gate scenario **BLOCKS the tag** unless
   the owner writes an override note that joins the release record (name the
   scenario, the fingerprint, and why shipping anyway is acceptable).
3. This sits beside the manual live suites (ladder P3–5, Penrose P10–P12) in the
   release checklist — the automated agent-gate covers the offline behavior; the
   manual suites cover live behavior. Both are required.

## Re-baseline / re-bless procedures

- **Add a scenario**: it enters *aspirational*; earns gate status via a fresh 5/5
  capture. New scenario files need no other ceremony.
- **Edit a scenario** (prompt or expectations): bump its `version`, re-capture
  that scenario, re-bless its trace.
- **Tool surface / KB / model / guidance change**: see Versioning above — the
  identity hash flips and forces the matching re-capture / re-bless.
- **Demote or delete a gate scenario**: requires an owner decision + a changelog
  entry below (teardown-proofing).

## Changelog

- **1.0.0** (2026-07-04, W2c): initial 14 scenarios (s01–s14). Gate-eligible by
  design: s01–s12, s14 (13); s13 born aspirational (hardest multi-chain). s05/s10/
  s13 carry `validate:null` — the ValidationPipeline cannot resolve wires crossing
  a palette/external_tox placeholder boundary (verified 2026-07-04; product gap
  noted in the W2c PR). Actual gate membership is set by the first n=5 capture.
- **baseline n=5** (2026-07-05, W2c deferred deliverable): first full n=5 capture,
  on merged `main` @ `6a2f461` (Merge W3a: builder correctness + grounding/
  bare-comp validators). Spend $8.21 (s10–s14), under the $25 cap. **Gate set
  (5/5, 7):** s01, s03, s05, s08, s10, s12, s14. **Aspirational (7):** s02/s04/s06
  (4/5) and s07/s09 (3/5) — model variance; **s11** (0/5 — correctly under-reports
  the wrapper's `in1`/`in2`/`out1`, the known bloom-manifest gap: born-aspirational
  against a known gap is the harness working, not rot; it also booked 1 budget-
  timeout ERROR, excluded from pass-rate); **s13** (5/5 but `gate:false`
  born-aspirational → **promotion candidate**, owner decision required to flip
  `gate:true` + re-capture). Lane R replay determinism verified byte-identical
  across two sweeps. **Provenance** (`baseline.json._provenance`): s10–s14 freshly
  captured on `6a2f461`; s01–s09 model-samples reused verbatim from `cbf01f1`
  (pre-W3a) per owner decision, re-validated PASS by Lane R on `6a2f461`. The
  8-field identity block is invariant across that snapshot pair (server_version is
  a constant), so `--compare` cannot see the split — the provenance block is the
  record.
