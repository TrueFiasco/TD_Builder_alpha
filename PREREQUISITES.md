# Prerequisites

## Required

| Requirement | Version / notes |
|---|---|
| **Python** | `>=3.10,<3.14`. **3.11 recommended.** Python 3.14+ is **not supported** (ChromaDB / its deps). |
| **pip packages** | `pip install -e ".[dev]"` from the release root. Core deps: `mcp`, `sentence-transformers`, `chromadb`, `numpy`, `scikit-learn`, `networkx`, `pyyaml`, `jsonschema`, `httpx`. **No API-key packages** — this release is key-free. |
| **An MCP-capable client** | Claude Desktop, ChatGPT Desktop, or Cursor (see `docs/SETUP/` and `MCP/README.md`). |

## Required only for some features

| Feature | Needs |
|---|---|
| The knowledge base (semantic search + operator/graph data) | `python scripts/fetch_vector_db.py` (public HTTPS download, ~72 MB) |
| Live-TD tools (`create_td_node`, `capture_top_output`, …) via the `td-builder-live` server | **TouchDesigner 2023+** running, with `MCP/td-webserver/mcp_webserver_base.tox` imported (WebServer DAT on `http://127.0.0.1:9981`; override via `TD_API_URL`). |
| Final `.toe` file (not just `.toe.dir`) | TouchDesigner's `toecollapse` CLI (ships with TD). |

> There is **no API key** anywhere in this release. KB search uses a local embedding model.

## Verify the install

```powershell
python scripts\check_deps.py     # green checklist: Python, deps, KB present
py -3.11 -m pytest tests\acceptance tests\measure -q   # ~21 checks (live tests need TD open)
```
