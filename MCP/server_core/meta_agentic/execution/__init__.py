"""Execution layer (trimmed for the key-free release).

Only the modules the MCP server uses remain:
    tox_builder, toe_builder_bridge, param_name_resolver

The V0-V6 Python-only strategy runner and its expert-executor / critic /
kb_query / llm_executor / variant-spawner stack were removed — they were never
reachable through any MCP tool. The workflow-orchestration trio
(orchestrator/blackboard/metrics) was equally unreachable and now lives in
quarantine/meta_agentic_orchestration/ (W2a; schema harvested to docs/specs/).
`ground_truth.py` — the param-schema validation layer, INERT since birth (it
pointed at a never-shipped corpus so every lookup fail-soft passed) — was
quarantined in W3a; the builder resolves param names via param_name_resolver
against the shipped KB instead.

Import submodules directly, e.g.:
    from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge
"""
