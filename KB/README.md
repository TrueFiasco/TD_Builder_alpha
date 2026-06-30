# KB — TD Builder knowledge base

This folder is TD Builder's knowledge base. Most of it is **not committed to git** — the large
generated artifacts (~180 MB extracted, ~108 MB zipped) ship as a single GitHub Release asset and are
fetched on install, which keeps the repo lean.

## Populate it (one command)

```
python scripts/fetch_vector_db.py
```

Downloads `td_builder_kb_v0.2.0.zip` over public HTTPS (no API key, no `gh`, no GitHub account),
verifies its sha256, and extracts the runtime artifacts below into this folder. Re-running is a no-op
once populated. `python scripts/check_deps.py` confirms the result.

## Contents

| File / dir | What it is | Ships how |
|---|---|---|
| `operators.json` (~34 MB) | Enriched operator specs — the source of truth for validation + lookups | **fetched** |
| `knowledge_graph_enhanced.gpickle` (~9 MB) | The knowledge graph (operators, params, examples, patterns) | **fetched** |
| `vector_db/` (~41 MB) | ChromaDB vector store — 6,447 condensed pointer chunks, embedded with **all-MiniLM-L6-v2** (local, key-free) | **fetched** |
| `lexical_index/bm25.pkl` (~8 MB) | BM25 lexical index backing hybrid (dense + sparse) retrieval | **fetched** |
| `models/ms-marco-MiniLM-L-6-v2/` (~87 MB) | Bundled cross-encoder reranker (offline, key-free) | **fetched** |
| `sources.lock.json` | Build provenance (pinned source revisions) | **fetched** |
| `wiki_supplemental/` | Hand-authored GLSL how-to guides (`Write_a_GLSL_TOP.md`, `Write_GLSL_POPs.md`, `Write_a_GLSL_Material.md`) | committed |
| `docked_dats.json` | Per-op docked-DAT specs used by the builder | committed |
| `manifest.json` | KB bundle metadata (sections, chunk histogram, retrieval stack) | committed |

## Retrieval stack (v0.2)

Search runs a hybrid pipeline: **dense (all-MiniLM-L6-v2) + BM25 → RRF(k=60) → operator-aware router →
cross-encoder rerank → calibrated score-floor + dedup** (see `MCP/server_core/search/retrieval_stack.py`).
The `graphrag.json` chunk file from v0.1.x is gone — those chunks now live as condensed pointer chunks in
`vector_db/` and hydrate from `operators.json` at query time.

## Embedding model — do not change

The vector store was built with `all-MiniLM-L6-v2` (384-dim). Query-time embedding **must** use the
same model — it does by default (`EMBEDDING_PROVIDER=local` in `Config/.env`). Pointing the embedding
provider at a cloud model would mismatch the store and break search. This is what keeps the whole
system key-free. (The bundled `models/` reranker is a *cross-encoder*, not the embedder.)

## Notes

- The bundle is version-pinned + sha256-verified in `scripts/vector_db_release.json`; a new KB build
  bumps the tag + hash there.
- `sources/` (snippet/palette capture inputs) and the KB-build QA artifacts are **not shipped** — they
  live only in the dev repo.

See `docs/KB_CONTENTS.md` for the longer write-up.
