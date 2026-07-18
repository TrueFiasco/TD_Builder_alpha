# build_gate — TD Builder build-correctness gate

Pre-release gate: proves the KB's build-critical data (op names, `.n` `FAMILY:type`
tokens, parameter codes, defaults) actually **BUILDS valid TouchDesigner** through both
the offline builder (`ToxBuilder`/`td_build_project`) and live TD, against the
live-TD ground truth — the untracked main-tree corpus at
`New KB build/Resources/operator_ground_truth/` (captured on TD 099.2025.32820).
Bare `operator_ground_truth` references below resolve there via
`gate_common.gt_dir()`, **not** to a directory under `eval/build_gate/`.

It is the build-side complement to the retrieval gates (`eval/run_eval.py`,
`eval/tool_coverage.py`) and reuses their scaffolding (offline env, KB resolvers that
read the gitignored KB from the MAIN tree, `GroundTruth`, `ParamDefaults`).

## Prerequisites
- `py -3.11` (3.14 has no chromadb wheel).
- In a worktree, bring the KB over from the main tree first (OperatorRegistry resolves
  `KB/operators.json` relative to its own `__file__`): per-FILE hardlink or real-copy
  `operators.json` and `knowledge_graph_enhanced.gpickle`, and **real-copy** `vector_db/`,
  `lexical_index/`, `models/`.
  **Never use a directory junction** — recursive deletes traverse junctions and have twice
  destroyed real KBs (remediation ticket 20). `graphrag.json` is *not* needed: it was retired
  in the v0.2.0 KB redesign and its chunks now live as pointer chunks inside `vector_db/`.
- TouchDesigner running with the `td-builder-live` MCP for Track B.

## Files
| file | role |
|---|---|
| `gate_common.py` | shared foundation: KB/GT resolvers, **`CanonicalMap`** (name→{builder_token, n_token, td_create}), raw `.n`/`.parm` readers (bypass the tolerant lossless_parser). `python gate_common.py` builds + sanity-checks the map. |
| `track_a_offline.py` | offline build-correctness: build via `ToxBuilder` → real `toeexpand` → compare `.n` token + params vs the live capture + `td_validate`. `--seed` / `--all` / `--families` / `--resume`. |
| `track_b_driver.py` | live round-trip (runs INSIDE TD via `execute_python_script`): create via `td_create` → read back `n.type`/`n.family` → set perturbed params → record to a resumable JSONL → destroy. Driven in slices (set `_B_START`/`_B_END`/`_B_RESET`, then `exec` it in a merged globals+locals namespace). |
| `track_c_smoke.py` | search→build handoff: `hybrid_search`→`get_operator_info`→`get_parameter_detail`→build→`td_validate` over realistic briefs. |
| `build_gate.py` | merger: unifies A+B, generates `proposed_fixes`, emits `grounding_token_map.json`, computes the release verdict. |

The Track-D guardrail *prototype* that used to live here shipped for real as
`MCP/engine/validation/grounding_validator.py` (ValidationPipeline stage 2.5, W3a / PR #13);
the gate-side prototype is preserved at `quarantine/deadweight_2026_07/track_d_grounding_prototype.py`.

## Run
```
py -3.11 eval/build_gate/gate_common.py            # canonical map + sanity
py -3.11 eval/build_gate/track_a_offline.py --all  # offline, all ops (resumable)
# Track B: in TD, slice-by-slice exec track_b_driver.py (see its docstring)
py -3.11 eval/build_gate/track_c_smoke.py          # handoff smoke
py -3.11 eval/build_gate/build_gate.py             # merge + verdict + fixes
```

## Outputs (staged to `New KB build/Output/build_gate/`, never committed)
`canonical_op_map.json`, `track_a_offline.json`+`TRACK_A.md`+`track_a_results.jsonl`,
`track_b_results.jsonl`, `track_c_smoke.json`+`TRACK_C.md`, `grounding_token_map.json`,
`BUILD_GATE.json`+`BUILD_GATE.md` (verdict), `proposed_fixes.json`+`PROPOSED_FIXES.md`.
