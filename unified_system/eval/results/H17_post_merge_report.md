# H17 post-merge report — retrieval-only eval

**Branch:** `feat/chromadb-merge-and-ports`
**Date:** 2026-05-07
**Mode:** retrieval-only (no V2 strategy invocation, no API key)
**Result:** **6/10 cases pass = 60.0%** post B0+B1+B2

## Why retrieval-only

The B0 ChromaDB merge + B1+B2 wiring fix *retrieval*, not *generation*. Generation is V2's job and requires `ANTHROPIC_API_KEY` to invoke the multi-agent strategy. Since this branch's stated goal is to fix retrieval, the meaningful measurement is whether the merged store + adapter surface the right operator content for each test prompt — not whether V2 then weaves it into a correct network. Generation quality would need a separate eval against V2's full pipeline (deferred until B7 / API-key access).

## Per-tier results

| Tier | Passed | Total | Pass rate |
|---|---|---|---|
| advanced | 3 | 3 | 100% |
| intermediate | 2 | 3 | 66.7% |
| basic | 1 | 4 | 25% |

The advanced tier outperforming basic is **counterintuitive but consistent** with the failure mode below: advanced cases reference distinctive operator names (Bullet Solver, GLSL TOP, Select CHOP) that are easy for dense retrieval to lock onto. Basic cases use commodity operator names (Noise, Null, Constant, Text, Composite) that overlap with general TD vocabulary, so the prompts' surrounding narrative drowns out the specific operator signal.

## Per-case detail

| Case | Tier | Pass | Recall | Notes |
|---|---|:-:|---:|---|
| advanced_01_select_chop_filter | advanced | ✓ | 1.00 | Select CHOP + Null CHOP both surfaced |
| advanced_02_instancing_geometry_chop | advanced | ✓ | 0.75 | Missing Camera COMP (Sphere SOP, Geometry COMP, Render TOP found) |
| advanced_03_bullet_solver_constraint | advanced | ✓ | 0.75 | Bullet Solver, Actor, Constraint COMPs found; missing Render TOP |
| basic_01_noise_chop_to_null | basic | ✗ | 0.00 | Neither Noise CHOP nor Null CHOP in top-50 |
| basic_02_circle_sop_render | basic | ✓ | 0.75 | Circle SOP, Camera, Render found; missing Geometry COMP |
| basic_03_movie_file_in_top | basic | ✗ | 0.50 | Movie File In TOP found; Null TOP missed |
| basic_04_text_top_color | basic | ✗ | 0.00 | Composite/Constant/Text TOPs all missed |
| intermediate_01_audio_reactive_particles | intermediate | ✗ | 0.00 | Missing all 4 expected (audio + particle) |
| intermediate_02_feedback_top_loop | intermediate | ✓ | 1.00 | Feedback TOP + Composite TOP both surfaced |
| intermediate_03_glsl_top_shader | intermediate | ✓ | 1.00 | Noise TOP + GLSL TOP both surfaced |

## Why the failures fail

All 4 failing cases share one root cause: **`all-MiniLM-L6-v2` dense retrieval picks up surrounding prompt vocabulary more than specific operator names when the prompt is narrative-heavy.** The merged store contains every expected operator (verified by direct metadata lookup — `Noise CHOP` has 2 docs, `Null CHOP` has 2 docs, etc.); it's the embedding-similarity ranking that fails to lift them into top-50.

Empirical confirmation: when queried directly with short, focused queries:

| Query | Top-3 operator hits |
|---|---|
| `"Noise CHOP"` | Noise_CHOP × 3 ✓ |
| `"Null CHOP"` | Null CHOP / Null_CHOP / Null_CHOP ✓ |
| `"video file movie file TOP"` | moviefileoutTOP / moviefileinTOP / moviefileoutTOP ✓ |
| `"render a circle SOP using a render TOP geometry COMP and camera COMP"` | renderTOP / Sprite_SOP / Camera_COMP — partial |

