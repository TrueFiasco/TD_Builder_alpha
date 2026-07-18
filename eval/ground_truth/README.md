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

## The three operator counts — which is real

Re-verified live 2026-07-17 against TouchDesigner **099.2025.32820**'s own
`families[]` registry (the creatable-operator authority):

| number | what it actually is |
|---|---|
| **647** | **TouchDesigner's real creatable operator count** — CHOP 165 · TOP 146 · SOP 112 · DAT 71 · COMP 40 · MAT 13 · POP 100. **This is the count to quote for "how many operators does TD have".** |
| **663** | entries in `KB/operators.json` — *not* a TD count. It carries **23 fossils** (names not creatable in this build) and is **missing 7** real ops, so `663 − 23 + 7 = 647`. Real KB coverage is **640 of 647**. |
| **685** | entries in this wiki-scraped `operator_types.json` — **not a superset**; it is wrong in *both* directions. It invents the 5 phantom POPs **and** omits 4 real ones (`textPOP`, `tracePOP`, `triangulatePOP`, `alembicoutPOP`). Never treat it as a coverage floor. |

### Why the KB has holes — and where the correct source already lives

The 4 missing POPs above are exactly 4 of the KB's 7 coverage holes: the KB
inherited them from this scrape. But TouchDesigner **ships** authoritative docs
locally, at
`C:\Program Files\Derivative\TouchDesigner\Samples\Learn\OfflineHelp\https.docs.derivative.ca\`
— and that tree covers **647 of 647** live operators (`Text_POP.htm`,
`Trace_POP.htm`, `Triangulate_POP.htm`, `Alembic_Out_POP.htm` all present; note
`TCP/IP_DAT.htm` is nested because its page name contains a slash). It also has
**no page for any of the 5 phantom POPs** — an independent confirmation that
they were never real.

So the two reliable sources are already on disk, and they are complementary:

| source | authoritative for | caveat |
|---|---|---|
| live `families[]` registry | **what is creatable** (647) | needs TD running |
| offline help tree | **what is documented** (647/647) | retains pages for retired ops (`Font_SOP.htm`, `CUDA_TOP.htm`, `UDT_In_DAT.htm`), so it is a documentation superset, not a creatable list |
| wiki scrape | *nothing* | invents and omits |

**Recommendation for W3 Census Lock:** seed the operator set from the live
registry (creatable truth) and take documentation from the offline help tree —
never from the wiki scrape. That combination structurally excludes phantoms (no
page **and** not creatable) and closes holes (page **and** creatable).

**23 fossils in the KB** (retired or renamed away): `Band EQ CHOP`,
`Parametric EQ CHOP` (→ `audiobandeqCHOP`/`audioparaeqCHOP`), `FreeD CHOP`,
`Stype CHOP` (→ `freedinCHOP`/`stypeinCHOP`), `EtherDream CHOP`,
`Helios DAC CHOP`, `RealSense CHOP`, `Scan CHOP`, `wrnchAI CHOP`,
`Build a List COMP`, `Impulse Force COMP`, `Indices DAT`, `UDT In DAT`,
`UDT Out DAT`, `Web DAT`, `Force POP`, `GLSL Create POP`, `Line Thick POP`,
`Font SOP`, `CUDA TOP`, `Layer TOP`, `SVG TOP`, `Simple Render TOP`.

**7 real ops the KB is missing:** `freedinCHOP`, `stypeinCHOP`, `tcpipDAT`,
`alembicoutPOP`, `textPOP`, `tracePOP`, `triangulatePOP`.

Reconciling the KB's content (retiring fossils, adding the holes) is
**W3 Census Lock** (board GT1/GT5) — this file only records the measurement.

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
