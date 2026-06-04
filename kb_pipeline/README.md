Unified TouchDesigner Knowledge Pipeline
========================================

Goal: one place to ingest docs/wiki, OP Snippets, and Palette tox files into a single knowledge graph, a single vector DB, and a single MCP tool.

Directory layout
- Parsers_Builders_Embedders/ >Parsers_Builders_Embedders used to gather sort and embed data.
- raw_docs/           -> source docs (e.g., Learn/OfflineHelp/https.docs.derivative.ca/)
- raw_snippets/       -> OPSnippets Snippets
- raw_palette/        -> Palette tox files
- lossless/{snippets,palette}/   -> lossless JSON outputs
- semantic/{snippets,palette}/   -> semantic JSON outputs
- index/              -> mapping/index files (operator -> files, summaries)
- graph/              -> merged graph outputs (gpickle + json)
- vector_db/          -> numpy vector artifacts (vector_index.json + embeddings.npy)
- vector_db_chroma/   -> optional ChromaDB built from embeddings.npy
- logs/               -> pipeline logs
- mcp/                -> MCP server/config that points to the merged graph/vector

Source paths (current defaults used by scripts)
- Docs: C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca\td_universal_parsed.json
- Snippet semantics: C:\TD_Projects\kb_pipeline\data\snippets\semantic
- Palette semantics: C:\TD_Projects\kb_pipeline\data\palette_semantic

Scripts (in this folder)
- build_graph.py
  - Merges doc operators (and summaries) with snippet/palette examples into one NetworkX graph.
  - Outputs: graph/td_knowledge_graph_merged.gpickle and graph/td_knowledge_graph_merged.json
- build_vectors.py
  - Collects text chunks from docs + snippet/palette example summaries for embedding.
  - Outputs: vector_db/vector_index.json (chunk index). If Chroma is available in the runtime, it can also build a Chroma collection.

MCP integration
- Point the MCP server to the merged graph in kb_pipeline/graph and the vector DB in kb_pipeline/vector_db.
- Tools should read from one index (kb_pipeline/index) to resolve file paths to lossless/semantic JSON.

Notes
- Existing lossless/semantic JSON formats are left unchanged; extra summaries live in index files.
- Set PYTHONIOENCODING=utf-8 when running converters to avoid encoding errors.

Python runtime notes
- **Python >=3.10,<3.14 REQUIRED** (BUG-018)
- Python 3.14+: NOT SUPPORTED - ChromaDB uses Pydantic V1 which is incompatible
- Python 3.11 (TouchDesigner): recommended unified runtime for KB tools; see `C:\TD_Projects\kb_pipeline\.venv_py311`.
