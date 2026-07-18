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

# weekly full sweep (all 18 scenarios, k=3)
py -3.11 eval/agent_eval/run_agent_eval.py --lane model --all --k 3

# baseline capture (n=5) → writes baseline.json + gate/aspirational split
py -3.11 eval/agent_eval/run_agent_eval.py --lane model --capture-baseline --n 5

# PARTIAL recapture: re-captures only the named scenarios and MERGES with the
# committed baseline.json (non-swept records reused verbatim, sets recomputed,
# reuse + identity drift disclosed in _provenance)
py -3.11 eval/agent_eval/run_agent_eval.py --lane model --capture-baseline --n 5 \
    --scenario s05_palette_audio --scenario s09_abstention

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
mcp.eval.json.tmpl  strict per-run MCP config template (offline scenarios)
mcp.eval.live.json.tmpl  live-surface variant: + td-builder-live (s15–s17)
scenarios/          s01…s21 (schema below)
fixtures/           make_fixtures.py → text.tox (generated/, gitignored)
                    knotgen.tox.dir + .toc — COMMITTED own-content component (s19–s21)
traces/             blessed replay traces (calls-only JSONL, committed)
review/             registration description-quality ledger (RUBRIC.md + extractor)
baseline.json       committed after an n=5 capture
runs/               gitignored: <run-id>/<scenario>/{transcript.jsonl, work/, score.json}
tests/test_scorer.py            seeded scorer acceptance tests (KB-free)
tests/test_requires_and_review.py  tool: gate, fixture canary, ledger extractor
```

Human-readable reports stage to `New KB build/Output/agent_eval/` (the established
staging convention); the only committed products are `baseline.json`, `scenarios/`,
`traces/`, `config.json`, `guidance.md`, `fixtures/*.tox.dir`, and `review/`.

### Fixtures — generated vs committed

`stage_fixtures` copies each name in a scenario's `fixtures` list into
`work/assets/<name>`, resolving **committed** `fixtures/<name>` first and only
then falling back to generating into `fixtures/generated/` (s17's
`eval_fragment.glsl`). Committed fixtures are repo content, never build output —
`ensure_fixtures` will not try to make them.

Staging under `work/assets/` is load-bearing for any **blessed** scenario, not
just tidiness: `bless()` templates only the run dir out of tool args
(`{{RUN_DIR}}`), so a fixture referenced from anywhere else would bake an
absolute machine path into the committed trace and break hosted replay. (This is
why s11 gets away with a `{{BLOOM_TOX}}` tvar pointing at a TD install — it has
no blessed trace.)

`knotgen.tox.dir` is **own content** (no Derivative material): a base COMP built
live in TouchDesigner and `toeexpand`'d, whose `circlePOP → glslPOP → outPOP`
deforms a circle onto a parametric knot. `manifest_from_tox` accepts an expanded
`.dir` directly, so it is hermetic — CI parses it with no TD binary. Its sibling
`.tox.toc` is required (the manifest parser refuses a `.dir` without one). Its
`.cparm` deliberately exercises all three parameter classes the `block_io`
renderer formats differently: an int with min/max, a vec3 (list default), and a
menu whose tokens must ride verbatim. `tests/test_requires_and_review.py` canaries
those literals, so editing the fixture fails loudly by name instead of as a
mystery red replay.

## Scenario schema

One JSON per scenario (`scenarios/sNN_<slug>.json`). Expectations bind to **stable
identity, not instance names** — the model names its own nodes, so assertions are
type-level (op presence by `family:base_type`, wires by type-adjacency, params by
code + mode + value). Assertion vocabulary (closed set, in `score.py`):

- `trace`: `tool_called`, `tool_not_called`, `call_order`, `tool_result_re`
  (`{"tool": ..., "re": ...}` — ≥1 call to `tool` whose result text matches;
  lane-INDEPENDENT, because replay re-executes and captures result text — this
  is how live-tool behaviors are asserted without model prose). Tool refs
  accept the **alias `kb_lookup_any`** (R-2: the **exact 10**
  knowledge-retrieval tools — `hybrid_search, get_operator_info, query_graph,
  list_pop_operators, find_operator_examples, find_operator_combination,
  find_parameter_usage, find_similar_networks, get_parameter_detail,
  get_network_patterns`; it deliberately EXCLUDES `get_expert_prompt` and
  `get_server_info`) or an any-of list.
- `artifact`: `tox`/`toe` (existence + expanded `.dir`), `ops_present`/`ops_absent`
  (type + min-count), `wires` (type-adjacency), `params` (code/mode/value/
  value_contains/value_re), `parm_line_re`, `network_has` (block/regex),
  `n_file` (first_line/re/not_re), `work_file_re` (file-backed shaders beside
  the artifact), `min_total_ops`, `min_families`, `absent`.
- `response` (model lane only): `must_match` / `must_not_match` over the
  assistant text.
- `validate`: `"PASS"` runs the 7-stage `ValidationPipeline` **out-of-band** on
  the built design (we do NOT trust the agent's own `td_validate` — whether it
  *called* it is a separate trace assertion). `null` skips it (used where the
  design crosses a palette/external_tox placeholder boundary the validator can't
  see inside — see the scenario `notes`).
- `live` (live-surface only): `absent: [path, ...]` — after the run, the scorer
  asks the **running TouchDesigner** whether anything survives at each path, via
  the READ_ONLY `get_td_nodes` tool. The second out-of-band oracle alongside
  `validate`, and the same reasoning: assert the **outcome**, never the
  mechanism or the agent's word for it. Scores in **both lanes** (replay
  re-executes the calls, then the same probe reads the same world). A probe that
  cannot produce a trustworthy read books **ERROR**, never FAIL — "we could not
  look" and "we looked and it was clean" must not collapse into one verdict.
  `load_scenario` refuses `expect.live` on a non-live surface: the probe has to
  stay behind the `td_live_running` gate or it would drag the live-server import
  and a guaranteed ERROR into the light-deps CI lanes.
- `writes_confined` (implicit, always on): all builds must pass `output_dir`
  under the run dir.

### `requires` tokens

`resolve_requires` gates a scenario on preconditions; an unsatisfied one (or an
unrecognized token) books **SKIP**, never FAIL/ERROR, in **both** lanes.

| token | satisfied when |
|---|---|
| `td_live_running` | `TD_EVAL_LIVE=1` **and** the TD WebServer answers (below) |
| `derivative_bloom_tox` | a local TouchDesigner install provides the real `bloom.tox` (s11); exports `{{BLOOM_TOX}}` |
| `tool:<name>` | `<name>` is on this checkout's tool surface (offline ∪ live) |

`tool:<name>` exists so a scenario written against a tool can predate — or
outlive — that tool's presence. s19–s21 carry `tool:register_component`
(W7/PR #37): on a pre-#37 bisect the tool is absent, so the behavior is
*unmeasurable*, and SKIP is the honest verdict; without the token the model
simply could not call it and the scenario would book a misleading failure. The
inventory probe is memoized per process and any probe failure SKIPs **that one
scenario** with the reason attached rather than taking the sweep down (the
`_td_reachable` posture).

### Live-surface scenarios (s15–s17)

A scenario with `"surface": "live"` + `requires: ["td_live_running"]` measures
the **td-builder-live** tools against a RUNNING TouchDesigner (the PR #24/#26
behaviors: foolproof GLSL flagging, two-phase POP viewer capture,
`get_glsl_status(file_path)`). Mechanics:

- **Precondition**: `td_live_running` = the **`TD_EVAL_LIVE=1` env opt-in**
  AND a socket-probe of the TD WebServer (`TD_API_URL`, default
  `127.0.0.1:9981`) — either half missing → **SKIP** (hosted CI, TD closed,
  or TD open without the opt-in), the s11 posture. The opt-in is load-bearing:
  these scenarios mutate the open TD project, and a scheduled `--all` sweep
  must never poke a live show file just because TD happened to be open.
  Prompts confine all mutations to a scratch container they create, delete it
  afterwards, and forbid `save_td_project` (also trace-asserted) — but only
  run them on a project you're happy for an agent to touch.
- **Lane M** materializes `mcp.eval.live.json.tmpl` (BOTH servers) and extends
  `--allowedTools` with the `mcp__td-builder-live__*` names **minus
  `save_td_project`** — the persistence boundary stays off the allowlist
  entirely, not just trace-asserted (a scenario's `tool_not_called` still
  scores any attempt). Residual soft boundary: `execute_python_script` could
  call `project.save()`; the live server's non-negotiables forbid it. Offline
  scenarios keep the fixed 18-tool surface. `surface:"live"` implies the
  `td_live_running` gate BY CONSTRUCTION (`load_scenario` injects it), so a
  future live scenario cannot accidentally omit the opt-in.
- **Lane R** routes live-tool calls to the in-process live server
  (`tests/measure/_server.py::load_live_server`), with a `get_td_info`
  preamble as the live half of the R-3 barrier. Live traces only exist once a
  live model run is blessed; until then the replay lane SKIPs them.
- **Scoring**: the live server gets its own connection-evidence track — a live
  scenario with no td-builder-live evidence books **ERROR**, never FAIL (a
  dead live server is not "the model regressed"). Live results are asserted
  with `tool_result_re` over the tool contract's rendered text, and live STATE
  with `expect.live.absent` (above), which probes TD directly after the run.
- **Assert outcomes, not mechanisms** (learned the hard way, 2026-07-16): v1 of
  s15–s17 asserted `tool_called: delete_td_node` for cleanup. The first-ever
  live run booked s15 FAIL against an agent that had cleaned up *correctly* —
  it used `execute_python_script` + `.destroy()`, the path the skill itself
  teaches for multi-op work. The container was gone; the scenario failed anyway,
  because it was scoring **how** rather than **what**. s16 passed the same sweep
  only because the agent happened to reach for the pinned tool. Broadening to an
  any-of tool list would have papered over it (`execute_python_script` is called
  for plenty of other reasons, so the assertion would pass vacuously), and
  asserting on the agent's printed confirmation just relocates the self-report.
  If an assertion can be satisfied by a model *saying* the right thing, it isn't
  an assertion — go and look at the world instead.

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
- **Partial capture** (`--capture-baseline` + `--scenario …`) **merges** with the
  committed `baseline.json`: only the swept scenarios' records are refreshed;
  every non-swept record is reused **verbatim** and the gate/aspirational/
  unmeasurable sets are recomputed over the merged map. The reuse is disclosed
  in `_provenance` (a `partial_recapture_<run-id>` note listing reused ids and
  any identity drift vs the prior capture — reused statistics were measured
  under the PRIOR identity; the file's identity block describes only the fresh
  sweep). A reused record whose scenario file was edited since (version drift)
  triggers a WARNING: it needs its own recapture. A capture that covers every
  prior scenario is a fresh overwrite (prior `_provenance` is NOT carried —
  write a new one). One caveat: `checkpoint.py` reconstructs from a single run
  dir and knows nothing of subsets — never commit a checkpoint of a
  partial-recapture run (it warns when it would stomp scored records).
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

Every result and baseline embeds an identity block. The **hard (refuse) tier**
is `AGENT_IDENTITY_FIELDS`:
`{scenario_set_version, model_id, cli_version, server_version, kb_manifest_version,
kb_sha, tool_inventory_hash, live_tool_inventory_hash, guidance_hash, user_store}`.
`--compare` **refuses** on any hard-tier mismatch (`--allow-identity-drift`
overrides, marking the report NON-COMPARABLE) — except that a REPLAY-lane sweep
compared against a model-lane baseline excludes `model_id`/`cli_version`/
`guidance_hash` from the check (replay has no model or CLI in the loop and
injects no guidance; the first two are structurally None there, and
`guidance_hash` — re-read from disk on every lane — would false-refuse on
every `guidance.md` edit while measuring an artifact replay never uses.
Every environment field replay actually exercises still refuses on drift).
`live_tool_inventory_hash` (added at the 2026-07-14 re-bless) stamps the
separate td-builder-live surface from its STATIC tool list — no running TD
needed; proven blind spot: the offline hash stayed constant across the live
21→22 `get_glsl_status` change. Baselines predating a field read as
*unknown* (warn, never refuse).
`user_store` (added at the 2026-07-16 W7 re-bless, owner decision ⑥) stamps
what USER component store the run could see: the literal `"absent"` for a
hermetic (pinned-empty) run — which every eval run must be, via the W7
`TD_BUILDER_USER_DIR`/`TD_USER_PALETTE_DIR` pins (`tests/measure/_server.py`
pre-import; the `mcp.eval*.json.tmpl` per-trial dirs) — else a content sha
over the user registry + index manifest, so a deliberately-dirty run (or a
hermeticity-pin regression) refuses `--compare` instead of silently measuring
KB ∪ user-store under a KB-only identity.

The **soft (warn) tier** is `AGENT_IDENTITY_WARN_FIELDS`:
`{engine_code_hash}` — a newline-normalized hash of `MCP/engine/**/*.py`, the
builder/validation code that produced the run. It closes the `server_version`
blind spot (a hand-bumped constant that stayed `"0.2.0"` while the validation
pipeline went 4→6 stages, and is 7 on current main). It flips on any engine edit, comments included,
which is exactly why it **warns and proceeds** — never refuses, never touches
the exit code. It stays unstamped in the committed baseline until the next
`--capture-baseline`. The block also carries `git_sha` (the commit the sweep
ran on) — informational only, in neither tier, never compared.

- **Tool-surface changes** (later waves touch `mcp_server.py`'s 18-tool list):
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

## Reviewing registration quality (`review/`)

`register_component` makes the model author the words a component is **found by**
— `summary`, `use_cases`, and a `parameter_descriptions` line per custom
parameter. No gate can score that: a vacuous summary commits, reloads and reports
`retrievable: true` exactly like a discriminating one. s19–s21 prove the
plumbing; they prove nothing about the prose. `review/` is the human check.

```bash
py -3.11 eval/agent_eval/review/extract_registrations.py --runs <run-id> --render
```

It harvests every authored field out of `runs/<run-id>/*/transcript.jsonl`,
juxtaposes it with what the component **actually is** (from the same run's
`prepare` skeleton — parameters, menus, defaults, inner ops, I/O), appends to
`review/registration_quality.jsonl`, and renders `registration_quality.md` for
eyeballing against [`review/RUBRIC.md`](review/RUBRIC.md) (Specificity /
Correctness / Searchability, 0–2 each). Both files are committed, so a capture
wave's authored text lands in the PR diff where it can actually be reviewed.

It is an **explicit command, never a sweep side-effect**: Lane R re-plays the
same authored text (no new signal), and a sweep that wrote into the repo tree
would collide with kb-full's "repo tree must stay clean" guard. `--traces`
harvests blessed traces too, but those are calls-only by design, so entries from
a trace carry the authored args with no `actual` column. Only
`register_component`'s own args/results are read — never KB-derived text, the
same licensing line `bless()` draws by refusing to store result envelopes.

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
  capture. New scenario files need no other ceremony. A scenario may ship with a
  blessed trace but **no** baseline entry (s18, s19–s21): `--bless` only needs one
  PASSing model run, whereas `gate_set` membership is *earned* at n/n in a
  capture. Do **not** hand-add ids to `scenarios`/`gate_set`.
- **`--capture-baseline` REWRITES `baseline.json` wholesale** — it builds the file
  from the scenarios in *that sweep* and does not merge, so a partial capture
  (`--capture-baseline --scenario sNN`) silently drops every other scenario's
  statistics. It also does not carry `_provenance` forward: hand-restore that
  block after any capture.
- **Edit a scenario** (prompt or expectations): bump its `version`, re-capture
  that scenario (a partial capture merges — see § Baseline), re-bless its trace.
- **Tool surface / KB / model / guidance change**: see Versioning above — the
  identity hash flips and forces the matching re-capture / re-bless.
- **Demote or delete a gate scenario**: requires an owner decision + a changelog
  entry below (teardown-proofing).

## Changelog

- **1.1.0 / W7 re-bless** (2026-07-18, main @ `05e6a98`; capture run
  `model-20260717-232224`): refreshed `baseline.json` to the **18-tool** offline
  identity (`register_component`, PR #37) so Lane R `--compare` and the nightly
  kb-full stop refusing on `tool_inventory_hash` 17→18 (v0.2.1 precondition B).
  **Partial recapture** (n=5, MERGES per PR #44): s05/s09/s10 re-sampled **and
  re-blessed** (the documented W7 command), s19–s21 re-sampled **stats-only** —
  their #37-era 18-tool traces and the queued `review/` ledger are left intact,
  since the rider only owes them the baseline numbers gate membership is *earned*
  from. The other **11** scenarios are reused verbatim;
  `_provenance.partial_recapture_model-20260717-232224` lists the reuse and the
  identity drift. All 30 model trials PASS; spend **$7.14** (under the $25 cap).
  **Gate set 7→11:** s09 promoted (0.6→5/5) and s19/s20/s21 earned membership at
  n/n; aspirational is now s02/s04/s06/s07/s11/s13. New **`user_store`** hard
  identity field (decision ⑥) — see § Versioning & identity.
  **Sanctioned reuse (Δ6c):** the 11 reused records' model statistics were
  sampled under the **pre-PR #24/#26** hybrid_search envelope; #24/#26 changed the
  hit shape (`parameter_names`/`score_kind`/`parameters_capped`/`compact` +
  sequence-block collapse) *after* those samples, but every reused blessed trace
  re-replays PASS against the new envelopes (Lane R verdicts byte-identical across
  sweeps), so the reused statistics stay meaning-stable. The top-level identity
  block describes the **recaptured** scenarios only; the drift is on the record in
  `_provenance`.
- **1.0.0 / W7 register_component companion** (2026-07-16, main @ 1e84d76): added
  **s19–s21** for the 18th offline tool (PR #37) — s19 register→search roundtrip
  (owner goal: a custom comp can be ADDED and then FOUND), s20 exact-name
  direct-injection under a 4-char name override (locks W1's dropped ≥5-char guard
  for the user registry), s21 Δ1 hit-parity (user hits carry `score_kind` but never
  `parameter_names`/`parameters`). All offline, `gate:true` by design, blessed from
  a Lane M capture — so Lane R actually exercises `register_component` in CI. New
  `requires` token **`tool:<name>`**; `stage_fixtures` gained committed-fixture and
  directory support; new committed own-content fixture `knotgen.tox.dir`. New
  `review/` ledger + rubric for eyeballing the model-authored registry text (no
  gate can score prose). No `scenario_set_version` bump — adding scenarios needs no
  ceremony, and the tool-surface bump that DID flip the identity was PR #37's own.
  `baseline.json` gets provenance text only (identity refresh + n=5 for s19–s21
  belong to the queued re-bless, which must include them). Also corrected the stale
  `rebless_2026_07_14` claim that s15–**s18** shipped with no blessed traces — s18
  was blessed at add time; the correct set is s15–s17.
- **partial-capture merge + replay guidance exclusion** (2026-07-16, PR #37
  post-merge audit B1 + Axis-2 minor): `--capture-baseline` with a scenario
  subset now MERGES with the committed baseline instead of overwriting it
  wholesale (previously the documented W7 partial re-bless would have silently
  erased 11 of 14 scenarios including 5 of 7 gate members, leaving Lane R's
  `--compare` reading `pass_rate=None` — blind — for all of them while exiting
  0). Reuse + identity drift are disclosed in `_provenance`; `checkpoint.py`
  warns before stomping scored records it has no trials for. Separately,
  `guidance_hash` joined `model_id`/`cli_version` in the replay-lane
  `--compare` exclusion — replay injects no guidance, so every `guidance.md`
  edit false-refused the compare. No scenario or baseline content changed.
- **1.0.0** (2026-07-04, W2c): initial 14 scenarios (s01–s14). Gate-eligible by
  design: s01–s12, s14 (13); s13 born aspirational (hardest multi-chain). s05/s10/
  s13 carry `validate:null` — the ValidationPipeline cannot resolve wires crossing
  a palette/external_tox placeholder boundary (verified 2026-07-04; product gap
  noted in the W2c PR). Actual gate membership is set by the first n=5 capture.
- **1.0.0 / PR #24-#26 re-bless** (2026-07-14, main @ cc0a6c5): tool-surface
  re-bless after the Penrose live-feedback waves. Offline identity UNCHANGED
  (17 tool names identical; the hybrid_search hit shape gained
  `parameter_names`/`score_kind`/`parameters_capped`/`compact` + W-C
  sequence-block collapse — all 13 blessed traces re-replay PASS against the
  new envelopes, verdicts byte-identical across two Lane-R sweeps). The LIVE
  surface changed (21→22, `get_glsl_status`) and the 8-field identity was
  blind to it → `live_tool_inventory_hash` joined the identity block (stamped
  into baseline.json with a `_provenance.rebless_2026_07_14` note; model-lane
  numbers untouched). Added **s15–s18** born-aspirational: s15 W-A
  break-shader→detect, s16 W-B POP viewer two-phase capture, s17 W-A2
  shader-file-edit→`get_glsl_status(file_path)` (all `surface:"live"`,
  `td_live_running`-gated, auto-SKIP without a running TD), s18 W-C
  hybrid_search param-collapse fidelity (offline). New assertion
  `tool_result_re`; new templates/fields as documented above. No
  scenario_set_version bump: adding scenarios needs no ceremony (§ Re-baseline)
  and every s01–s14 file is byte-identical.
- **s15/s16/s17 v2 — live-outcome cleanup** (2026-07-16): new `expect.live.absent`
  assertion (see § Assertions); s15/s16/s17 `version` 1 → 2, each swapping
  `tool_called: delete_td_node` for `live.absent: ["/eval_sNN_scratch"]`.
  Prompts are **byte-identical** — the defect was in the expectation, and
  leaving the prompt alone keeps the re-run a clean test of the scorer change.
  No `scenario_set_version` bump: the field guards *baseline comparability*, and
  these three have **no baseline entries at all** (born aspirational at the PR
  #24–#26 re-bless, never captured — `baseline.json` records `null` for each),
  so no recorded number changes meaning. Same precedent as that entry, which
  added these scenarios *and* the `tool_result_re` primitive without a bump.
  Still open, deliberately: s17's `tool_called: execute_python_script` is a
  near-vacuous proxy for "rewrote the file on disk" — retiring it needs an
  on-disk outcome assertion the harness lacks (the file is restored by design,
  so its final state cannot witness the intermediate edit). Owner call; see the
  s17 `notes`.
- **identity warn tier** (2026-07-16, hygiene bundle H4b): `engine_code_hash`
  added as a soft-warn identity field (`AGENT_IDENTITY_WARN_FIELDS`) +
  informational `git_sha` — see § Versioning & identity. No re-bless, no
  baseline edit: traces are calls-only and identity is computed fresh per
  sweep; the old baseline reads the new field as *unknown* (warn) until the
  next capture stamps it. CI Lane R gained `--compare` in the same bundle, so
  the refusal/warn machinery now actually executes in hosted runs.
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
  record. **Current-main re-validation:** origin/main advanced `6a2f461`→`572ceed`
  during the capture (W4a + BUG-3 v0.2.1, both touching `toe_builder_bridge.py`);
  the branch was merged up to `572ceed` and all 13 blessed traces re-replay PASS
  on that builder with byte-identical `verdicts.json` across all four sweeps
  (2× each snapshot) → CI Lane R is green on current main; builder-neutrality now
  proven through W4a/BUG-3.
