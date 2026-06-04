# H17 NL-prompt eval harness

Automated end-to-end eval that runs `(prompt, expected_network)` pairs through
the meta-agentic strategy runner (V2 by default) and scores the result
against an expected operator/connection set.

Designed to bracket the B0 ChromaDB merge / B1+B2 retrieval rewiring work:
run once for a baseline, run again post-merge, report the delta.

## On prior QA results

`archive/personalities/.../QA TESTER - TEST COVERAGE - QUEENIE/` contains
two earlier QA result files that disagree wildly on the same prompt suite
(33% vs 100% pass — `problems.md` H16). They predate this harness and were
human-graded under different criteria from different sessions. **The numbers
in this directory's reports are the new authoritative baseline; the old QA
files are historical.** Do not try to reconcile.

## Cost and time

Each case invokes a multi-turn V2 strategy run with `Preset.QUICK_DRAFT`:
- ~$0.05 of Claude API calls per case (rough estimate; varies with iteration count)
- ~2-5 min wall clock per case
- 10 cases → ~$0.50 and ~30-50 min for a full run

Tests are **skipped by default**. Set `RUN_NL_EVAL=1` to opt in.

## Running

```bash
# Full baseline run, writes to unified_system/eval/results/baseline_<ts>.{json,md}
python -m unified_system.eval.prompt_eval

# Single case for iteration:
python -m unified_system.eval.prompt_eval --case basic_01

# Mock runner (no API calls; validates harness plumbing):
python -m unified_system.eval.prompt_eval --mock --label mock_smoke

# Custom output dir + label (e.g. post-merge run):
python -m unified_system.eval.prompt_eval --label post_b0_b1_b2

# Via pytest (requires RUN_NL_EVAL=1):
RUN_NL_EVAL=1 pytest unified_system/tests/test_prompt_eval.py -v
```

## Authoring cases

Each `cases/*.yaml` declares:

```yaml
name: my_case_name           # must match filename stem
tier: basic                  # basic | intermediate | advanced
prompt: |
  Free-form natural language prompt the agent receives.
expected_operators:
  - CHOP:noise
  - CHOP:null
expected_connections:
  - [noise1, null1]          # (src_op_name, dst_op_name) using TD default names
expected_parameters:         # optional — currently informational only
  noise1:
    amp: "0.5"
tolerance:
  min_operator_recall: 0.8   # default 0.8
  min_connection_recall: 0.5 # default 0.5
notes: |
  Why this case exists, what failure mode it targets.
```

## Pass criteria

A case passes when:
- `operator_recall ≥ tolerance.min_operator_recall` (default 0.8)
- `connection_recall ≥ tolerance.min_connection_recall` (default 0.5)

Recall = `|expected ∩ actual| / |expected|`. Operator IDs are normalized to
`FAMILY:type` form; connections compare `(src_name, dst_name)` pairs of
operator-base-names (last path segment).

## Where the numbers go

JSON + markdown reports land in `unified_system/eval/results/<label>_<timestamp>.{json,md}`.
The markdown is one-page: total pass rate, per-tier breakdown, per-case
table with recall scores. The JSON has full per-case actuals/expecteds for
deep inspection.
