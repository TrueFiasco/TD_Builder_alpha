# eval/ground_truth — the census, and the operator list generated from it

Two committed files, one generated from the other:

| file | what it is |
|---|---|
| `td_census.json` (~52 KB) | a versioned dump of **TouchDesigner's own `families[]` class registry** at build `099.2025.32820` — the creatable-operator authority, 647 entries, plus each operator's inheritance chain. Captured by `scripts/capture_td_census.py`. This is CI's stand-in for a live TouchDesigner. |
| `operator_types.json` (~48 KB) | `{family -> [{name, td_create}]}`, **647 entries, generated from the census** by `kb_build/gen_operator_types.py`. It is a subset of reality **by construction**. |

`eval/predicates.py` `GroundTruth.__init__` reads `operator_types.json`
unconditionally, so without it the retrieval eval cannot run on a fresh clone
(the kb-full CI lane; see `docs/CI.md`).

## What changed, and why it mattered

Until W3 Census Lock this file was a **wiki scrape**. Its `td_create` tokens were
synthesized by string-munging wiki page titles, and it was wrong in *both*
directions:

- it **invented 13 operators** that have never existed — `Source_POP`,
  `Attractor_POP`, `Drag_POP`, `Collision_POP`, `Kill_POP`, `Add_POP`,
  `Velocity_POP`, `Analyze_DAT`, `Fuse_SOP`, `Mirror_SOP`, `Normals_SOP`,
  `Scatter_SOP`, `Gradient_TOP` (the first five were the known set; the census
  surfaced the other eight);
- it **omitted 7 real ones**;
- it carried **6 tutorial articles** as if they were operators (`Write_a_*`);
- and it double-counted one operator under two spellings (`FIFO_DAT` and
  `Fifo_DAT`), which is why its own header said 685 while it held 684 distinct
  tokens.

The harm was not a retrieval miss. A model asked to receive FreeD camera-tracking
data found the retired `FreeD CHOP`, tried it, and got a node that would not
create — while the operator that actually does the job, `freedinCHOP`, was
invisible. A miss degrades gracefully; a confident wrong answer does not.

## The three counts — which is which

Live-verified against `families[]` at **099.2025.32820**, twice.

| number | what it actually is |
|---|---|
| **647** | **TouchDesigner's creatable operator count** — CHOP 165 · TOP 146 · SOP 112 · DAT 71 · COMP 40 · MAT 13 · POP 100. Quote this for "how many operators does TD have". Also the size of `operator_types.json`. |
| **663** | entries in `KB/operators.json` — *not* a TD count. 23 fossils, 7 missing, so `663 − 23 + 7 = 647`. |
| **640** | **KB coverage** of the census (663 − 23). Quote this for "how much does the KB cover". |

`scripts/census_guard.py` asserts all three mechanically, and
`scripts/docs_lint.py` checks that the docs quoting them still agree.

## Regenerating

```powershell
# 1. capture the registry (needs TouchDesigner RUNNING and NOT minimized --
#    a minimized TD accepts the socket but never answers)
py -3.11 scripts/capture_td_census.py --dry-run   # verify 647 first
py -3.11 scripts/capture_td_census.py

# 2. regenerate the operator list from it (needs a local TD install for names)
py -3.11 kb_build/gen_operator_types.py
py -3.11 kb_build/gen_operator_types.py --check   # byte-identical?

# 3. re-verify
py -3.11 scripts/census_guard.py
py -3.11 scripts/census_guard.py --self-test
```

The capture **refuses to write** if the total moves off 647 unless you pass
`--allow-count-change --reason "..."`. A count change is either a TD upgrade or a
broken capture, and the second is far more likely.

### The two sources, and what each is authoritative for

| source | authoritative for | caveat |
|---|---|---|
| live `families[]` registry | **what is creatable** (647) | needs TD running |
| offline help **operator** pages | **how names are spelled** (647/647) | a documentation superset — it retains pages for retired ops (`Font_SOP.htm`, `CUDA_TOP.htm`), so it is not a creatable list |
| offline help **class** pages | *nothing* | **under half complete**: 1,442 `*_Class` names are referenced, only 656 ship. `Bind_CHOP.htm` links `bindCHOP_Class`, which is not in the tree at all. Do not use it to arbitrate class names — use live TD. |
| wiki scrape | *nothing* | invents and omits |

