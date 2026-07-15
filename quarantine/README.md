# quarantine/ — dead code preserved under the quarantine-not-fix decision

Code in this directory is **out of service**: it is on no import path, collected by no
test runner, installed by no package, and scanned by no docs lint. It is kept — rather
than deleted — under the project's locked *quarantine-not-fix* decision, so the design
work it embodies stays reviewable in-tree instead of only in git history.

## Rules (established W2a, 2026-07-04, owner-approved)

1. **Never importable.** No `__init__.py` anywhere under `quarantine/`; nothing in the
   repo may add it to `sys.path` or import from it. Absence tests
   (`tests/engine/test_import_isolation.py`) pin that quarantined modules stay off the
   import path and out of `MCP/server_core/mcp_server.py`.
2. **Out of every automated surface.** pytest collects only `tests/` (`testpaths` in
   `pyproject.toml`); packaging installs nothing (`packages = []`); `quarantine` is in
   docs-lint `exclude_dirs` (`scripts/docs_lint_rules.json`) because this README
   legitimately describes dead patterns.
3. **Moved with `git mv`**, files stay tracked — quarantine is preservation, not a
   slow-motion delete.
4. **Every entry is manifested below**: what it is, why it's here, what knowledge was
   salvaged and where, what it would take to revive it, and when it can be disposed of.
5. **Reviving anything here is an owner decision executed by a dedicated wave**, never a
   drive-by re-import.

## Manifest

### meta_agentic_orchestration/ (quarantined 2026-07-04, W2a)

`orchestrator.py`, `blackboard.py`, `metrics.py` — the workflow-orchestration trio,
formerly `MCP/server_core/meta_agentic/execution/`.

- **What:** a Python-only multi-expert workflow engine: a §1-§7 sectioned "blackboard"
  project document with versioning/locking, a phase state machine
  (INIT→CREATIVE→TECHNICAL→RESOURCES→DESIGN→BUILD→COMPLETE) with critic-score
  thresholds and convergence rules, and a per-run metrics collector.
- **Why quarantined:** dead since the key-free release — no MCP tool path ever
  instantiated any of the three (verified by the H4 structural audit and again at W0/W2a).
  Until W0 their import even held the live builders hostage (one shared try/except flag);
  W0 split that, W2a removed the import entirely.
- **Knowledge salvaged:** schema + intent harvested to
  [docs/specs/blackboard_schema.md](../docs/specs/blackboard_schema.md) (input to the
  parked D6 cowork phase-loops proposal) and
  [docs/specs/metrics_shapes.md](../docs/specs/metrics_shapes.md) (input to the D4
  minimal feedback spine). The related unwired `delegate_to:` key in
  `Agents/expertise/td_network_patterns.yaml` was folded into its adjacent `notes:` line
  (nothing ever consumed the key).
- **Revival condition:** only via the D6 proposal if the owner green-lights it — and D6's
  premise is blackboard-as-*file* driven by cowork phase-loops, so revival would reuse
  the schema, almost certainly not these classes.
- **Disposal trigger:** once D6 ships (or is rejected) with the spec docs as its input,
  this entry can be deleted outright.

### ground_truth.py (quarantined 2026-07-04, W3a)

`ground_truth.py` — the `GroundTruth` param-schema validation singleton, formerly
`MCP/server_core/meta_agentic/execution/ground_truth.py`.

- **What:** a loader + validator for per-operator parameter schemas (menu label→value,
  param-name resolution, value validation), keyed off `*_defaults.json` files it globbed
  from an `operator_ground_truth/params` directory.
- **Why quarantined:** INERT SINCE BIRTH. `GROUND_TRUTH_DIR` resolved to
  `MCP/server_core/operator_ground_truth/params`, which has never existed in any release —
  `load()` warned "Ground truth directory not found" and returned nothing, so every lookup
  fail-soft returned `None`/`invalid`. Its sole consumer, `ToeBuilderBridge._param_lines`,
  therefore ALWAYS took its `if not validation["valid"]:` fallback (menu-resolve via
  `param_name_resolver`), making the whole validation layer — and its `else` branch — dead.
  Removing it is provably behavior-preserving and also silences the per-op warning spam.
  (The real param corpus lives in the dev tree at `New KB build/Resources/
  operator_ground_truth/params`, used only by the offline build gate — never shipped.)
- **Knowledge salvaged:** none needed — its live job (param-name resolution against the
  KB) is already done by `param_name_resolver.py`, which reads the shipped
  `KB/operators.json`. The menu-label→value mapping survives in
  `param_name_resolver.resolve_menu_value` + `MENU_VALUE_MAP`.
- **Revival condition:** only if a future release ships a real per-operator param-schema
  corpus AND an owner decides a second validation layer (beyond name resolution) earns its
  regression risk. Wire it against the shipped KB, never a dev-only path.
- **Disposal trigger:** deletable outright once the shipped param corpus question is
  settled — nothing depends on it.

### deadweight_2026_07/ (quarantined 2026-07-15, dead-weight sweep)

Items moved here by the 2026-07 dead-weight sweep (the full per-item forensics —
git history to the orphaning commit, replacement owner, revival costing — live in the
sweep report `DEADWEIGHT_REPORT_2026-07-15.md`, a session artifact held by the owner;
the load-bearing facts are carried inline below so each entry stands alone).
Absence pins: `tests/engine/test_import_isolation.py::test_deadweight_2026_07_absent_from_live_tree`.

#### openapi_codegen/ — `genHandlers.js` + `api_controller_handlers.mustache`

Formerly `MCP/td-webserver/genHandlers.js` and
`MCP/td-webserver/templates/mcp/api_controller_handlers.mustache`.

- **What:** the OpenAPI→handler codegen pair inherited from the upstream
  touchdesigner-mcp project: a Node script (imports fs-extra/mustache/yaml) that rendered
  `modules/mcp/controllers/generated_handlers.py` from `openapi.yaml` via the mustache
  template.
- **Why quarantined:** born broken in this repo — all three of its paths resolve under a
  `td/` prefix that has never existed in any commit (it is the upstream repo's layout),
  no `package.json` ever existed so its deps were never installable, and nothing
  references it. Worse than dead, it is an **active footgun**: "fix the paths and re-run
  it" reads like maintenance, would silently replace the live, hand-maintained
  `generated_handlers.py` — 365 lines of explicit per-route validation, including the
  B17 recurse-threading and B25 mode-param handling and PR #24's F3 `get_nodes` limit
  guard — with a naive reflection dispatcher that debug-prints full request bodies
  (including `exec_python_script` source) to the TD textport, and would *look* fine:
  the 12 operationIds in `openapi.yaml` still match the module's `__all__`, so every
  route registers cleanly at startup while behavior silently degrades.
- **Knowledge salvaged:** the four repo comments that described the codegen as live were
  reworded in the same sweep commit (`bootstrap_mcp.py`, `api_controller.py` ×2,
  `session_handlers.py`); `generated_handlers.py` is now consistently described as the
  hand-maintained static handler module ("generated" in its name is upstream heritage).
- **Revival condition:** none as-is. New TD-side routes extend via dynamic registration
  (`feedback_handlers`/`session_handlers` `get_*_routes()` →
  `OpenAPIRouter.register_route`) — the live seam. Genuine codegen revival would mean
  porting the hand-written validation into the template plus a CI drift check (priced
  L and negative-value in the sweep report) and is an owner decision.
- **Disposal trigger:** deletable if the td-webserver asset ever drops the OpenAPI
  routing layer, or once upstream provenance stops being worth keeping in-tree.
