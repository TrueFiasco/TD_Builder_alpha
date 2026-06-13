"""
Expert agent prompts served by the `get_expert_prompt` MCP tool.

Each expert directory contains:
    - plan.md: Planning step prompt
    - build.md: Build step prompt
    - self_improve.md: Self-review step prompt
    - config.yaml: Expert configuration (optional)

The roster is the 6 experts in EXPERT_IDS below; the offline server exposes the
same set via get_expert_prompt (see AVAILABLE_EXPERTS in
MCP/server_core/mcp_server.py). Format reverse-engineering notes live in
docs/TOE_FORMAT_LEARNINGS.md.
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