The intersection is what makes both failure modes cancel: the registry excludes
phantoms and fossils, the help tree guarantees every real operator has a name.
Names are **not** derivable from the OPType (`rerangePOP` → `ReRange_POP`,
`choptoPOP` → `CHOP_to_POP`, `oakselectPOP` → `OAK_Select_POP`) and TD's own
spelling is inconsistently cased (`NVIDIA_Flex_TOP` but
`Nvidia_Flow_Emitter_COMP`), so the join normalises to alphanumerics. The
generator **aborts** rather than synthesising a name it cannot find.

> Use the **versioned** help path
> `C:\Program Files\Derivative\TouchDesigner.2025.32820\Samples\Learn\OfflineHelp\https.docs.derivative.ca\`.
> The unversioned `...\Derivative\TouchDesigner\` directory is a *different*
> (older, 32460) build on maintainer machines. `TCP/IP_DAT.htm` nests into a
> subdirectory because its page name contains a slash.

## Still outstanding — W7c's worklist

These are KB **content** changes; they need a re-embed and are not this file's job.

**23 fossils in the KB** (retired or renamed away): `Band EQ CHOP`,
`Parametric EQ CHOP` (→ `audiobandeqCHOP`/`audioparaeqCHOP`), `FreeD CHOP`,
`Stype CHOP` (→ `freedinCHOP`/`stypeinCHOP`), `EtherDream CHOP`,
`Helios DAC CHOP`, `RealSense CHOP`, `Scan CHOP`, `wrnchAI CHOP`,
`Build a List COMP`, `Impulse Force COMP`, `Indices DAT`, `UDT In DAT`,
`UDT Out DAT`, `Web DAT`, `Force POP`, `GLSL Create POP`, `Line Thick POP`,
`Font SOP`, `CUDA TOP`, `Layer TOP`, `SVG TOP`, `Simple Render TOP`.

**7 real ops the KB is missing:** `freedinCHOP`, `stypeinCHOP`, `tcpipDAT`,
`alembicoutPOP`, `textPOP`, `tracePOP`, `triangulatePOP`.

Both lists are pinned as allowlists in `scripts/census_guard.py`, with anti-rot
checks: an entry that stops being a hole (or a fossil) is itself a finding, so
the lists cannot silently accumulate dead names.

## Provenance and licensing

- **TD build pin:** `099.2025.32820`, recorded **inside** `td_census.json` (not
  only in this prose) so tests can assert it. Note `KB/manifest.json` still pins
  the KB's own capture at `0.99.2025.32460` — the KB is 360 builds older, which
  is why a few "fossils" are really cross-version renames.
- **Licensing note:** committed with owner sign-off (2026-07-04, extended to the
  census 2026-07-18). The content (operator display names, class names, and the
  inheritance chain) is a strict subset of the information already published in
  the v0.2.0 release asset's `operators.json` and in TouchDesigner's own shipped
  documentation.

## The corpus, and the twin that used to live there

The per-operator **live-capture corpus** is the untracked main-tree
`New KB build\Resources\operator_ground_truth\` — `sampling_results.json`
(641 success / 0 failed / 44 skipped), `params/` and `tox_expanded/` (~31 MB).
That directory stays untracked on purpose: it feeds the build gate's Track A,
which needs TouchDesigner's `toeexpand`/`toecollapse` binaries and cannot run on
hosted CI at all.

It also used to hold a byte-identical **copy** of `operator_types.json`. CI read
the tracked file; every local default read the copy. They agreed only by being
identical — so regenerating either would have made local runs and CI grade
against different ground truth, silently. Since W3 every resolver prefers the
tracked file (`paths.operator_types_path()`), with the corpus path kept only as a
legacy fallback, and `tests/unit/test_ground_truth_no_twin.py` fails if any
source file starts constructing the corpus path again.

**The `params/` and `tox_expanded/` directories still resolve from the corpus** —
only the operator list moved. Never derive one from the other's parent.
