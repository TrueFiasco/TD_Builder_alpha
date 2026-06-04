# Gate A — Harness Fitness Report

Date: 2026-05-17 · Interpreter: `C:\Users\Jake\AppData\Local\Python\pythoncore-3.11-64\python.exe` (Python 3.11.9, `mcp` ok, pytest 9.0.3)

## Headline

The measure harness is **largely reuse-as-is**. `pytest tests/measure` = **8 passed, 1 skipped** (95.8s). Nothing is broken. The plan's #1 risk ("unproven harness — emit/Probe/conftest/load_server may be unfit") is **substantially retired**. Two small WRAPs and one important plan correction below.

## Per-piece verdicts

| Piece | Verdict | Evidence / note |
|---|---|---|
| `tests/conftest.py` (root) | **reuse-as-is** | Collected in 0.07s, imports clean; 8 tests passed (does NOT silently skip all). `server`/`probe`/`td_live`/`has_api_key`/`promote` fixtures functional. |
| `_server.load_server()` | **reuse-as-is** | Server imports under pythoncore-3.11-64; **37 MCP tools** (19 TD-Live). Smoke tests pass (`server_identity`, `tool_inventory`, `validate_runs_five_stages`). |
| `harness.emit()` + baselines | **reuse-as-is** | Writes timestamped JSON+MD to `tests/measure/results/`; round-trips 4 baselines in `tests/measure/baselines/`; delta works. (glsl before/after still gets its own report layer *on top*, as planned — `emit` itself is fit.) |
| `probe.py` `Probe.call()` | **reuse-as-is (+1 wrap)** | Reaches KB/build **and** live tools. WRAP: `render_valid` needs the raw base64 from `capture_top_output`'s `ImageContent`; `ToolResult` only counts images — predicates.py must extract image bytes (extend probe handling or call handler directly). |
| `judge.py` | **split: heuristic reuse / LLM replace** | `_heuristic()` is deterministic, sane, offline → reuse-as-is for layer (c) fallback. `rubric_score()` LLM branch (anthropic + API key) → **replace** with Max-plan `claude` CLI in our `llm.py`. Gates don't collide (judge=`RUN_JUDGE`; ours=`RUN_CASE_REVIEW`). |
| Loader pattern (`prompt_eval` / `test_agent_quality` importlib) | **reuse-as-is (pattern)** | Confirmed present; copy the `importlib.util.spec_from_file_location` shape, not `sys.path`. |

## Important plan correction — `query_graph` is NOT live topology

`query_graph` is a **KB** query only (`command: params|related|family` over the operator knowledge graph). It does **not** see the running TD network. The plan's "Verified during planning: query_graph → connections" note was **wrong** — Gate A's purpose.

The real live introspection exists as **MCP tools** (reachable via `probe.call()`, gated on TD running), from `td_live_client.py`:

- `binding_wired` → **`capture_network_layout`** — returns nodes `(name, family/type, x, y)` + connections `from_path → to_path (input N)` + counts. (WRAP: tool flattens to markdown; parse it, or hit the underlying `/api/feedback/capture/network` JSON for structured data.)
- `render_valid` → **`capture_top_output`** — base64 JPEG/PNG of the rendered TOP → decode → checkerboard + degenerate-frame analysis.
- `compiles` / `error_class_absent` → **`get_cook_errors`** / **`get_td_node_errors`** / **`get_error_summary`** (text).
- `op_exists` / `param_exists` → `OperatorRegistry` (offline, no live needed).
- Live build (build/fix sections) → `create_td_node` / `update_td_node_parameters` / `td_build_project`.

Net: every live predicate is feasible via existing MCP tools — no direct HTTP client needed, Probe is reusable for the live path too.

## `claude` CLI headless smoke — PASS

`/c/Users/Jake/.local/bin/claude` v2.1.81. `claude -p --model haiku --output-format json "…"` → clean JSON, `.result` = answer text, model alias resolved to `claude-haiku-4-5-20251001`, parseable. Confirms the no-API-key Max-plan transport and `--model opus|sonnet|haiku` ladder mechanism.

- Cost-shape note: ~45.5k `cache_creation_input_tokens` per invocation (CLI bootstraps session context each call). Plan-billed on Max, but informs ladder cost → favor `--only`/batching and a minimal `--system-prompt`; not a blocker.

## Environment state

- TD **not running** (127.0.0.1:9981 unreachable now) → confirms v1 must be offline-deterministic (as planned); live predicates gated/skipped until TD is up.
- agent-quality opt-in gate is `RUN_NL_EVAL` (not `RUN_JUDGE`) — irrelevant to us (we use `RUN_CASE_REVIEW` / `RUN_CASE_CALIBRATION`), noted to avoid confusion.

## Impact on the plan

1. **Replace** every planned `query_graph`-for-topology reference with `capture_network_layout`; update the "Verified during planning" note.
2. Add a WRAP task: image-bytes extraction for `render_valid` from `capture_top_output`.
3. Add a WRAP task: markdown→struct parse for `capture_network_layout` (or JSON-endpoint path).
4. Keep `judge._heuristic` as the layer-(c) offline fallback; build `llm.py` CLI transport for the LLM branch.
5. No `emit`/`Probe`/`conftest` replacement needed — proceed on the existing harness.

**STOP — Gate A. Awaiting go-ahead for Gate A′ (exemplar spec sheet).**
