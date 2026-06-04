# Unified TouchDesigner Knowledge Base (KB) - PDR

## Objective
Build and maintain **one** local TouchDesigner knowledge base that supports:
- **Retrieval**: one hybrid search interface over **all sources** (vector + graph).
- **Grounded answers**: every answer cites its provenance (docs/snippets/palette).
- **Building**: generate either (a) TouchDesigner Text DAT Python scripts, or (b) expanded `.toe/.tox` projects that can be collapsed with `toecollapse.exe` (rigorous, template-based).

## Primary Data Sources (must be preserved)
1) **Offline docs/wiki pages**
   - Contains operator docs, concepts, classes, how-tos.
   - Source-of-truth file: `C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca\td_universal_parsed.json`

2) **OP Snippets**
   - Ground-truth example networks + human-written summaries in `index.tsv`.
   - Canonical sources:
     - `C:\TD_Projects\kb_pipeline\data\snippets\index.tsv`
     - `C:\TD_Projects\kb_pipeline\data\snippets\semantic\*_semantic.json`
   - Optional (for builder): lossless exports stored separately (do **not** change schema).

3) **Palette toxs + palette wiki pages**
   - Palette `.tox` components + their offline wiki HTML pages.
   - Canonical sources:
     - `C:\TD_Projects\kb_pipeline\data\palette_semantic\*_semantic.json`
     - `C:\TD_Projects\kb_pipeline\data\palette_wiki\Palette-*.htm`

## Non-negotiables
- **Do not change** existing lossless/semantic JSON formats (treat them as stable contracts).
- Every derived/enriched artifact must be **rebuildable** from canonical sources.
- Every record must carry provenance: `source`, `path`, and (when applicable) `operator_type` / `palette_name` / `relpath`.
- Builder path must end in a verified `toecollapse.exe` output that can be `toeexpand.exe`’d again.

## What “Semantic” Should Mean (and what it should NOT)
### Semantic JSON (stable contract)
Purpose: a compact, structured representation of a snippet/palette network that is:
- Searchable (operators, connections, key parameters),
- Indexable (consistent IDs/metadata),
- Suitable as input to *further* summarization/enrichment.

Semantic JSON is **not** the final “human explanation”.

### Human-facing “Meaning” Layer (derived, allowed to evolve)
Store this separately (index/enrichment files), e.g.:
- `curator_summary` from `index.tsv`
- `llm_summary` (short, human-readable)
- `network_explanation` (what each connection/parameter is doing)
- `key_ops`, `key_params`, `dataflow`

These must NOT require changing the semantic/lossless JSON schemas.

## Canonical Storage Layout (single source-of-truth)
Keep `kb_pipeline` self-contained:
- `data/wiki_docs/` docs JSON (or symlink/copy of `td_universal_parsed.json`)
- `data/snippets/index.tsv`
- `data/snippets/semantic/*.json`
- `data/palette_semantic/*.json`
- `data/palette_wiki/*.htm`
- `index/` mapping and enrichment outputs (safe place for extra metadata)
- `vector_db/` one vector store backend (choose one; see below)
- `graph/` one graph representation used by retrieval

## Unified IDs (critical)
Define stable IDs so vectors, graph, and index all agree:
- Docs operator:
  - `op::{operator_name}` (e.g. `op::analyzeCHOP`)
- Snippet example:
  - `snippet::{operator_type}::{example_name}` (e.g. `snippet::analyzeCHOP::example3`)
- Palette component:
  - `palette::{palette_name}` (e.g. `palette::bloom`)

IDs must not depend on array indices or incidental ordering.

## Retrieval Contract
One tool entrypoint (MCP) must support:
- vector retrieval over doc + snippet + palette “meaning text”
- optional graph expansion for related ops/components
- filters: `source`, `family/category`, `difficulty`, `min_popularity`
- return results with provenance + pointers to raw/semantic/lossless files when relevant

## Vector DB: choose ONE backend
### Option A (current): numpy + JSON index (already working)
- Pros: simple, fast, no dependencies
- Cons: custom code; no built-in filtering/query features

### Option B: ChromaDB (recommended long-term)
- Pros: standard vector DB, metadata filtering, persistence, tooling
- Cons: requires Python environment compatible with Chroma (use Py311 venv)

Decision: migrate only if MCP runtime is standardized on Py311 (recommended anyway, matches TouchDesigner).

## Graph: choose ONE representation
- Use the existing lightweight JSON adjacency representation:
  - `graph/td_knowledge_graph_simple.json`
- Keep NetworkX graphs as optional build artifacts only (not runtime-critical).

## Build/Enrichment Pipeline (4 steps)
1) **Ingest**: copy/normalize sources into `kb_pipeline/data/` (no schema changes)
2) **Enrich**: generate indexes + summaries into `kb_pipeline/index/`
   - join `index.tsv` → snippet examples
   - palette wiki HTML → palette components
   - (optional) LLM-generated `llm_summary` per example/component
3) **Index**: build the vector DB + graph from canonical + enrichment
4) **Serve**: one MCP server reads `vector_db/` + `graph/` + `index/`

## Acceptance Criteria
- A new machine can clone/copy `kb_pipeline/` and run:
  - `td_assistant action=query ...` successfully without referencing external paths
- Queries for a snippet return:
  - curator summary (when available)
  - compact network summary (dataflow + key ops)
  - paths to semantic (and lossless if available)
- Builder workflows can round-trip a template:
  - expand → lossless → edit → rebuild dir/toc → collapse → expand (sanity)

