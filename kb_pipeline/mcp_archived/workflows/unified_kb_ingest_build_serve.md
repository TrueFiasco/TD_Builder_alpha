# Workflow: Unified KB (Ingest → Enrich → Index → Serve)

## Goal
Keep the TD assistant clean by treating `C:\TD_Projects\kb_pipeline` as the **only** runtime knowledge base, built from three source families (docs/snippets/palette).

## Step 1 — Ingest (copy/normalize sources)
- Docs (source-of-truth): `C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca\td_universal_parsed.json`
  - Optionally copy into `C:\TD_Projects\kb_pipeline\data\wiki_docs\td_universal_parsed.json` to make the KB fully portable.
- Snippets:
  - Copy `index.tsv` into `C:\TD_Projects\kb_pipeline\data\snippets\index.tsv`
  - Copy semantic snippet JSONs into `C:\TD_Projects\kb_pipeline\data\snippets\semantic\`
- Palette:
  - Copy semantic palette JSONs into `C:\TD_Projects\kb_pipeline\data\palette_semantic\`
  - Copy palette wiki HTML into `C:\TD_Projects\kb_pipeline\data\palette_wiki\`

## Step 2 — Enrich (join + meaning layer)
Outputs go in `C:\TD_Projects\kb_pipeline\index\`:
- Join snippet `index.tsv` → snippet examples (curator summaries)
- Extract palette summaries from HTML (already supported by `extract_palette_summaries.py`)
- Optional: run an LLM summarizer to produce `llm_summary` for snippets/palette (store separately; do not change semantic JSON schemas)

## Step 3 — Index (vector + graph)
Build:
- Vector DB (documents for embeddings):
  - docs: operator overview + parameter tier chunks
  - snippets: curator summary + lightweight graph summary (avoid parameter noise)
  - palette: wiki summary + component tags
- Graph:
  - operator nodes, example/component nodes, relations (`example_of`, `contains`, `connection`)

### Commands (known-good)
- Rebuild vector text index (no embeddings, fast):
  - `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe C:\TD_Projects\kb_pipeline\build_vectors.py --fallback-only`
- Rebuild local embeddings (writes `vector_db/embeddings.npy`):
  - `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe C:\TD_Projects\kb_pipeline\generate_embeddings_simple.py`
- Create ChromaDB from existing embeddings (optional, one-time):
  - `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe C:\TD_Projects\kb_pipeline\create_chroma_from_embeddings.py --out C:\TD_Projects\kb_pipeline\vector_db_chroma`
- Rebuild operator index + merged graph (requires Py311 because NetworkX breaks on Py3.14):
  - `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe C:\TD_Projects\kb_pipeline\build_graph.py`

## Step 4 — Serve (one MCP tool)
Run a single MCP server (recommended: `kb_pipeline/mcp/unified_mcp_server.py`) that reads:
- `vector_db/` (vector search)
- `graph/td_knowledge_graph_simple.json` (graph expansion)
- `index/` (file pointers + enrichment)

### Command
- `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe C:\TD_Projects\kb_pipeline\mcp\unified_mcp_server.py`

## Notes
- If you standardize runtime on Python 3.11 (TouchDesigner’s Python), you can use ChromaDB as the single vector store.
- Builder workflows should use templates and round-trip validation (expand/collapse) for rigor.
