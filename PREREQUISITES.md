# Prerequisites

## Required

| Requirement | Version / notes |
|---|---|
| **Python** | `>=3.10,<3.14`. **3.11 recommended** (matches TouchDesigner 2023+). Python 3.14+ is **not supported** — ChromaDB depends on Pydantic V1. |
| **pip packages** | `pip install -r META_AGENTIC_TOOL\requirements.txt` and `pip install -r td-mcp\requirements.txt`. Core deps: `mcp`, `anthropic`, `sentence-transformers`, `chromadb`, `numpy`, `scikit-learn`, `pyyaml`, `httpx`. |
| **An MCP-capable client** | One of: ChatGPT Desktop, Claude Desktop, Cursor (see `docs/SETUP/`). |

## Required only for some features

| Feature | Needs |
|---|---|
| `td-validate` / `td-convert` / `td-build` CLIs | `pip install -e .\unified_system` |
| Live-TD tools (`create_td_node`, `capture_op_viewer`, `execute_python_script`, …) | **TouchDesigner 2023+** running, with `network-editor-mcp\td\mcp_webserver_base.tox` imported. Its WebServer DAT listens on `http://127.0.0.1:9981` (override with the `TD_API_URL` env var). |
| Final `.toe` file (not just `.toe.dir`) | TouchDesigner's `toecollapse` CLI (ships with TD). |
| `spawn_engineer` / `spawn_expert` (agentic tools) | An `ANTHROPIC_API_KEY` environment variable. **Mode 2 only** — see [MODES.md](MODES.md). All other tools work without any API key. |

## Verify the install

```powershell
python -c "from meta_agentic.execution.expert_executor import EXPERT_CONFIGS; print(list(EXPERT_CONFIGS.keys()))"
# Expect: ['creative_expert','cg_expert','critic','td_designer','td_glsl_expert','network_builder','summary_generator','td_python_expert']

pytest unified_system\tests\          # 55 tests should pass
```

> Run the `python -c` check with the PYTHONPATH from your `docs/SETUP/` guide,
> or from inside `META_AGENTIC_TOOL\`.
