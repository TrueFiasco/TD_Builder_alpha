# Tool risk annotations

Owner-approved classification behind the MCP `ToolAnnotations` carried by every tool
on both servers (W4b, harness audit cluster C3). This is the in-repo source of truth;
the code sets these hints from the three shared constants named below.

## Why

The two servers previously described which tools mutate a live TouchDesigner graph
only in English tool descriptions, so a client's approval layer had nothing
structured to gate on — it could not tell `get_td_nodes` (safe read) from
`delete_td_node` (destroys graph state) or `execute_python_script` (arbitrary code).
These annotations give the client machine-readable risk tiers. They are the
prerequisite for D3's future live-authorization tiering (auto-allow safe tools, gate
dangerous ones).

MCP annotations are **hints**, advisory metadata a client may use to shape its
approval UX. They do not change tool behavior.

## Hints shipped

Owner decision: ship only the three named hints. `openWorldHint` is **omitted** (left
at the SDK default everywhere) — none of these tools reach an unbounded external
world; they hit a local KB, local files, or a single loopback TD endpoint, and the
hint adds no gating signal here.

Per the MCP spec, `destructiveHint` and `idempotentHint` are meaningful **only when
`readOnlyHint` is false**.

## Classes (shared `ToolAnnotations` constants)

| Class | `readOnlyHint` | `destructiveHint` | `idempotentHint` | Meaning |
|---|---|---|---|---|
| `READ_ONLY` | `True` | — | — | No environment change. |
| `WRITE_ADDITIVE` | `False` | `False` | `False` | Creates a file/artifact; never mutates the live graph (offline `td-builder`). |
| `WRITE_ADDITIVE_IDEMPOTENT` | `False` | `False` | `True` | Additive write whose targets are stable and name-keyed (delete-then-upsert), so re-running has the same effect (offline `register_component`). Same hint triple as `WRITE_CHECKPOINT` but a distinct class: an idempotent additive registry/index **upsert**, not a **checkpoint overwrite** of one stable target — and the offline constant vocabulary is test-pinned separately from the live one. Owner-approved (W7 decision 1, consistent with the D3 precedent below). |
| `WRITE_CHECKPOINT` | `False` | `False` | `True` | Writes a file to a stable target; never mutates the live graph; overwriting is idempotent (live `save_td_project`). |
| `DESTRUCTIVE` | `False` | `True` | `False` | May mutate/destroy live graph state or run arbitrary code. |

Destructive tools all take `idempotentHint=False` conservatively: `create_td_node`
auto-suffixes on name collision, `update_td_node_parameters` can pulse params or add
sequence children, and the exec tools are arbitrary — none are safely idempotent.

**D3 save/snapshot tool (`save_td_project`, live surface): `WRITE_CHECKPOINT`.** It
writes a `.toe` copy to disk (an honest `readOnlyHint=False` — the audit forbids lying
hints), does not mutate the live graph, and overwrites a stable target, so re-running it
has the same effect (`idempotentHint=True`). It is a NEW class, distinct from
`WRITE_ADDITIVE`: the offline `WRITE_ADDITIVE` pins `idempotentHint=False`
(test-locked), so the `readOnlyHint=False, destructiveHint=False, idempotentHint=True`
shape needs its own constant. That keeps `save_td_project` allow-under-auto without
lying about read-only-ness — it is the pre-mutation safety primitive and must fire
unattended.

## Offline `td-builder` (18) — 16 read-only + 1 write-additive + 1 write-additive-idempotent

| Tool | Class | Note |
|---|---|---|
| hybrid_search | READ_ONLY | KB query |
| get_operator_info | READ_ONLY | KB query |
| query_graph | READ_ONLY | KB query |
| list_pop_operators | READ_ONLY | KB query |
| find_operator_examples | READ_ONLY | KB query |
| find_operator_combination | READ_ONLY | KB query |
| find_parameter_usage | READ_ONLY | KB query |
| find_similar_networks | READ_ONLY | KB query |
| get_parameter_detail | READ_ONLY | KB query |
| get_network_patterns | READ_ONLY | KB query |
| td_validate | READ_ONLY | pure validation |
| td_convert | READ_ONLY | pure format transform |
| get_expert_prompt | READ_ONLY | reads prompt files |
| get_server_info | READ_ONLY | runtime identity |
| expand_toe_file | READ_ONLY | reads a file; `toeexpand` writes only a temp dir cleaned up in `finally` — no persistent side effect |
| td_build_status | READ_ONLY | polls in-memory job state |
| **td_build_project** | **WRITE_ADDITIVE** | writes a `.tox`/`.toe` to disk; never touches the live graph |
| **register_component** | **WRITE_ADDITIVE_IDEMPOTENT** | writes the user registry + user Chroma store + manifest (+ optional palette `.tox` copy) — all OUTSIDE the shipped KB; every write is a name-keyed delete-then-upsert, so re-running is idempotent (honest `idempotentHint=True`, W7 owner decision 1) |

