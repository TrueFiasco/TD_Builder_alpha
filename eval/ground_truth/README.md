# eval/ground_truth — committed CI snapshot

`operator_types.json` (~60 KB) is a **wiki-scrape-derived** operator name list
(`{family -> [{name, td_create}]}`, 685 entries) — **NOT a live-TouchDesigner
capture.** Its `td_create` tokens are SYNTHESIZED by string-munging TouchDesigner
wiki page titles (the untracked
`New KB build\Resources\operator_ground_truth\extract_all_operators.py`), not read
from a running TD, so it includes 5 never-real "phantom" POPs — `Source_POP`, `Attractor_POP`,
`Drag_POP`, `Collision_POP`, `Kill_POP` — that carry no TD class and are absent
from the live operator registry (see the 2026-07-17 ground-truth audit). Treat it
as a permissive **name-integrity allowlist**, not as census ground truth.

`eval/run_eval.py`'s name-integrity gate requires it — `eval/predicates.py`
`GroundTruth.__init__` reads it unconditionally, so without this file the
retrieval eval cannot run on a fresh clone (e.g. the kb-full CI lane; see
`docs/CI.md`).

**The real live-capture corpus** is the (untracked) main-tree
`New KB build\Resources\operator_ground_truth\` — its `sampling_results.json`
(641 success / 0 failed / 44 skipped) and expanded-`.toe` evidence are the
actual per-operator TouchDesigner captures. That directory ALSO carries a copy of
this same wiki-scrape `operator_types.json`; **this committed file is a pinned
snapshot of that copy for CI**, not a second source of truth — local runs of
`run_eval.py` keep defaulting to the corpus copy; CI passes
`--gt-types eval/ground_truth/operator_types.json` explicitly.

- **TD build pin:** `0.99.2025.32460` — the KB v0.2 capture pin recorded in
  `KB/manifest.json` `td_build`. The wiki scrape itself is not version-locked;
  this pin describes the corpus harvest it was filed alongside.
- **Do NOT hand-regenerate for a census correction.** Dropping the phantom-5 and
  reconciling the 685-vs-663 count against a real live census is tracked as
  **W3 Census Lock** (board GT1), not a `Copy-Item`. The historical snapshot
  refresh (after a corpus re-harvest against a new TD pin — keep the two in
  lockstep, and re-run the eval + build gates when they move) was:

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
