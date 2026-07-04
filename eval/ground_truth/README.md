# eval/ground_truth — committed CI snapshot

`operator_types.json` (~60 KB) is the live-TouchDesigner operator registry
(`{family -> [{name, td_create}]}`, 685 operators) that `eval/run_eval.py`'s
name-integrity gate requires — `eval/predicates.py` `GroundTruth.__init__`
reads it unconditionally, so without this file the retrieval eval cannot run
on a fresh clone (e.g. the kb-full CI lane; see `docs/CI.md`).

**Authoritative copy:** the main-tree ground-truth corpus at
`New KB build\Resources\operator_ground_truth\operator_types.json`
(untracked; captured from live TouchDesigner during the KB v0.2 ground-truth
harvest). **This committed file is a pinned snapshot of it for CI**, not a
second source of truth — local runs of `run_eval.py` keep defaulting to the
corpus copy; CI passes `--gt-types eval/ground_truth/operator_types.json`
explicitly.

- **TD build pin:** `0.99.2025.32460` (same capture pin as `KB/manifest.json`
  `td_build` and the rest of the operator_ground_truth corpus).
- **Regeneration** (after a corpus re-harvest against a new TD pin — keep the
  two in lockstep, and re-run the eval + build gates when they move):

  ```powershell
  # from the main tree root
  Copy-Item "New KB build\Resources\operator_ground_truth\operator_types.json" `
            "eval\ground_truth\operator_types.json"
  ```

- **Licensing note:** committed with owner sign-off (2026-07-04). The content
  (operator display names + `td_create` class names) is a strict subset of the
  information already published in the v0.2.0 release asset's `operators.json`.

The rest of the corpus (`tox_expanded/`, `params/`, ~31 MB) stays untracked on
purpose: it feeds the build gate's Track A, which needs TouchDesigner's own
`toeexpand`/`toecollapse` binaries and therefore cannot run on hosted CI at
all — see the build-gate disposition in `docs/CI.md`.
