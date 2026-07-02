"""Execution layer (trimmed for the key-free release).

Only the modules the MCP server uses remain:
    blackboard, metrics, orchestrator, tox_builder, toe_builder_bridge,
    ground_truth, param_name_resolver

The V0-V6 Python-only strategy runner and its expert-executor / critic /
kb_query / llm_executor / variant-spawner stack were removed — they were never
reachable through any MCP tool.

Import submodules directly, e.g.:
    from meta_agentic.execution.blackboard import Blackboard, SectionID
    from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge
"""