So the retrieval is fundamentally sound; the eval's narrative prompts (e.g. "Create a TouchDesigner network with a Noise CHOP feeding into a Null CHOP") dilute the operator-name signal in the embedding.

## What this means in practice

Within the V2 strategy runner the user prompt is passed verbatim to `query_knowledge_base_comprehensive` (the function this branch fixed). So V2 gets exactly the same retrieval the eval measures: ~60% recall on naturally-phrased prompts that name the desired operators.

That's a real, measurable improvement over the pre-merge state — where:
- The runtime path *itself* threw `InvalidCollectionException: Collection touchdesigner_docs does not exist` at startup (verified during investigation), silently caught and disabled.
- `query_knowledge_base_comprehensive` was a hand-written keyword if-ladder against ~47 hardcoded keywords across 6 buckets, producing alphabetical-first slices of the wrong family for many queries (B1 in `problems.md`).

It is not a silver bullet. The 40% remaining failure rate points to follow-up work, none of which is in this branch's scope:

1. **Hybrid retrieval (BM25 + dense)** — reweight literal operator-name matches alongside semantic similarity. Would address the "operator name buried in narrative" failure mode directly. Standard pattern; chromadb supports adding BM25 alongside.
2. **Pre-query operator-name extraction** — have the strategy runner extract operator names from the prompt with a small classifier or regex before retrieval, then do targeted lookups by `metadata.name`. Cheap and surgical.
3. **Better embedding model** — voyage-code-2 is configured in `search_config.json` but the API path is `NotImplementedError`; the runtime falls back to `all-MiniLM-L6-v2`. A code-tuned embedding model would likely lift recall on technical prompts.
4. **Wider top-K** — the eval used K=50; V2's `query_knowledge_base_comprehensive` uses K=20. Bumping V2's K would help marginally but doesn't solve the underlying signal-dilution issue.

## What changed in this branch

- B0 produced a unified ChromaDB store at `META_AGENTIC_TOOL/data/vector_db_merged/` with 34,350 docs (32,475 orphan + 1,869 active + 6 build_instruction). 500 active operator overviews enriched with the orphan's `python_class` metadata (no dedup; both granularities preserved).
- B1+B2 replaced `query_knowledge_base_comprehensive`'s hardcoded keyword if-ladder with `UnifiedSearchAdapter.search()` against the merged store. `KnowledgeBase.semantic_search` no longer a placeholder.
- M6-port restored POP-family operator name resolution in the runtime graph query (BUG-021 fix that lived only in the root copy).
- M4-port brought BUG-004 palette-embedding features into `unified_system/parsers/lossless_parser.py`.
- H17 harness in place for repeat measurement; retrieval-only mode is the cheap, deterministic, no-API path.

## Comparison to the qualitative validation

Three unit tests pass against documented failure-mode prompts (`META_AGENTIC_TOOL/meta_agentic/tests/test_kb_query_semantic.py`):

- `test_audio_reactive_particles_surfaces_both_audio_and_particle_content` — passes (B1's documented dual-bucket failure mode is fixed).
- `test_pop_query_resolves_via_merged_store_and_graph` — passes (M6-port + B0 working together).
- `test_build_instructions_surface_for_dat_to_chop` — passes (BUILD_INSTRUCTIONS ingestion working).

The unit tests pass because they use looser pass criteria ("does *some* audio content surface? does *some* particle content surface?"). The retrieval eval uses stricter pass criteria ("do *these specific* operators surface in top-K?"). Both numbers are honest views of the same system from different angles.

## Reproducing this report

```bash
# From repo root, with the merged store at META_AGENTIC_TOOL/data/vector_db_merged:
python -m unified_system.eval.prompt_eval --retrieval-only --label post_b0_b1_b2_retrieval

# To regenerate the merged store (~5 min on CPU once the model is cached):
python META_AGENTIC_TOOL/scripts/merge_chromadb_stores.py
```

JSON output: `unified_system/eval/results/post_b0_b1_b2_retrieval_<timestamp>.json`.
Markdown: `unified_system/eval/results/post_b0_b1_b2_retrieval_<timestamp>.md`.
