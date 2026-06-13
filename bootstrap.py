"""Shared PYTHONPATH bootstrap for the TD Builder package.

The release is presented as six folders:
    MCP/      server launchers (server.py, live_server.py) + server_core/ + engine/ + TD-side WebServer asset
    KB/       the consolidated knowledge base bundle (fetched on install)
    Agents/   expert prompts + skills + expertise
    Config/   .env + search_config.json + settings
    LLM/      pre-prompts
    Tools/    CLI launchers + tool docs

The offline server module lives at MCP/server_core/mcp_server.py; its
__file__-relative resolution of the KB bundle (<root>/KB) and its sibling search
stack keep working unchanged. This module just makes the engine import roots
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
