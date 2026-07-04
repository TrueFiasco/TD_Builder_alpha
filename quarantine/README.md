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