## Live `td-builder-live` (22) — 16 read-only + 1 write-checkpoint + 5 destructive

| Tool | Class | Note |
|---|---|---|
| capture_top_output | READ_ONLY | forces a cook (not a persistent mutation) |
| get_top_info | READ_ONLY | |
| get_cook_errors | READ_ONLY | |
| get_error_summary | READ_ONLY | |
| capture_network_layout | READ_ONLY | |
| get_python_exceptions | READ_ONLY | |
| capture_op_viewer | READ_ONLY | forces a cook; op-viewer families use a temp viewer created+destroyed within the call |
| get_glsl_status | READ_ONLY | reads the shader Info DAT (may create+destroy a temp Info DAT) — no persistent mutation on this surface; the persistent docked `<name>_info` is created only by the update_td_node_parameters receipt (see that row) |
| get_td_info | READ_ONLY | |
| get_td_nodes | READ_ONLY | |
| get_td_node_parameters | READ_ONLY | |
| get_td_node_errors | READ_ONLY | |
| get_td_classes | READ_ONLY | |
| get_td_class_details | READ_ONLY | |
| get_td_module_help | READ_ONLY | |
| get_mutation_status | READ_ONLY | reports what committed since server start (post-timeout recovery) |
| **save_td_project** | **WRITE_CHECKPOINT** | dialog-proof filesystem copy of the last-saved `.toe`; never mutates the graph; overwrites a stable target |
| **create_td_node** | **DESTRUCTIVE** | adds a node (auto-suffixes → not idempotent) |
| **update_td_node_parameters** | **DESTRUCTIVE** | mutates params (may pulse / add sequence children); its W-A3 GLSL receipt may create+dock a persistent `<name>_info` Info DAT on the checked GLSL op if it lacks one (owner decision 2026-07-14 — within this class); the receipt resolves the consuming GLSL op via dock/sibling/capped project scan (read-only scan, no extra mutation) |
| **delete_td_node** | **DESTRUCTIVE** | destroys a node + descendants |
| **execute_python_script** | **DESTRUCTIVE** | arbitrary Python in TD |
| **exec_node_method** | **DESTRUCTIVE** | arbitrary method (`.destroy()`, `.save()`, …) |

## Where the code lives

- Offline: `MCP/server_core/mcp_server.py` — `READ_ONLY` / `WRITE_ADDITIVE` /
  `WRITE_ADDITIVE_IDEMPOTENT` constants above `list_tools()`; each `Tool(...)`
  carries `annotations=`.
- Live: `MCP/live_client/td_live_client.py` — `READ_ONLY` / `WRITE_CHECKPOINT` /
  `DESTRUCTIVE` constants above `TD_LIVE_TOOLS`; each `Tool(...)` carries `annotations=`.
- The canonical operationId→class map for the live authorization tiering (D3) is
  `MCP/live_tool_risk.json`; the td-webserver reads it to build its policy map (opt-in
  read-only mode via `TD_BUILDER_LIVE_READONLY`), and the client annotations are
  CI-locked to it.
- The classification is regression-checked by `tests/unit/test_output_budgets.py` and
  `tests/unit/test_live_tool_risk.py`.

Annotations add fields to `Tool(...)`; they change no tool **name** or **count** by
themselves. D3/#26 added live tools (19→22) without touching the offline inventory or
the agent-eval `tool_inventory_hash` (sorted names of the offline server); **W7's
`register_component` (17→18 offline) is the change that flips that hash** — its
owner-machine baseline re-capture is sequenced immediately after the W7 merge.
