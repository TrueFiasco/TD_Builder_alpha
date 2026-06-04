# Measurement & improvement suite

This is **not** a pass/fail gate. Each target measures a scalar metric over a
dataset, stores a baseline, prints a ranked **worst-case backlog**, and reports
the **delta vs the last baseline**. The loop is:

> measure → read the worst cases → change the code → re-measure → keep the
> baseline only if the number improved.

## Interpreter

The server's runtime deps live in the configured 3.11 interpreter:

```
C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe
```

Use it for every command below (it has `mcp`, `chromadb`, `sentence-transformers`).

## Targets

| Target | What it measures | Scorer | API? |
|---|---|---|---|
| `builder_param_acceptance` (#1) | % of an operator's real params that survive `td_build_project` → re-parse, vs `operator_ground_truth/params/*_defaults.json` | pure diff | no |
| `retrieval_recall` (#2) | recall@10 / MRR / KB coverage from `hybrid_search`+`get_operator_info`; `find_similar_networks` coverage (≈0% floor) | auto | no |
| `validator_accuracy` (#3) | false-flag rate (good rejected) + miss rate (bad passed) + right-stage rate, over good nets + `mutators.py` corruptions | auto | no |
| `agent_quality` (#4) | operator/connection recall of V2-generated networks vs the H17 YAML answer keys | auto | **yes** |
| `crosscut` | per-tool response tokens, latency, error actionability, compact-vs-full bloat | heuristic / opt-in judge | no |

## Commands

```powershell
$PY = "C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe"
cd C:\TD_builder_alpha

# First run = establish baselines (no delta yet)
& $PY -m pytest tests/measure -m "not mode2" -s --promote

# Improvement loop: change code, re-run a target, read metric + Δ + worst cases
& $PY -m pytest tests/measure/test_builder_params.py -s
& $PY -m pytest tests/measure/test_retrieval.py -s
& $PY -m pytest tests/measure/test_validator.py -s
& $PY -m pytest tests/measure/test_crosscut.py -s

# Everything at once, one consolidated table
& $PY -m pytest tests/measure/test_measure_all.py -s

# Promote new numbers ONLY when a change improved them
& $PY -m pytest tests/measure -m "not mode2" -s --promote

# #4 agent quality (real API cost ~$0.05/case)
$env:RUN_NL_EVAL="1"; $env:ANTHROPIC_API_KEY="sk-..."
& $PY -m pytest tests/measure/test_agent_quality.py -s
```

## Dataset size knobs

Targets sample per family for a fast loop; widen via env vars:

- `MEASURE_FULL=1` — use the entire dataset (all ~640 builder ops, all operators)
- `MEASURE_BUILDER_N=<n>` — builder ops per family (default 3)
- `MEASURE_RETRIEVAL_N=<n>` — retrieval queries per family (default 6)
- `RUN_JUDGE=1` (+ `ANTHROPIC_API_KEY`) — LLM-graded fuzzy sub-scores instead
  of the deterministic heuristic

## Outputs

- `tests/measure/baselines/<target>.json` — promoted baseline (commit these).
- `tests/measure/results/<target>_<ts>.{json,md}` — every run's full report +
  delta + worst-case backlog (gitignore-able history).

## How to improve a target

1. Run it, read the printed `worst N` and the `## worst cases` table in the MD.
2. The `group` column localises the weakness (operator family / mutation
   category / tool). Fix the code there.
3. Re-run the single target. The `Δ` line tells you if it worked; `REGRESSED`
   warns if you broke previously-good cases.
4. When green-er, `--promote` to lock the new baseline.
