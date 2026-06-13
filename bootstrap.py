"""Shared PYTHONPATH bootstrap for the TD Builder alpha package.

The alpha is a single coherent package presented as:
    MCP/             MCP server launcher + TD-side WebServer asset
    core/            engine surface (unified_system + meta_agentic + td-mcp)
    KB/              the single consolidated knowledge base bundle
    tools/           CLI entry points (td-validate / td-convert / td-build)
    skills_expertise/  skills + expert prompts
    docs/            install / modes / demo walkthrough

The verified MCP server module stays at META_AGENTIC_TOOL/mcp_server.py so its
__file__-relative resolution of the KB bundle (../KB) and its sibling search
stack keeps working unchanged. This module just makes the engine import roots
resolvable regardless of current working directory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Engine import roots. Order matters: repo root first, then the subsystem
# package roots whose top-level names (api, core, validation, builders,
# meta_agentic, td_live_client, json_to_dir_LOSSLESS) the server imports.
_PATHS = [
    ROOT,
    ROOT / "MCP" / "engine",        # the TD-file engine (was unified_system)
    ROOT / "MCP" / "server_core",   # the MCP server + search + meta_agentic (was META_AGENTIC_TOOL)
]


def setup() -> Path:
    """Insert engine import roots onto sys.path (idempotent). Returns repo root."""
    for p in _PATHS:
        s = str(p)
        if p.exists() and s not in sys.path:
            sys.path.insert(0, s)
    return ROOT
