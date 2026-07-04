# Workflow metrics shapes (design harvest, D4 input)

**Status: design input, not implemented.** Harvested 2026-07-04 (harness remediation W2a)
from the never-wired workflow-orchestration reference implementation, now preserved at
`quarantine/meta_agentic_orchestration/` (see `quarantine/README.md`). Nothing in the
shipped server records these metrics. This document keeps the *dataclass shapes and
aggregation intent* as input to D4 (minimal feedback spine).

Companion: [blackboard_schema.md](blackboard_schema.md) (D6 input).

## The four shapes

**TokenUsage** — cost accounting unit, per agent call and rolled up per phase:

| Field | Type | Notes |
|---|---|---|
| `input_tokens` / `output_tokens` | int | derived: `total_tokens`, `estimated_cost_usd` |

The reference implementation hardcoded 2025-01 per-1K prices in the module
(input 0.015 / output 0.075 USD). Lesson for D4: price tables must be config/data, never
code constants — they were stale before the code ever ran.

**PhaseMetrics** — one per workflow phase:

| Field | Type | Notes |
|---|---|---|
| `phase` | str | phase name |
| `iterations` | int | expert-revision count within the phase |
| `scores` | list[float] | full critic-score history, order preserved |
| `token_usage` | TokenUsage | phase rollup |
| `started_at` / `completed_at` | timestamp | wall-clock bounds |
| `reopened_count` | int | how often a blocking issue forced the phase back open |

Derived: `final_score` (last), `best_score` (max), `improvement` (last − first). Keeping
the whole score *history* — not just the final — is what makes convergence detection and
"did iteration help?" questions answerable.

**TroubleshootingEvent** — every recovery gets a record:

| Field | Type | Notes |
|---|---|---|
| `event_type` | str | `build_failure` / `validation_error` / `phase_reopen` / `manual_intervention` |
| `phase` | str | where it happened |
| `timestamp` | str | UTC |
| `description` / `resolution` | str / str-or-null | what went wrong, what fixed it |
| `tokens_spent` | int | cost attributable to the recovery, separate from productive spend |

The taxonomy is the valuable part: it splits *rework cost* out of total cost, which is
exactly the signal a feedback spine needs to say whether the harness is getting cheaper
at recovering.

**ArtifactValidation** — did the output actually work:

| Field | Type |
|---|---|
| `toe_valid` | bool |
| `uniforms_connected` | bool |
| `palette_used` | bool |
| `params_functional` | bool |
| `validation_errors` | list[str] |

The four booleans are TD-specific but the pattern generalizes: a small fixed checklist of
*independently verifiable* artifact properties, not one pass/fail bit.

## Aggregation intent

- **Run quality = min across phase final-scores** (deliberately pessimistic — the V5/V6
  multi-perspective rule: a run is only as good as its weakest reviewed phase).
- Rollups: total tokens/cost, total iterations, counts by troubleshooting type
  (`build_failures`, `validation_errors`, `phase_reopens`, `manual_interventions`).
- Report envelope (JSON): `run_metrics{strategy, project, started/completed_at,
  cost{...}, quality{per-phase score histories}, iterations{per-phase + total},
  troubleshooting{counts + full event list}, artifacts{...}, agent_calls[...]}` — one
  self-contained file per run, diffable across runs.
- **Cross-run comparison**: rows of (strategy, tokens, cost, quality, iterations,
  failure counts, artifact validity), sorted by quality desc then cost asc — the shape of
  an A/B answer, not a dashboard.

## Notes for the D4 design

- Minimal viable spine from these shapes: per-run report file + TroubleshootingEvent
  taxonomy + the artifact checklist. PhaseMetrics only matters once there are phases
  worth attributing to (D6); TokenUsage only once the harness can actually observe token
  counts.
- The reference implementation had no writer wired to any real signal — every field was
  designed but never fed. D4 should start from what the harness can *measure today*
  (eval gate results, build-gate outcomes, test pass/fail, wall-clock) and grow toward
  these shapes, not implement them wholesale.
