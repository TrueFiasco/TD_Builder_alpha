# TD Builder — v0.2.0

A **key-free** Python system for AI-driven generation, validation, and conversion of
TouchDesigner networks, exposed to LLM clients as **two MCP servers**, plus live
TouchDesigner editing/feedback tools. Everything runs locally — **no API key required**.

## Folder layout

| Folder | What's in it |
|---|---|
| **`MCP/`** | The two MCP servers + all the code they run. `server.py` (offline) and `live_server.py` (live-TD) are the entry points; `server_core/` is the server brain, `engine/` is the TD-file engine, `live_client/` holds the live-TD client, `td-webserver/` is the TouchDesigner-side `.tox` asset. |
| **`KB/`** | The knowledge base (operator specs, graph, vector store, wiki guides). Fetched/placed on install — see `KB/README.md`. |
| **`Agents/`** | Expert prompts (`experts/`), learned expertise (`expertise/`), skills (`td-builder-howto/`, `td_network_analysis/`), and strategy notes (`Strategies/`). The server reads experts/expertise from here. |
| **`Tools/`** | LLM-facing documentation of every tool (`TOOLS.md` + the `KB tools/`, `Live tools/`, `offline Builder tools/`, `Other/` categories) and the offline CLI launchers. |
| **`Config/`** | User configuration: `.env.template`, `search_config.json`, and `SETTINGS.md`. |
| **`LLM/Pre-Prompts/`** | Reusable pre-prompts and when to use them. |
| `scripts/` | `fetch_vector_db.py` (downloads the KB bundle), `check_deps.py` (verifies your install). |
| `tests/` | Acceptance + smoke gate so you can confirm a working install. |

## The two MCP servers

| Server | Register as | Tools | When |
|---|---|---|---|
| `MCP/server.py` | `td-builder` | **18** key-free tools — KB search, `td_validate`/`td_convert`/`td_build_project`/`td_build_status`, `expand_toe_file`, `register_component`, `get_expert_prompt`, `get_server_info` | always |
| `MCP/live_server.py` | `td-builder-live` | **22** live tools — capture / node CRUD / introspection of a running TouchDesigner | only when TouchDesigner is open |

Keeping the live tools in a separate server means offline sessions don't carry their ~22 tool
schemas in the model's context. See [MCP/README.md](MCP/README.md) for the client config.

## Quick start (Windows + PowerShell)

> **Prerequisites:** Python 3.10–3.13 (3.11 recommended), TouchDesigner 2025+ (only for the live
> tools + final `.toe` collapse). See [PREREQUISITES.md](PREREQUISITES.md).

```powershell
# 1. Create a venv on Python 3.11
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install (single editable install + dev/test extras)
pip install -e ".[dev]"

# 3. Download the knowledge base (~108 MB zip) — public HTTPS, no GitHub account needed
python scripts\fetch_vector_db.py

# 4. Verify your install
python scripts\check_deps.py        # expect all green

# 5. Register the MCP server(s) with your client — see MCP/README.md
#    IMPORTANT: point the client's "command" at THIS venv's python
#    (<ROOT>\.venv\Scripts\python.exe; macOS/Linux: <ROOT>/.venv/bin/python) —
#    a bare "python" is the system interpreter and dies with ImportError.
#    Offline:  .venv\Scripts\python.exe MCP\server.py       (td-builder, 18 tools)
#    Live:     .venv\Scripts\python.exe MCP\live_server.py  (td-builder-live, 22 tools — only with TD open)
```

> **First run:** the first KB-dependent call loads the knowledge base (~180 MB) + the local embedding
> model + the bundled reranker (one-time, ~1–2 min), then every call is fast.

## Modes

There is **one mode: key-free**. KB semantic search uses a local embedding model
(`all-MiniLM-L6-v2`) — no Voyage/OpenAI/Anthropic key, no cloud calls. (Agent-spawning and the
multi-agent strategy runner were removed in this release; the experts ship as prompts you load via
`get_expert_prompt`.)

## Measured, not promised

The KB and builder are gated by a published eval harness ([eval/](eval/)) — every release must pass:

- **Build correctness**: offline-generated operators re-expanded through TD's own `toeexpand` and
  diffed against live-TD ground truth — **636/636 operator tokens exact** (verified by importing
  offline `.tox` files into a running TouchDesigner).
- **Retrieval quality**: labeled benchmark (recall@k / MRR / nDCG) with a frozen trend gate,
  held-out paraphrases against overfitting, and a coverage tier spanning **≥90% of operators in
  every family** (all 673 operators enumerated). Hybrid retrieval (dense + BM25 + reranker) took
  the aggregate score from 0.86 → 0.93 over dense-only.
- **Name integrity**: zero retokenized operator names in returned chunks (was 294 pre-redesign).

## Run the gate

```powershell
py -3.11 -m pytest tests\acceptance tests\measure -q   # ~22 checks; live tests need TD open
```

## Known limitations

- BASIC-mode `.toe` building (from-scratch networks) emits parameter-format warnings; the LOSSLESS
  round-trip path (the CLIs / `td_fixture_pipeline`) is solid.
- `td_build_project(palette=…)` is a known-broken path (deferred to a later release).
- See [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).

## License

TD Builder is licensed under the **GNU Affero General Public License v3.0 or later
(AGPL-3.0-or-later)** — see [LICENSE](LICENSE). Note AGPL **§13 (Remote Network Interaction)**: if you
run a modified version of these MCP servers for others to interact with over a network, you must offer
those users the Corresponding Source of your modified version.
