# kb_build — TD Builder v0.2 KB rebuild pipeline (Phase 1: anatomy)

Rebuilds the shipped KB as **condensed pointer chunks** that hydrate from a big
KB (operators.json + Resources) via the existing MCP tools. Implements the
approved plan (`plan-mode-task-redesign-serialized-kite.md`) §5/§6/§8/§9 Phase 1.

The pipeline reads **only** from the local build corpus
`New KB build/Resources/` and stages all output under
`New KB build/Output/KB/` — **never commit a built KB** (it ships as a
sha256-pinned release asset).

## Run

```sh
# build every implemented §6 section (additive, cumulative index)
py -3.11 kb_build/build_kb.py --sections all
# or a subset
py -3.11 kb_build/build_kb.py --sections palette,operators

# measure against the Phase-0 harness, pointing at the new build output
py -3.11 eval/run_eval.py --backend enhanced --repeats 5 \
  --kb "…/New KB build/Output/KB" \
  --gt-types "…/Resources/operator_ground_truth/operator_types.json" \
  --gt-operators "…/New KB build/Output/KB/operators.json"
```

## Layout

| file | §6 | produces (meta.type) |
|---|---|---|
| `common.py` | — | Identity join, chunk contract, MiniLM embed + Chroma `td_unified` round-trip |
| `build_kb.py` | — | orchestrator → `vector_db/`, `operators.json`, gpickle, `manifest.json`, `sources.lock.json` |
| `ingest_palette.py` | 6.4 | `block_overview` / `block_usecase` / `block_io` |
| `ingest_operators.py` | 6.1 / 6.2 | `operator_overview` / `parameter_group` |
| `ingest_python.py` | 6.3 | `class_method` / `python_pattern` / `callback` |
| `ingest_recipes.py` | 6.6 | `recipe` (authored, canonical) / `pattern` (td_network_patterns) |
| `ingest_examples.py` | 6.7 | `real_example` (OPSnippets) |
| `ingest_concepts.py` | 6.5 | `concept` |
| `ingest_build.py` | 6.9 | `build_instruction` |

Not yet implemented: §6.8 curriculum `lesson_pattern` (needs `expand_toe_file`
on the curriculum `.tox`; the howto metric is already met by §6.6 recipes).

## The chunk contract (why the meta keys are what they are)

The Phase-0 harness (`eval/predicates.py`) is the contract. Relevance + name
integrity read these `meta` keys, so every ingester must emit them:

- `type` — NOT `chunk_type` (predicates read `meta.type`).
- `__source_store` — `td_operator/td_param/td_python/td_block/td_concept/td_recipe/td_example/td_build`.
- `python_class`, `name`/`operator_name`, `family` — operator identity, JOINED
  from `operator_ground_truth` + `operators.json`. The **SPACED canonical name**
  is always emitted (never the underscored wiki-title form) so the name-integrity
  gate stays at 0 retokenized.
- `class` + `method` (class_method), `name` (python_pattern / callback / palette /
  concept-`term`), `parameter_group` + `parameters` (parameter_group).
- `parent_chunk` — persisted **inside meta** (the old pipeline computed it then
  dropped it at upsert).

**Name-integrity rule:** never set `python_class` to a base-class token
(`CHOP_Class` is not an operator python_class) or to a value absent from the
registry — that registers as an unresolved identity. class_method/python_pattern/
callback/concept chunks carry `class`/`method`/`name`/`term` only.

**Chroma round-trip:** the shipped `search_docs.TDDocSearch` opens
`PersistentClient(vector_db)`, `get_collection("td_unified")`, embeds queries with
raw `all-MiniLM-L6-v2` (no normalization, default L2 space), `score = 1 - distance`.
Metadata must be flat scalars (lists → pipe-joined, dicts → JSON, None dropped).
`build_kb` copies the shipped `knowledge_graph_enhanced.gpickle` into the output so
the adapter constructs (the harness scores only `semantic_results`, which is pure
vector search — the graph content does not affect the metrics; a re-grounded graph
rebuild is a separate pass).
