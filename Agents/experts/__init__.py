"""
Expert agent prompts for the META_AGENTIC_TOOL workflow.

Each expert directory contains:
    - plan.md: Planning step prompt
    - build.md: Build step prompt
    - self_improve.md: Self-review step prompt
    - config.yaml: Expert configuration (optional)

This is the canonical roster (8 experts). Strategy runner V2-V6 currently
invokes 5 of them (creative_expert, cg_expert, td_designer,
network_builder, critic). The other 3 (td_glsl_expert, td_python_expert,
ui_expert) are reachable via the inactive MCP server's `spawn_expert`
tool but are not part of any V2-V6 phase order yet.

Five previously-registered experts (summary_generator,
format_reverse_engineer, creative_orchestrator, claude_code_orchestrator,
network_editor_expert) were never invoked by any strategy and have been
moved to `archive/experts_unused/` as part of the H1/M20/M21 cleanup.
The unique reverse-engineering content from `format_reverse_engineer/
LEARNINGS.md` was preserved at `unified_system/docs/TOE_FORMAT_LEARNINGS.md`.
"""

from pathlib import Path

EXPERTS_DIR = Path(__file__).parent

EXPERT_IDS = [
    "td_designer",         # TouchDesigner network design
    "td_glsl_expert",      # GLSL shader programming
    "td_python_expert",    # TD Python scripting
    "network_builder",     # .toe/.tox file generation
    "ui_expert",           # UI / control-panel design
    "critic",              # quality scoring + YAML output schema
]


def get_expert_path(expert_id: str) -> Path:
    """Get the path to an expert's directory."""
    return EXPERTS_DIR / expert_id
