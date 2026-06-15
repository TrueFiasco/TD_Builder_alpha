# KB — TD Builder knowledge base

This folder is TD Builder's knowledge base. Most of it is **not committed to git** — the large
generated artifacts (~210 MB extracted, ~72 MB zipped) ship as a single GitHub Release asset and are fetched on install, which
keeps the repo lean.

## Populate it (one command)

```
python scripts/fetch_vector_db.py
```

Downloads `td_builder_kb_v0.1.1.zip` over public HTTPS (no API key, no `gh`, no GitHub account),
verifies its sha256, and extracts the four runtime files below into this folder. Re-running is a no-op
once populated. `python scripts/check_deps.py` confirms the result.

## Contents

| File / dir | What it is | Ships how |
|---|---|---|
| `operators.json` (~36 MB) | 673 enriched operator specs — the source of truth for validation + lookups | **fetched** |
| `graphrag.json` (~58 MB) | RAG chunks + wiki/operator graph used by semantic search | **fetched** |
| `knowledge_graph_enhanced.gpickle` (~9 MB) | The ~37k-node knowledge graph (operators, params, examples, patterns) | **fetched** |
| `vector_db/` (~110 MB) | ChromaDB vector store, embedded with **all-MiniLM-L6-v2** (local, key-free) | **fetched** |
| `wiki_supplemental/` | Hand-authored GLSL how-to guides (`Write_a_GLSL_TOP.md`, `Write_GLSL_POPs.md`, `Write_a_GLSL_Material.md`) | committed |
| `manifest.json` | KB bundle metadata (axes, sizes, md5s) | committed |

## Embedding model — do not change

The vector store was built with `all-MiniLM-L6-v2` (384-dim). Query-time embedding **must** use the
same model — it does by default (`EMBEDDING_PROVIDER=local` in `Config/.env`). Pointing the embedding
provider at a cloud model would mismatch the store and break search. This is what keeps the whole
system key-free.

## Notes

- The bundle is version-pinned + sha256-verified in `scripts/vector_db_release.json`; a new KB build
  bumps the tag + hash there.
- `sources/` (snippet/palette capture inputs) and the KB-build QA artifacts are **not shipped** — they
  live only in the dev repo.

See `docs/KB_CONTENTS.md` for the longer write-up.
