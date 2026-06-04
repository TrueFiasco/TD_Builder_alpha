# core/ — TD Builder engine surface

The engine is composed of three subsystem package roots that the MCP server
and CLI tools import by their top-level names (resolved via `bootstrap.py`):

| Import roots | Lives in | Role |
|---|---|---|
| `api`, `core`, `validation`, `builders`, `parsers` | `../unified_system/` | Lossless `.toe` parser, 5-stage validator, format converter, LOSSLESS/BASIC builder |
| `meta_agentic` (+ `experts/`, `expertise/`) | `../META_AGENTIC_TOOL/meta_agentic/` | Strategy runner, expert executor, blackboard |
| td-mcp dependency modules | `../td-mcp/` | Agents/builder/validation helpers on the server import path |

These are **not** flattened into this folder on purpose (alpha hybrid layout):
the verified MCP server resolves the consolidated KB bundle and its sibling
search stack via `__file__`-relative paths, so the subsystem dirs stay intact
and are wired together by `bootstrap.py` (single PYTHONPATH surface) and
`MCP/python/server.py` (the launcher). Treat this README as the map of the
engine; deep physical flattening is a post-alpha refactor.

Canonical knowledge base: `../KB/` (operators.json / graphrag.json /
knowledge_graph_enhanced.gpickle / vector_db/ + sources/ + meta/). See
`../KB/KBU_REPORT.md` and `../KB/manifest.json`.
