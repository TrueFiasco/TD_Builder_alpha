#!/usr/bin/env python3
"""
TouchDesigner MCP Server with Multi-Agent System
Spawns specialized engineer agents for knowledge extraction
"""

import sys
import json
import asyncio
import os
import re
from pathlib import Path
from typing import Any, Sequence, Dict, Callable, List, Optional, Union
import base64
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))

# Add unified_system to path for validation and format conversion
UNIFIED_SYSTEM_ROOT = Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(UNIFIED_SYSTEM_ROOT))

# --------------------------------------------------------------------------
# Stdout-pollution guard
# --------------------------------------------------------------------------
# MCP uses stdout for the JSON-RPC protocol channel. Diagnostic prints from
# imported modules (unified_graph_query, enhanced_graph_query, search
# adapters, sentence-transformers etc.) use bare print() which would write
# to stdout and pollute the protocol — Claude Desktop then surfaces those
# as "Unexpected token ... is not valid JSON" warnings to the user.
#
# Solution: redirect sys.stdout -> sys.stderr for the entire import and
# module-level initialization phase. Restored to the real stdout in main()
# right before stdio_server() takes over the protocol channel.
#
# mcp_server.py's own prints already use file=sys.stderr explicitly, so
# this change doesn't affect them. It only catches the bare print() calls
# in the imported third-party modules.
_real_stdout = sys.stdout
sys.stdout = sys.stderr

# Query tracker for Sweet 16 evolution
try:
    from meta_agentic.history.query_tracker import log_query, QueryTracker
    QUERY_TRACKING_ENABLED = True
    print("Query tracking enabled for Sweet 16 evolution", file=sys.stderr)
except ImportError:
    QUERY_TRACKING_ENABLED = False
    def log_query(*args, **kwargs): pass

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, ImageContent
except ImportError:
    print("ERROR: MCP package not installed", file=sys.stderr)
    print("Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# TD Live Client - HTTP client for TouchDesigner WebServer DAT
# Provides visual feedback and CRUD tools for running TD instances
try:
    from td_live_client import TD_LIVE_TOOLS, TD_LIVE_HANDLERS
    TD_LIVE_ENABLED = True
    print("Live TD tools enabled (19 tools for a running TouchDesigner).", file=sys.stderr)
except ImportError:
    TD_LIVE_ENABLED = False
    TD_LIVE_TOOLS = []
    TD_LIVE_HANDLERS = {}
    # Expected on the offline 'td-builder' server: the 19 live tools are served
    # by the separate 'td-builder-live' server (MCP/live_server.py).
    print("Offline server: live TD tools are served separately by td-builder-live.", file=sys.stderr)

try:
    import importlib.util

    # Load unified graph query engine (wiki docs + enhanced examples)
    spec = importlib.util.spec_from_file_location("unified_graph_query", str(Path(__file__).parent / "unified_graph_query.py"))
    unified_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(unified_module)
    UnifiedGraphQuery = unified_module.UnifiedGraphQuery
    print("Loaded unified graph query (wiki + examples)", file=sys.stderr)

    # Load unified search adapter (enhanced with multiple embedding providers)
    try:
        spec = importlib.util.spec_from_file_location("unified_search", str(Path(__file__).parent / "search" / "unified_search.py"))
        search_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(search_module)
        UnifiedSearchAdapter = search_module.UnifiedSearchAdapter
        print("Loaded unified search adapter with enhanced embedding support", file=sys.stderr)
    except Exception as e:
        # Fallback to legacy HybridGraphRAG
        try:
            spec = importlib.util.spec_from_file_location("hybrid_search", str(Path(__file__).parent / "hybrid_search.py"))
            hybrid_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hybrid_module)
            UnifiedSearchAdapter = hybrid_module.HybridGraphRAG
            print("Loaded legacy hybrid search (fallback)", file=sys.stderr)
        except Exception as e2:
            print(f"WARNING: Could not load search (vector DB unavailable): {e2}", file=sys.stderr)
            print("  Unified graph will still work. To enable vector search, install: pip install sentence-transformers", file=sys.stderr)
            UnifiedSearchAdapter = None

except Exception as e:
    print(f"ERROR: Could not load unified graph query: {e}", file=sys.stderr)
    sys.exit(1)

# META_AGENTIC_TOOL Expert Workflow Integration
try:
    from meta_agentic.execution.blackboard import Blackboard, SectionID
    from meta_agentic.execution.metrics import MetricsCollector
    from meta_agentic.execution.orchestrator import WorkflowOrchestrator, StrategyConfig
    from meta_agentic.execution.tox_builder import ToxBuilder
    from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge
    EXPERT_WORKFLOW_ENABLED = True
    print("META_AGENTIC_TOOL expert workflow enabled", file=sys.stderr)
except ImportError as e:
    EXPERT_WORKFLOW_ENABLED = False
    print(f"WARNING: META_AGENTIC_TOOL not available: {e}", file=sys.stderr)

# Import unified_system components for validation and format conversion
try:
    from api.network_builder import NetworkBuilder
    from core.format_converter import FormatConverter
    from core.operator_registry import OperatorRegistry
    from validation.pipeline import ValidationPipeline
    from builders.toe_builder import TOEBuilder

    # Initialize validation/conversion components
    _registry = OperatorRegistry()
    _converter = FormatConverter(_registry)
    _validator = ValidationPipeline(_registry)
    UNIFIED_SYSTEM_ENABLED = True
    print("Unified system validation/conversion enabled", file=sys.stderr)
except (ImportError, FileNotFoundError) as e:
    # FileNotFoundError: the KB (operators.json) isn't fetched yet. Degrade
    # gracefully (the build/validate/convert tools emit their own unavailable
    # message) instead of crashing the whole MCP import.
    UNIFIED_SYSTEM_ENABLED = False
    _registry = None
    _converter = None
    _validator = None
    print(f"WARNING: Unified system not available: {e}", file=sys.stderr)

# Import meta_agentic compaction utilities (optional)
try:
    from meta_agentic.compaction import compact_events_to_state, refresh_legacy_yaml
    HAS_COMPACTION = True
    COMPACTION_IMPORT_ERROR = None
    print("Meta-agentic compaction enabled", file=sys.stderr)
except Exception as e:
    HAS_COMPACTION = False
    COMPACTION_IMPORT_ERROR = str(e)
    print(f"WARNING: Compaction not available: {e}", file=sys.stderr)


# Expert prompts for td_designer, network_builder, etc.
EXPERTS_DIR = Path(__file__).resolve().parents[2] / "Agents" / "experts"

AVAILABLE_EXPERTS = {
    "td_designer": {
        "description": "Create TouchDesigner network specifications from creative briefs. Knows operator types, parameters, and TD conventions.",
        "files": ["build.md", "plan.md"]
    },
    "network_builder": {
        "description": "Build .toe/.tox files from network specifications. Handles parameter values, connections, and file generation.",
        "files": ["build.md", "plan.md"]
    },
    "td_glsl_expert": {
        "description": "Write and optimize GLSL shaders for TouchDesigner. Knows GLSL TOP patterns and uniforms.",
        "files": ["build.md", "plan.md"]
    },
    "td_python_expert": {
        "description": "Write Python scripts for TouchDesigner automation. Knows TD Python API.",
        "files": ["build.md", "plan.md"]
    },
    "ui_expert": {
        "description": "Design TouchDesigner UI and control panels. Knows widget patterns.",
        "files": ["build.md", "plan.md"]
    },
    "critic": {
        "description": "Review and score outputs. Flags issues and suggests improvements.",
        "files": ["build.md"]
    },
}
# Roster cleanup (H1/M20/M21): summary_generator, format_reverse_engineer, and
# creative_orchestrator were registered here historically but never invoked by
# V2-V6 strategies and not reachable via the standard expert loader; they were
# removed from this roster.

def load_expert_prompt(expert_name: str, phase: str = "build") -> str:
    """Load expert prompt from meta_agentic/experts/{expert}/{phase}.md"""
    expert_dir = EXPERTS_DIR / expert_name
    if not expert_dir.exists():
        return f"ERROR: Expert '{expert_name}' not found"

    prompt_file = expert_dir / f"{phase}.md"
    if not prompt_file.exists():
        return f"ERROR: Phase '{phase}' not found for expert '{expert_name}'"

    try:
        return prompt_file.read_text(encoding='utf-8')
    except Exception as e:
        return f"ERROR reading {prompt_file}: {e}"




# --------------------------------------------------------------------------
# Lazy knowledge-base init  (FAST STARTUP — fixes Desktop init timeouts)
# --------------------------------------------------------------------------
# The enhanced graph (~37k nodes) + ChromaDB + sentence-transformers take
# 1-2 min to load. Doing that at import blocks the MCP `initialize` handshake,
# so trivial tools (get_server_info) and the client connection itself time out
# in Claude/ChatGPT Desktop — especially with multiple servers contending.
# Fix: resolve bundle paths now (cheap) and DEFER the heavy construction to
# the first KB-dependent tool call via _ensure_kb().
try:
    # Prefer the consolidated alpha KB/ bundle (repo-root/KB); fall back to the
    # legacy META_AGENTIC_TOOL/data layout (pre_alpha baseline).
    _kb = Path(__file__).resolve().parents[2] / "KB"
    _data = Path(__file__).parent / "data"
    if (_kb / "operators.json").exists():
        enhanced_graph_path = _kb / "knowledge_graph_enhanced.gpickle"
        graphrag_json_path = _kb / "graphrag.json"
        enriched_wiki_path = _kb / "operators.json"
        vectordb_path = _kb / "vector_db"
    else:
        enhanced_graph_path = _data / "td_knowledge_graph_enhanced.gpickle"
        graphrag_json_path = _data / "td_graphrag.json"
        enriched_wiki_path = _data / "wiki_docs" / "td_universal_parsed_enriched.json"
        vectordb_path = _data / "vector_db_merged"
except Exception as e:
    print(f"WARNING: Could not resolve KB paths: {e}", file=sys.stderr)
    enhanced_graph_path = graphrag_json_path = enriched_wiki_path = vectordb_path = Path("___missing___")

knowledge_graph = None
hybrid_search = None
# _KB_STATUS values: "pending" | "warming" | "ready" | "partial" | "failed"
#   pending  — warmup hasn't started yet
#   warming  — _load_kb() is running right now
#   ready    — both knowledge_graph AND hybrid_search loaded
#   partial  — knowledge_graph loaded but hybrid_search is None (semantic search
#              unavailable: vector_db missing OR sentence-transformers not installed
#              OR semantic init exception). Graph-only tools still work.
#   failed   — knowledge_graph could not be loaded. No KB tools work.
# _KB_REASON: human-readable detail for partial/failed states. Empty otherwise.
_KB_STATUS = "pending"
_KB_REASON: str = ""
_kb_lock = threading.Lock()  # serializes warm-up thread vs first KB tool call


def _ensure_kb():
    """Build the knowledge graph + unified search on first use (idempotent).

    BLOCKING — used by the warmup thread at startup. Tool handlers should
    use _kb_check() instead, which is non-blocking and returns a structured
    "warming" response to the caller rather than waiting on the lock.
    """
    if _KB_STATUS in ("ready", "partial", "failed"):
        return
    with _kb_lock:
        if _KB_STATUS in ("ready", "partial", "failed"):  # double-check after wait
            return
        _load_kb()


def _kb_check(needs_semantic: bool = False) -> Optional[Dict[str, Any]]:
    """Non-blocking KB readiness check for tool handlers.

    Returns None if the tool can proceed, or a structured error dict
    (status + actionable message) to return to the caller as-is.

    needs_semantic=True means the tool requires hybrid_search (semantic
    vector search). Only `hybrid_search` itself needs this; every other
    KB tool only needs the knowledge_graph (graph-only).
    """
    if _KB_STATUS == "ready":
        return None
    if _KB_STATUS in ("pending", "warming"):
        return {
            "status": "kb_warming",
            "message": (
                "KB is still loading (~1–2 min after server start). "
                "Wait and retry; do NOT fall back to live introspection — "
                "the answer is in the KB."
            ),
            "retry_after_seconds": 30,
        }
    if _KB_STATUS == "partial":
        if not needs_semantic:
            return None  # graph-only tools still work
        return {
            "status": "kb_partial",
            "message": _KB_REASON,
            "actionable": True,
        }
    # failed
    return {
        "status": "kb_failed",
        "message": _KB_REASON or "KB unavailable; see server stderr.",
        "actionable": True,
    }


def _load_kb():
    """One-time KB + search construction. Always runs under _kb_lock.

    Sets _KB_STATUS to one of: ready | partial | failed. Sets _KB_REASON
    with an actionable message for partial/failed states so callers can
    surface a useful next step instead of a confusing AttributeError.
    """
    global knowledge_graph, hybrid_search, _KB_STATUS, _KB_REASON
    _KB_STATUS = "warming"
    # CRITICAL stdout-pollution guard: KB/search submodules
    # (UnifiedGraphQuery / UnifiedSearchAdapter / sentence-transformers /
    # chromadb) emit bare print() progress like "🔍 Loading ..." to stdout.
    # _ensure_kb() runs at RUNTIME on the first KB-dependent tool call —
    # AFTER main() restored the real stdout, which IS the MCP JSON-RPC
    # channel. Any such print corrupts the protocol and the client
    # ("... is not valid JSON" -> server disconnected). Force every byte of
    # this lazy load to stderr, then restore stdout for MCP responses.
    _saved_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        # --- pre-flight: check files exist before construction so we can give
        # actionable error messages instead of opaque construction failures ---
        if not enhanced_graph_path.exists():
            _KB_STATUS = "failed"
            _KB_REASON = (
                f"Knowledge graph file not found at {enhanced_graph_path}. "
                f"Fix: run `python scripts/fetch_vector_db.py` from the repo "
                f"root, then restart the MCP server."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            return
        if not graphrag_json_path.exists():
            _KB_STATUS = "failed"
            _KB_REASON = (
                f"Knowledge graphrag JSON not found at {graphrag_json_path}. "
                f"Fix: run `python scripts/fetch_vector_db.py` from the repo "
                f"root, then restart the MCP server."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            return

        # --- load knowledge_graph (required) ---
        try:
            print("Loading unified knowledge graph (wiki + examples)", file=sys.stderr)
            knowledge_graph = UnifiedGraphQuery(
                graphrag_json_path=str(graphrag_json_path),
                enhanced_graph_path=str(enhanced_graph_path),
                enriched_wiki_path=str(enriched_wiki_path),
            )
            print(f"Loaded unified TD knowledge graph with {len(knowledge_graph.nodes)} nodes", file=sys.stderr)
        except Exception as e:
            _KB_STATUS = "failed"
            _KB_REASON = (
                f"Knowledge graph init error: {e}. "
                f"Check server stderr for the full traceback. "
                f"Common causes: corrupt gpickle file, mismatched Python version, "
                f"missing networkx/numpy. Try reinstalling: `pip install -e \".[api,dev]\"`."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return

        # --- load hybrid_search (optional — degrade to partial, not failed) ---
        if UnifiedSearchAdapter is None:
            _KB_STATUS = "partial"
            _KB_REASON = (
                "Semantic search unavailable: sentence-transformers / "
                "UnifiedSearchAdapter not importable in this Python env. "
                "Graph tools (get_operator_info, find_operator_examples, "
                "get_parameter_detail, etc.) still work. "
                "Fix: `pip install -e \".[api,dev]\"` then restart the MCP server."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            return
        if not vectordb_path.exists():
            _KB_STATUS = "partial"
            _KB_REASON = (
                f"Semantic search unavailable: vector DB missing at "
                f"{vectordb_path}. Graph tools still work. "
                f"Fix: `python scripts/fetch_vector_db.py` then restart the MCP server."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            return
        try:
            hybrid_search = UnifiedSearchAdapter(
                graph_path=str(enhanced_graph_path),
                vectordb_path=str(vectordb_path),
                use_legacy=False,
            )
            print("Loaded unified search", file=sys.stderr)
            _KB_STATUS = "ready"
            _KB_REASON = ""
        except Exception as e:
            _KB_STATUS = "partial"
            _KB_REASON = (
                f"Semantic search init error: {e}. Graph tools still work. "
                f"Check server stderr for the full traceback."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    finally:
        sys.stdout = _saved_stdout

app = Server("touchdesigner-mcp-server")

SERVER_NAME = "touchdesigner-mcp-server"
SERVER_VERSION = "0.1.2"

# Tools that need the heavy knowledge graph / vector search. Only these
# trigger the one-time _ensure_kb() lazy load; everything else (get_server_info,
# live-TD, validate/convert/build, spawn_*, expert prompts) stays instant.
_KB_DEPENDENT_TOOLS = {
    "hybrid_search", "get_operator_info", "query_graph", "list_pop_operators",
    "find_operator_examples", "find_operator_combination", "find_parameter_usage",
    "find_similar_networks", "get_parameter_detail", "get_network_patterns",
}


def _build_menu_options(param: Dict[str, Any]) -> List[Dict[str, str]]:
    """Zip menuNames + menuLabels into [{code, label}, ...] for menu parameters.

    The enriched wiki stores menu choices as two parallel arrays — menuNames
    (the code used in .par files and Python) and menuLabels (the human-facing
    display label). Returns [] if neither field is populated. Falls back to a
    legacy `options` field if some record uses that shape.
    """
    names = param.get("menuNames") or []
    labels = param.get("menuLabels") or []
    if not names and not labels:
        legacy = param.get("options") or []
        return legacy if isinstance(legacy, list) else []
    n = max(len(names), len(labels))
    return [
        {
            "code":  names[i]  if i < len(names)  else (labels[i] if i < len(labels) else ""),
            "label": labels[i] if i < len(labels) else (names[i]  if i < len(names)  else ""),
        }
        for i in range(n)
    ]


def execute_tool_for_agent(tool_name: str, tool_params: dict) -> Any:
    """Execute a tool request from a spawned agent"""
    
    # Check if knowledge graph is available for graph-based tools
    if knowledge_graph is None and tool_name in ["get_operator_info", "query_graph", "list_pop_operators"]:
        return {"error": "TD documentation not loaded"}

    # Check if hybrid search is available (optional - requires sentence_transformers)
    if hybrid_search is None and tool_name == "hybrid_search":
        return {"error": "Hybrid search not initialized (requires sentence_transformers)"}

    try:
        if tool_name == "hybrid_search":
            query = tool_params["query"]
            n_results = tool_params.get("n_results", 5)
            return hybrid_search.search(query, n_results=n_results)

        elif tool_name == "get_operator_info":
            operator_name = tool_params["operator_name"]
            # Log query for Sweet 16 evolution tracking
            if QUERY_TRACKING_ENABLED:
                # Extract family from operator name or result
                family = "UNKNOWN"
                for fam in ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]:
                    if fam.lower() in operator_name.lower():
                        family = fam
                        break
                log_query(operator_name, family, source="claude_desktop", test_type="claude_desktop")
            # Use knowledge_graph (UnifiedGraphQuery) instead of hybrid_search
            return knowledge_graph.get_operator_info(operator_name)
            
        elif tool_name == "query_graph":
            command = tool_params["command"]
            if command == "params":
                operator = tool_params.get("operator")
                return knowledge_graph.get_operator_info(operator)
            elif command == "related":
                operator = tool_params.get("operator")
                return knowledge_graph.get_operator_info(operator)
            elif command == "family":
                family = tool_params.get("family")
                # Return operators by family (simplified - list operator nodes)
                ops = [n for n in knowledge_graph.nodes.values()
                      if n.get('type') == 'Operator' and n.get('family', '').upper() == family.upper()]
                return [{'name': op['name'], 'family': op['family']} for op in ops]
            else:
                return {"error": f"Unknown command: {command}"}

        elif tool_name == "find_operator_examples":
            operator = tool_params.get("operator")
            limit = tool_params.get("limit", 10)
            return knowledge_graph.find_examples_by_operator(operator, limit)

        elif tool_name == "find_operator_combination":
            operator_types = tool_params.get("operator_types", [])
            require_connection = tool_params.get("require_connection", True)
            limit = tool_params.get("limit", 5)
            return knowledge_graph.find_examples_by_operator_combination(operator_types, require_connection, limit)

        elif tool_name == "find_parameter_usage":
            operator_type = tool_params.get("operator_type")
            parameter_name = tool_params.get("parameter_name")
            limit = tool_params.get("limit", 10)
            return knowledge_graph.find_parameter_usage(operator_type, parameter_name, limit)

        elif tool_name == "find_similar_networks":
            example_id = tool_params.get("example_id")
            limit = tool_params.get("limit", 5)
            return knowledge_graph.find_similar_patterns(example_id, limit)

        elif tool_name == "get_network_patterns":
            min_frequency = tool_params.get("min_frequency", 5)
            return knowledge_graph.get_network_patterns(min_frequency)
                
        elif tool_name == "list_pop_operators":
            return knowledge_graph.get_operators_by_family("POP")
        
        elif tool_name == "write_file":
            file_path = Path(tool_params["file_path"])
            content = tool_params["content"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding='utf-8')
            return {"status": "written", "path": str(file_path), "bytes": len(content)}
        
        elif tool_name == "list_directory":
            dir_path = Path(tool_params["path"])
            if not dir_path.exists():
                return {"error": f"Directory not found: {dir_path}"}
            items = [str(item.name) for item in sorted(dir_path.iterdir())]
            return {"items": items, "count": len(items)}
            
        else:
            return {"error": f"Unknown tool: {tool_name}"}
            
    except Exception as e:
        return {"error": str(e)}






async def td_build_project(design: Dict, project_name: str = None, output_dir: str = None) -> Dict:
    """
    Build a TouchDesigner .tox file from a network design specification.

    Uses META_AGENTIC_TOOL's ToxBuilder with validated operator mappings.

    Args:
        design: Network design dict with:
            - operators: list of {name, type, position, parameters}
            - connections: list of {from, to}
            - palette: Optional palette name to embed (e.g., "audioAnalysis")
        project_name: Optional project name (auto-generated if not provided)
        output_dir: Optional output directory (defaults to mcp_server/output)

    Returns:
        Dict with status, file path, and build details

    Example design:
        {
            "operators": [
                {"name": "noise1", "type": "noiseTOP", "position": [0, 0], "parameters": {"type": "random"}},
                {"name": "level1", "type": "levelTOP", "position": [200, 0], "parameters": {"opacity": 0.8}}
            ],
            "connections": [{"from": "noise1", "to": "level1"}]
        }
    """
    if not EXPERT_WORKFLOW_ENABLED:
        return {
            "status": "ERROR",
            "message": "META_AGENTIC_TOOL not available - ToxBuilder cannot be used"
        }

    try:
        import time
        import gzip

        # Generate project name if not provided
        if not project_name:
            project_name = f"td_project_{int(time.time()) % 10000}"

        # Set output directory
        if not output_dir:
            output_dir = str(Path(__file__).parent / "output")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        print(f"Building project: {project_name}", file=sys.stderr)

        # Ensure design has required structure
        if not isinstance(design, dict):
            return {
                "status": "ERROR",
                "message": "design must be a dictionary with 'operators' and 'connections'"
            }

        # Handle palette embedding — deferred to V0.2 (planned via live import, or by
        # referencing an external .tox from a base/container COMP, not bundled JSON).
        if 'palette' in design:
            return {
                "status": "ERROR",
                "message": ("Palette embedding is not available in V0.1.2 (planned for "
                            "V0.2 via live import / external .tox reference). Build the "
                            "network without the 'palette' key."),
            }

        if 'operators' not in design:
            design['operators'] = []
        if 'connections' not in design:
            design['connections'] = []
        if 'project' not in design:
            design['project'] = project_name

        # Build using ToxBuilder (for non-palette builds)
        builder = ToxBuilder(output_dir, verbose=True)
        tox_path = builder.build_tox(design, project_name)

        if tox_path and tox_path.exists():
            return {
                "status": "SUCCESS",
                "project_name": project_name,
                "output_file": str(tox_path),
                "file_size": tox_path.stat().st_size,
                "operators": len(design.get('operators', [])),
                "connections": len(design.get('connections', []))
            }
        else:
            return {
                "status": "ERROR",
                "message": "ToxBuilder did not produce output file"
            }

    except Exception as e:
        import traceback
        return {
            "status": "ERROR",
            "message": str(e),
            "traceback": traceback.format_exc()
        }


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    
    tools = [
        Tool(
            name="hybrid_search",
            description="Search TouchDesigner documentation using semantic search + knowledge graph. Returns relevant operators, parameters, concepts with relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question about TouchDesigner"
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_operator_info",
            description="Get info about a TouchDesigner operator. Use compact=true to save context (returns name, family, type, summary).",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_name": {
                        "type": "string",
                        "description": "Name of the operator (e.g., 'Grid SOP', 'Audio File In CHOP')"
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, returns minimal info to save context. Default: false",
                        "default": False
                    }
                },
                "required": ["operator_name"]
            }
        ),
        Tool(
            name="query_graph",
            description="Query TouchDesigner knowledge graph. Use compact=true for 'family' queries to get just names (saves ~700K context).",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["params", "related", "family"],
                        "description": "Type of query: 'params' (operator parameters), 'related' (related operators), 'family' (operators in family)"
                    },
                    "operator": {
                        "type": "string",
                        "description": "Operator name (required for 'params' and 'related')"
                    },
                    "family": {
                        "type": "string",
                        "description": "Operator family (required for 'family' command): SOP, CHOP, TOP, DAT, COMP, MAT, POP"
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, returns only names for 'family' queries. Default: false",
                        "default": False
                    }
                },
                "required": ["command"]
            }
        ),
        Tool(
            name="list_pop_operators",
            description="List all POP (Particle) operators available in TouchDesigner",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="find_operator_examples",
            description=(
                "Find real example networks demonstrating how to use a specific operator. "
                "Returns parameter values, connections, and text explanations from working "
                "TouchDesigner examples.\n"
                "\n"
                "Disambiguation: pass `family='TOP'` (etc.), or use the colon-form "
                "('TOP:noise') / family-suffixed ('noiseTOP') / space-separated ('noise TOP') "
                "in `operator`.\n"
                "\n"
                "Response shape (Wave 5 W5.2):\n"
                "  - Single-family resolution (family supplied OR bare name matches one family) "
                "    → flat list of example dicts.\n"
                "  - Bare name matching MULTIPLE families → bucketed dict:\n"
                "      {_resolution: 'multi-family', _query: ..., _families: [...],\n"
                "       results_by_family: {CHOP: [...], TOP: [...], ...}}\n"
                "    Each bucket is capped at `limit`. Caller should pick a family or iterate "
                "    `results_by_family` explicitly."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operator": {
                        "type": "string",
                        "description": "Operator name. Bare ('noise'), colon-form ('TOP:noise'), suffixed ('noiseTOP'), or space-separated ('noise TOP'). Bare names matching multiple families return a per-family bucketed dict (W5.2)."
                    },
                    "family": {
                        "type": "string",
                        "enum": ["CHOP", "TOP", "SOP", "MAT", "DAT", "COMP", "POP"],
                        "description": "Optional family scope. Overrides any family inferred from `operator`. Supplying this forces single-family flat-list response."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 10). For bucketed multi-family responses, this is per-bucket.",
                        "default": 10
                    }
                },
                "required": ["operator"]
            }
        ),
        Tool(
            name="find_operator_combination",
            description=(
                "Find examples that use specific operator combinations. Useful for learning "
                "how operators work together (e.g., 'CHOP:noise + CHOP:analyze', "
                "'TOP:feedback + TOP:level').\n"
                "\n"
                "Wave 5 W5.1 — every entry in `operator_types` MUST encode a family scope. "
                "Bare names like 'constant' or 'noise' are rejected with a structured error "
                "(they previously matched across every family with the same name and could "
                "surface cross-family false-positives silently). Accepted forms:\n"
                "  TOP:constant   colon-form (family explicit)\n"
                "  constantTOP    suffix-form (family explicit)\n"
                "  constant TOP   space-separated wiki form\n"
                "  ALL:constant   explicit opt-in for cross-family matching\n"
                "\n"
                "On bare-name input you get back {error, rejected, accepted_forms, hint} — "
                "re-issue the call with one of the accepted forms."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of family-scoped operator types to find together. Each entry must be in one of: 'TOP:noise' (colon), 'noiseTOP' (suffix), 'noise TOP' (space), or 'ALL:noise' (opt-in any-family). Bare names like 'noise' are rejected."
                    },
                    "require_connection": {
                        "type": "boolean",
                        "description": "Whether operators must be connected (default: true)",
                        "default": True
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["operator_types"]
            }
        ),
        Tool(
            name="find_parameter_usage",
            description="Find examples of parameter usage. Use compact=true to get just values (saves ~50K context).",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_type": {
                        "type": "string",
                        "description": "Operator type (e.g., 'analyze', 'filter', 'noise')"
                    },
                    "parameter_name": {
                        "type": "string",
                        "description": "Parameter name (e.g., 'function', 'method', 'type')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 10)",
                        "default": 10
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, returns only unique values found. Default: false",
                        "default": False
                    }
                },
                "required": ["operator_type"]
            }
        ),
        Tool(
            name="find_similar_networks",
            description="Find examples with similar network patterns to a given example. Useful for finding alternative implementations or related techniques.",
            inputSchema={
                "type": "object",
                "properties": {
                    "example_id": {
                        "type": "string",
                        "description": "Example ID (e.g., 'analyzeCHOP/example1')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of similar examples to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["example_id"]
            }
        ),
        Tool(
            name="get_parameter_detail",
            description="Get full description and options for a specific parameter. Use after get_operator_info(compact=true) to drill down into specific params.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_name": {
                        "type": "string",
                        "description": "Operator name (e.g., 'Noise CHOP', 'Level TOP')"
                    },
                    "parameter_name": {
                        "type": "string",
                        "description": "Parameter code name (e.g., 'amp', 'period', 'invert')"
                    }
                },
                "required": ["operator_name", "parameter_name"]
            }
        ),
        Tool(
            name="get_network_patterns",
            description="Get common network patterns found across TouchDesigner examples. Shows frequently-used operator combinations and connection patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_frequency": {
                        "type": "integer",
                        "description": "Minimum number of times pattern must appear (default: 5)",
                        "default": 5
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="td_build_project",
            description=(
                "Build a TouchDesigner .tox from a network design.\n"
                "Required args: `design` (or `network_design` for containers). "
                "Operators take `{name, type, family?, parameters?, uniforms?}`. "
                "Connections take `{from, to}`. Use `table_data` to populate Table DATs.\n"
                "Caveats:\n"
                "1. Disambiguate types that exist in multiple families: pass `family` "
                "(or use the colon-form `'CHOP:noise'` / suffix `'noiseCHOP'`). "
                "Common ambiguous types: noise, constant, null, analyze, level, math, "
                "transform, merge, blend, text.\n"
                "2. Look up operator-specific parameter values via `get_operator_info` "
                "or `find_parameter_usage` rather than guessing — invented types are "
                "now rejected (Wave 3 B08) so build will fail noisily if you fabricate one.\n"
                "3. `embed_tox` is unreliable; prefer the `palette` field or inline builds.\n"
                "See `docs/td_build_project_guide.md` for the full rule set."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "design": {
                        "type": "object",
                        "description": "Network design with 'operators', 'connections', and optional 'containers'. Operators have: name, type, family (optional), position (optional), parameters (optional), uniforms (for GLSL). Example: {\"operators\": [{\"name\": \"noise1\", \"type\": \"noise\", \"family\": \"CHOP\"}], \"connections\": [{\"from\": \"noise1\", \"to\": \"null1\"}]}"
                    },
                    "network_design": {
                        "type": "object",
                        "description": "Advanced network design with containers, embed_tox support for palette components, and hierarchical paths. Takes precedence over 'design' if both provided."
                    },
                    "table_data": {
                        "type": "object",
                        "description": "Dict mapping Table DAT names to 2D arrays of cell values"
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Optional project name. Auto-generated if not provided."
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Optional output directory. Defaults to mcp_server/output."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["toe", "tox"],
                        "default": "tox",
                        "description": "Build mode: toe (project) or tox (component)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="td_validate",
            description=(
                "Validate a TouchDesigner network JSON against the unified 5-stage validation pipeline. "
                "Returns validation report with errors, warnings, and suggestions. "
                "Stages: Schema -> Semantic -> Reference -> Logical -> TD Rules."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {
                        "type": "object",
                        "description": "TD network JSON (builder, extended, or canonical format)"
                    },
                    "format_layer": {
                        "type": "string",
                        "enum": ["builder", "extended", "canonical"],
                        "default": "builder",
                        "description": "Input format layer"
                    },
                    "verbose": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include detailed validation stages"
                    }
                },
                "required": ["network"]
            }
        ),
        Tool(
            name="td_convert",
            description=(
                "Convert TouchDesigner network JSON between format layers. "
                "Supports: builder (AI-friendly) <-> extended (ground truth) <-> canonical (compact). "
                "Always converts through Extended as hub - never directly between Builder and Canonical."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {
                        "type": "object",
                        "description": "TD network JSON to convert"
                    },
                    "source_layer": {
                        "type": "string",
                        "enum": ["builder", "extended", "canonical"],
                        "description": "Source format layer"
                    },
                    "target_layer": {
                        "type": "string",
                        "enum": ["builder", "extended", "canonical"],
                        "description": "Target format layer"
                    }
                },
                "required": ["network", "source_layer", "target_layer"]
            }
        ),
        Tool(
            name="get_expert_prompt",
            description="Get the full prompt/instructions for a specialized TD expert. Use this before complex builds to get the expert's complete knowledge. Available experts: td_designer (network specs), network_builder (file generation), td_glsl_expert (shaders), td_python_expert (scripts), ui_expert (control panels), critic (review).",
            inputSchema={
                "type": "object",
                "properties": {
                    "expert_name": {
                        "type": "string",
                        "enum": ["td_designer", "network_builder", "td_glsl_expert", "td_python_expert", "ui_expert", "critic"],
                        "description": "Name of the expert to load"
                    },
                    "phase": {
                        "type": "string",
                        "enum": ["build", "plan", "self_improve"],
                        "default": "build",
                        "description": "Which phase prompt to load (build is most common)"
                    }
                },
                "required": ["expert_name"]
            }
        ),
        Tool(
            name="get_server_info",
            description="Return runtime identity of this MCP server: working directory, absolute script path, version, server name, Python version, and whether the live-TD client is enabled. Use this to confirm which copy/install of the server is actually running.",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        ),
        Tool(
            name="expand_toe_file",
            description=(
                "Expand a TouchDesigner .toe/.tox file (via toeexpand.exe) and parse it OFFLINE. "
                "mode='summary' (default) returns each node's op_type plus its NON-DEFAULT parameters "
                "with value + mode (constant/expression/reference/bind), and the connection list — "
                "ideal for understanding/explaining an existing network. mode='full' returns the complete "
                "lossless JSON (operator positions + raw files + .toc) that round-trips back into a "
                ".toe.dir/.tox. Also accepts an already-expanded .toe.dir/.tox.dir (skips toeexpand)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "toe_path": {
                        "type": "string",
                        "description": "Absolute path to a .toe/.tox file, or to an already-expanded .toe.dir/.tox.dir."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "summary = node/connection map with non-default params; full = complete round-trippable lossless JSON."
                    }
                },
                "required": ["toe_path"]
            }
        )
    ]

    # Add TD Live Client tools (visual feedback + CRUD) when available
    if TD_LIVE_ENABLED and TD_LIVE_TOOLS:
        tools.extend(TD_LIVE_TOOLS)
        print(f"Added {len(TD_LIVE_TOOLS)} TD Live tools to MCP server", file=sys.stderr)

    return tools


# TD parameter modes (the integer stored in a .parm line; see lossless_parser
# _parse_parameters). 0=constant, 1=expression, 2=export/reference, 3=bind.
_TD_PARM_MODE = {0: "constant", 1: "expression", 2: "reference", 3: "bind"}

_SEQ_PARAM_RE = re.compile(r"^(\D*?)(\d+)(.*)$")


def _collapse_seq_params(params, family_threshold: int = 2, keep_per_family: int = 1):
    """Collapse long repeated TD sequence-param families in a summary.

    TD sequence params look like ``attr0name, attr1name, …`` / ``vec0name, vec1name, …`` /
    ``sampler0extendu, …`` — a glslPOP's Create-Attributes + Vectors pages alone can emit
    dozens of rows, which blew the expand_toe_file(mode='summary') token budget. This keeps
    the first ``keep_per_family`` index of each family and replaces the rest with an
    explicit marker ``{name, collapsed: <count>, note}``. Families with
    ``<= family_threshold`` members (e.g. fromrange1/2) and non-sequence params pass through
    untouched. The omitted count is always reported — never a silent truncation.
    """
    buckets = {}      # family -> [(idx, param)], first-appearance order preserved via `rendered`
    rendered = []     # ("plain", param) | ("seq", family)
    for p in params:
        m = _SEQ_PARAM_RE.match(p.get("name", ""))
        if not m:
            rendered.append(("plain", p))
            continue
        family = f"{m.group(1)}#{m.group(3)}"
        if family not in buckets:
            buckets[family] = []
            rendered.append(("seq", family))
        buckets[family].append((int(m.group(2)), p))

    out = []
    for kind, val in rendered:
        if kind == "plain":
            out.append(val)
            continue
        members = sorted(buckets[val], key=lambda t: t[0])
        if len(members) <= family_threshold:
            out.extend(p for _, p in members)
        else:
            out.extend(p for _, p in members[:keep_per_family])
            omitted = len(members) - keep_per_family
            out.append({
                "name": val,
                "collapsed": omitted,
                "note": f"{omitted} repeated sequence params omitted in summary; use mode='full'",
            })
    return out


def _summarize_td_network(network) -> dict:
    """Compact node/connection summary of a parsed TDNetwork.

    Lists each operator's op_type ("FAMILY:type") and only its NON-DEFAULT
    parameters (TouchDesigner writes only changed params to .parm), each with
    its value and mode (constant/expression/reference/bind).
    """
    from core.models import ParameterValue

    operators = []
    for op in network.operators:
        params = []
        for pname, pval in (op.parameters or {}).items():
            if isinstance(pval, ParameterValue):
                label = _TD_PARM_MODE.get(
                    pval.td_mode, "expression" if pval.expression else "constant"
                )
                value = pval.value if label == "constant" else (
                    pval.expression if pval.expression is not None else pval.value
                )
            else:
                label, value = "constant", pval
            params.append({"name": pname, "value": value, "mode": label})
        operators.append({
            "path": op.path,
            "op_type": op.op_type or (f"{op.family.value}:{op.type}" if op.family else op.type),
            "params": _collapse_seq_params(params),
        })

    connections = [
        {"from": c.source, "to": c.target,
         "source_output": c.source_output, "target_input": c.target_input}
        for c in network.connections
    ]
    by_family = network.statistics.by_family if (network.statistics and network.statistics.by_family) else {}
    return {
        "project_name": network.metadata.project_name,
        "mode": network.metadata.mode,
        "node_count": len(network.operators),
        "connection_count": len(network.connections),
        "by_family": by_family,
        "operators": operators,
        "connections": connections,
    }


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[Union[TextContent, ImageContent]]:
    """Handle tool calls"""
    
    try:
        # Non-blocking KB readiness check for KB-dependent tools.
        # If the background warmup hasn't finished yet, return a structured
        # "kb_warming" response so the caller can wait and retry instead of
        # blocking the MCP request and hitting the client timeout.
        # If the KB partially or fully failed to load (missing files, missing
        # deps, init exception), return a structured error naming the fix.
        if name in _KB_DEPENDENT_TOOLS:
            kb_err = _kb_check(needs_semantic=(name == "hybrid_search"))
            if kb_err is not None:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "ok": False,
                        "data": None,
                        "error": kb_err,
                        "meta": {"tool": name, "server": SERVER_NAME},
                    }, indent=2),
                )]

        if name == "hybrid_search":
            query = arguments["query"]
            n_results = arguments.get("n_results", 5)
            
            if not hybrid_search:
                return [TextContent(type="text", text="ERROR: Hybrid search not initialized")]
            
            results = hybrid_search.search(query, n_results=n_results)

            # Enrich results with full parameter data from knowledge_graph.
            # hybrid_search.search() returns a dict {query, semantic_results, relationships, ...};
            # the list of per-document hits lives under 'semantic_results', and the operator name
            # lives in each hit's 'metadata' dict.
            if knowledge_graph and isinstance(results, dict):
                for result in results.get('semantic_results', []):
                    if not isinstance(result, dict):
                        continue
                    meta = result.get('metadata') if isinstance(result.get('metadata'), dict) else {}
                    op_name = meta.get('operator_name') or result.get('operator_name') or result.get('name')
                    if op_name:
                        try:
                            full_info = knowledge_graph.get_operator_info(op_name)
                            if full_info and 'wiki_parameters' in full_info:
                                result['parameters'] = full_info['wiki_parameters']
                                result['parameter_count'] = len(full_info['wiki_parameters'])
                                if full_info.get('ground_truth_param_count'):
                                    result['ground_truth_param_count'] = full_info['ground_truth_param_count']
                        except Exception:
                            pass

            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]

        elif name == "get_operator_info":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Tools not initialized")]

            operator_name = arguments["operator_name"]
            compact = arguments.get("compact", False)

            # Use knowledge_graph (UnifiedGraphQuery) for comprehensive operator info
            info = knowledge_graph.get_operator_info(operator_name)

            # Compact mode: return essential fields + all params with types
            if compact and info:
                # Extract all parameters with their types
                params_compact = {}
                wiki_params = info.get("wiki_parameters", {})

                # Handle both dict and list formats
                if isinstance(wiki_params, dict):
                    # Dict format: {"param_code": {"description": ..., ...}}
                    for code, p in wiki_params.items():
                        if isinstance(p, dict):
                            ptype = p.get("type", "unknown")
                            desc = p.get("description", "")
                            # Infer type from description if not explicit
                            if ptype == "unknown":
                                desc_lower = desc.lower()
                                if "menu" in desc_lower or "dropdown" in desc_lower:
                                    ptype = "menu"
                                elif "toggle" in desc_lower or "on/off" in desc_lower:
                                    ptype = "toggle"
                                elif any(x in desc_lower for x in ["float", "decimal", "0.0"]):
                                    ptype = "float"
                                elif any(x in desc_lower for x in ["integer", "whole number"]):
                                    ptype = "int"
                            params_compact[code] = ptype
                        else:
                            params_compact[code] = str(type(p).__name__)
                elif isinstance(wiki_params, list):
                    for p in wiki_params:
                        if isinstance(p, dict):
                            code = p.get("code", p.get("name", ""))
                            ptype = p.get("type", "unknown")
                            # Normalize type names
                            if "menu" in ptype.lower():
                                ptype = "menu"
                            elif "float" in ptype.lower() or ptype in ["XY", "XYZ", "UV", "RGB", "RGBA"]:
                                ptype = "float"
                            elif "int" in ptype.lower():
                                ptype = "int"
                            elif "str" in ptype.lower():
                                ptype = "str"
                            elif "toggle" in ptype.lower() or "bool" in ptype.lower():
                                ptype = "toggle"
                            params_compact[code] = ptype

                compact_info = {
                    "name": info.get("name"),
                    "family": info.get("family"),
                    "type": info.get("op_type") or info.get("type"),
                    "summary": info.get("summary") or info.get("description", "")[:200],
                    "parameters": params_compact,
                    "_note": "Use get_parameter_detail for full descriptions"
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(compact_info, indent=2)
                )]

            return [TextContent(
                type="text",
                text=json.dumps(info, indent=2)
            )]
        
        elif name == "query_graph":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]

            command = arguments["command"]
            compact = arguments.get("compact", False)

            if command == "params":
                operator = arguments.get("operator")
                if not operator:
                    return [TextContent(type="text", text="Error: 'operator' required for 'params' command")]
                result = knowledge_graph.get_operator_parameters(operator)

            elif command == "related":
                operator = arguments.get("operator")
                if not operator:
                    return [TextContent(type="text", text="Error: 'operator' required for 'related' command")]
                result = knowledge_graph.get_related_operators(operator)

            elif command == "family":
                family = arguments.get("family")
                if not family:
                    return [TextContent(type="text", text="Error: 'family' required for 'family' command")]
                result = knowledge_graph.get_operators_by_family(family)

                # Compact mode: return operators categorized by function
                if compact and isinstance(result, list):
                    # Group by function/category based on operator name patterns
                    categories = {}
                    for op in result:
                        if isinstance(op, dict):
                            name = op.get("name", "")
                            # Extract category from name suffix (e.g., "Noise TOP" -> generator)
                            cat = "other"
                            name_lower = name.lower()
                            if any(x in name_lower for x in ["noise", "ramp", "constant", "pattern", "circle", "rectangle"]):
                                cat = "generators"
                            elif any(x in name_lower for x in ["blur", "level", "edge", "sharpen", "hsv", "composite"]):
                                cat = "filters"
                            elif any(x in name_lower for x in ["math", "logic", "trigger", "count", "compare"]):
                                cat = "math"
                            elif any(x in name_lower for x in ["in", "out", "null", "select", "switch"]):
                                cat = "utilities"
                            elif any(x in name_lower for x in ["file", "movie", "audio", "video"]):
                                cat = "io"
                            elif any(x in name_lower for x in ["transform", "crop", "tile", "flip"]):
                                cat = "transform"
                            elif any(x in name_lower for x in ["render", "geo", "light", "camera"]):
                                cat = "3d"
                            elif any(x in name_lower for x in ["chop", "top", "sop", "dat"]):
                                cat = "conversion"
                            if cat not in categories:
                                categories[cat] = []
                            categories[cat].append(name)

                    compact_result = {
                        "family": family,
                        "count": len(result),
                        "categories": {k: sorted(v) for k, v in sorted(categories.items())},
                        "_note": "Use compact=false for full operator details"
                    }
                    return [TextContent(
                        type="text",
                        text=json.dumps(compact_result, indent=2)
                    )]

            else:
                return [TextContent(type="text", text=f"Error: Unknown command '{command}'")]

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        elif name == "list_pop_operators":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            # B22 — delegate to the canonical enumeration used by query_graph(family='POP').
            # Previously this inline-iterated knowledge_graph.nodes (enhanced graph only) and
            # missed wiki-side operators, returning 95 while query_graph(family='POP') returned 100.
            # B28 — drop meta entries (`masterPOP`, `_conceptsPOP` etc.) that aren't real operators.
            ops = knowledge_graph.get_operators_by_family("POP") or []
            result = [
                {
                    "name": op.get("name", ""),
                    "family": (op.get("data") or {}).get("family", "POP"),
                }
                for op in ops
                if op.get("name", "")
                and not op.get("name", "").startswith("_")
                and not op.get("name", "").lower().startswith("master")
            ]
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_operator_examples":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            # Accept both `operator` (schema) and `operator_name` (consistent with
            # get_operator_info/get_parameter_detail) so callers using either work.
            operator = arguments.get("operator") or arguments.get("operator_name")
            if not operator:
                return [TextContent(type="text", text="Error: 'operator' (or 'operator_name') is required")]
            limit = arguments.get("limit", 10)
            # B24 — optional `family` disambiguates bare names. Also accepts
            # colon-form ('TOP:noise') / suffixed-form ('noiseTOP') in the
            # `operator` arg itself; the backend normalises both.
            family = arguments.get("family")
            result = knowledge_graph.find_examples_by_operator(
                operator, limit, family=family,
            )
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_operator_combination":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            operator_types = arguments.get("operator_types", [])
            require_connection = arguments.get("require_connection", True)
            limit = arguments.get("limit", 5)
            result = knowledge_graph.find_examples_by_operator_combination(
                operator_types, require_connection, limit
            )
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_parameter_usage":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            operator_type = arguments.get("operator_type")
            parameter_name = arguments.get("parameter_name")
            limit = arguments.get("limit", 10)
            compact = arguments.get("compact", False)
            result = knowledge_graph.find_parameter_usage(
                operator_type, parameter_name, limit
            )

            # Compact mode: return only unique values to save context
            if compact and isinstance(result, list):
                unique_values = set()
                for item in result:
                    if isinstance(item, dict):
                        # B19 — backend records use `parameter_value`, not `value`.
                        # Keep `value` and `parameter_name` as graceful fallbacks for
                        # any future backend-shape drift.
                        val = item.get("parameter_value") or item.get("value") or item.get(parameter_name)
                        if val is not None:
                            unique_values.add(str(val))
                compact_result = {
                    "operator_type": operator_type,
                    "parameter_name": parameter_name,
                    "example_count": len(result),
                    "unique_values": sorted(list(unique_values)),
                    "_note": "Use compact=false for full example contexts"
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(compact_result, indent=2)
                )]

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_similar_networks":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            example_id = arguments.get("example_id")
            limit = arguments.get("limit", 5)
            result = knowledge_graph.find_similar_networks(example_id, limit)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_parameter_detail":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            operator_name = arguments.get("operator_name")
            parameter_name = arguments.get("parameter_name")

            # Get operator info
            info = knowledge_graph.get_operator_info(operator_name)
            if not info:
                return [TextContent(type="text", text=f"Operator '{operator_name}' not found")]

            # Find the specific parameter - handle both dict and list formats
            wiki_params = info.get("wiki_parameters", {})
            param_detail = None

            if isinstance(wiki_params, dict):
                # Dict format: {"param_code": {"description": ..., ...}}
                for code, p in wiki_params.items():
                    if code.lower() == parameter_name.lower():
                        if isinstance(p, dict):
                            param_detail = {
                                "code": code,
                                "name": p.get("display_name", code),
                                "type": p.get("type", "unknown"),
                                "description": p.get("description", "No description available"),
                                "section": p.get("section", ""),
                                "default": p.get("default"),
                                "options": _build_menu_options(p),
                                "range": p.get("range"),
                            }
                        else:
                            param_detail = {"code": code, "value": str(p)}
                        break
            elif isinstance(wiki_params, list):
                for p in wiki_params:
                    if isinstance(p, dict):
                        code = p.get("code", p.get("name", ""))
                        if code.lower() == parameter_name.lower():
                            param_detail = {
                                "code": code,
                                "name": p.get("display_name", code),
                                "type": p.get("type", "unknown"),
                                "description": p.get("description", "No description available"),
                                "section": p.get("section", ""),
                                "default": p.get("default"),
                                "options": _build_menu_options(p),
                                "range": p.get("range"),
                            }
                            break

            if not param_detail:
                return [TextContent(type="text", text=f"Parameter '{parameter_name}' not found on operator '{operator_name}'")]

            return [TextContent(
                type="text",
                text=json.dumps(param_detail, indent=2)
            )]

        elif name == "get_network_patterns":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            min_frequency = arguments.get("min_frequency", 5)
            result = knowledge_graph.get_network_patterns(min_frequency)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "td_build_project":
            # Support both 'design' (simple) and 'network_design' (advanced with containers)
            network_design = arguments.get("network_design")
            design = arguments.get("design", {})
            table_data = arguments.get("table_data", {})
            project_name = arguments.get("project_name")
            output_dir = arguments.get("output_dir")
            mode = arguments.get("mode", "tox")

            # B08 — pre-validate operator types against OperatorRegistry. Catches
            # invented type strings (e.g. "POP:sourcePOP") before producing a broken .tox.
            # Walks both the flat `operators` list and any nested `containers[*].operators` /
            # `containers[*].network.operators`. Accepts colon-form ("CHOP:noise") and
            # separate-family form ({"family":"CHOP","type":"noise"}).
            if UNIFIED_SYSTEM_ENABLED:
                def _collect_ops(design_dict):
                    d = design_dict or {}
                    ops = list(d.get("operators", []) or [])
                    for c in d.get("containers", []) or []:
                        ops.extend(c.get("operators", []) or [])
                        net = c.get("network", {}) or {}
                        ops.extend(net.get("operators", []) or [])
                    return ops

                unknown = []
                for op in _collect_ops(network_design or design):
                    if not isinstance(op, dict):
                        continue
                    raw = (op.get("type") or "").strip()
                    if not raw:
                        continue
                    if ":" in raw:
                        full = raw
                    else:
                        fam = (op.get("family") or "").strip()
                        if not fam:
                            unknown.append(raw)
                            continue
                        full = f"{fam}:{raw}"
                    if not _registry.get_operator_by_type(full):
                        unknown.append(full)
                if unknown:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "ERROR",
                        "message": "Unknown operator types — not in registry",
                        "unknown_types": sorted(set(unknown)),
                        "hint": "Use query_graph(command='family') or hybrid_search to look up valid types.",
                    }, indent=2))]

            # If network_design is provided, use ToeBuilderBridge for advanced features
            if network_design and EXPERT_WORKFLOW_ENABLED:
                try:
                    if not output_dir:
                        output_dir = str(Path(__file__).parent / "output")
                    Path(output_dir).mkdir(parents=True, exist_ok=True)

                    if not project_name:
                        import time
                        project_name = f"td_project_{int(time.time()) % 10000}"

                    # Use ToeBuilderBridge for advanced features
                    if mode == "tox":
                        bridge = ToxBuilder(output_dir, verbose=True)
                        result_path = bridge.build_tox(network_design, project_name)
                    else:
                        bridge = ToeBuilderBridge(Path(output_dir))
                        result_path = bridge.build_from_design(network_design, project_name)

                    # Count operators and connections
                    op_count = len(network_design.get("operators", []))
                    conn_count = len(network_design.get("connections", []))
                    for container in network_design.get("containers", []):
                        op_count += len(container.get("operators", []))
                        conn_count += len(container.get("connections", []))
                        network = container.get("network", {})
                        conn_count += len(network.get("connections", []))

                    if result_path and Path(result_path).exists():
                        file_size = Path(result_path).stat().st_size
                        result = {
                            "status": "SUCCESS",
                            "builder": "ToeBuilderBridge",
                            "output_file": str(result_path),
                            "file_size": file_size,
                            "operators": op_count,
                            "connections": conn_count,
                            "features_used": {
                                "containers": len(network_design.get("containers", [])) > 0,
                                "embed_tox": any(
                                    op.get("embed_tox")
                                    for container in network_design.get("containers", [])
                                    for op in container.get("operators", [])
                                )
                            }
                        }
                    else:
                        result = {
                            "status": "ERROR",
                            "message": "Build completed but file was not created",
                            "attempted_path": str(result_path) if result_path else "None"
                        }
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                except Exception as e:
                    import traceback
                    return [TextContent(type="text", text=json.dumps({
                        "status": "ERROR",
                        "builder": "ToeBuilderBridge",
                        "message": str(e),
                        "traceback": traceback.format_exc()
                    }, indent=2))]

            # Fall back to original td_build_project for simple design
            if table_data:
                design["table_data"] = table_data
            result = await td_build_project(design, project_name, output_dir)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "td_validate":
            if not UNIFIED_SYSTEM_ENABLED:
                return [TextContent(type="text", text=json.dumps({
                    "error": "Unified system validation not available",
                    "hint": "Check unified_system imports"
                }, indent=2))]

            try:
                network_json = arguments.get("network")
                if not network_json:
                    return [TextContent(type="text", text="Error: 'network' is required")]

                format_layer = arguments.get("format_layer", "builder")
                verbose = arguments.get("verbose", False)

                # Convert to TDNetwork if needed
                if format_layer == "builder":
                    network = _converter.from_builder(network_json)
                elif format_layer == "canonical":
                    network = _converter.from_canonical(network_json)
                else:  # extended
                    network = _converter.from_builder(network_json)

                # Validate
                project_name = network_json.get("meta", {}).get("project_name", "network")
                report = _validator.validate(network, project_name)

                # Build response
                result = {
                    "valid": report.valid,
                    "total_errors": report.total_errors,
                    "total_warnings": report.total_warnings,
                    "errors": [{"stage": e.stage, "message": e.message, "severity": e.severity}
                              for e in report.get_errors()],
                    "warnings": [{"stage": w.stage, "message": w.message, "severity": w.severity}
                                for w in report.get_warnings()]
                }

                if verbose:
                    result["stages"] = {}
                    for stage_report in report.stages:
                        result["stages"][stage_report.stage] = {
                            "passed": stage_report.status == "PASS",
                            "errors": len(stage_report.errors),
                            "warnings": len(stage_report.warnings)
                        }

                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except Exception as e:
                import traceback
                return [TextContent(type="text", text=json.dumps({
                    "error": f"Validation error: {str(e)}",
                    "traceback": traceback.format_exc()
                }, indent=2))]

        elif name == "td_convert":
            if not UNIFIED_SYSTEM_ENABLED:
                return [TextContent(type="text", text=json.dumps({
                    "error": "Unified system format converter not available",
                    "hint": "Check unified_system imports"
                }, indent=2))]

            try:
                network_json = arguments.get("network")
                if not network_json:
                    return [TextContent(type="text", text="Error: 'network' is required")]

                source_layer = arguments.get("source_layer")
                target_layer = arguments.get("target_layer")

                if not source_layer or not target_layer:
                    return [TextContent(type="text", text="Error: 'source_layer' and 'target_layer' are required")]

                # Convert source -> Extended (ground truth)
                if source_layer == "builder":
                    network = _converter.from_builder(network_json)
                elif source_layer == "canonical":
                    network = _converter.from_canonical(network_json)
                else:  # already extended
                    network = _converter.from_builder(network_json)

                # Convert Extended -> target
                if target_layer == "builder":
                    result_json = _converter.to_builder(network)
                elif target_layer == "canonical":
                    result_json = _converter.to_canonical(network)
                else:  # extended
                    result_json = _converter.to_builder(network)
                    result_json["format_layer"] = "extended"

                return [TextContent(type="text", text=json.dumps(result_json, indent=2))]
            except Exception as e:
                import traceback
                return [TextContent(type="text", text=json.dumps({
                    "error": f"Conversion error: {str(e)}",
                    "traceback": traceback.format_exc()
                }, indent=2))]

        elif name == "get_expert_prompt":
            expert_name = arguments["expert_name"]
            phase = arguments.get("phase", "build")
            prompt_content = load_expert_prompt(expert_name, phase)
            return [TextContent(
                type="text",
                text=prompt_content
            )]

        elif name == "get_server_info":
            info = {
                "ok": True,
                "data": {
                    "server_name": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "script_path": str(Path(__file__).resolve()),
                    "cwd": os.getcwd(),
                    "python": sys.version.split()[0],
                    "td_live_enabled": TD_LIVE_ENABLED,
                },
                "meta": {"tool": "get_server_info", "server": SERVER_NAME},
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        elif name == "expand_toe_file":
            import shutil as _shutil
            import subprocess as _subprocess
            import tempfile as _tempfile
            import glob as _glob

            def _expand_err(msg, hint=None):
                err = {"message": msg}
                if hint:
                    err["hint"] = hint
                return [TextContent(type="text", text=json.dumps({
                    "ok": False, "data": None, "error": err,
                    "meta": {"tool": "expand_toe_file", "server": SERVER_NAME},
                }, indent=2))]

            toe_path_arg = arguments.get("toe_path")
            out_mode = (arguments.get("mode") or "summary").lower()
            if not toe_path_arg:
                return _expand_err("Missing required argument 'toe_path'.")
            if out_mode not in ("summary", "full"):
                return _expand_err(f"Invalid mode '{out_mode}'. Use 'summary' or 'full'.")
            src = Path(toe_path_arg)
            if not src.exists():
                return _expand_err(f"Path not found: {src}",
                                   "Pass an absolute path to a .toe/.tox file or an expanded .toe.dir/.tox.dir.")

            cleanup_dir = None
            if src.is_dir() and src.name.endswith(".dir"):
                toe_dir = src
            elif src.is_file() and src.suffix.lower() in (".toe", ".tox"):
                from paths import resolve_td_tool
                exe = resolve_td_tool("toeexpand")
                if not exe:
                    return _expand_err(
                        "toeexpand not found.",
                        "Install TouchDesigner (it provides toeexpand), set TD_TOEEXPAND/TD_BIN_DIR, "
                        "or pass an already-expanded .toe.dir.")
                work = Path(_tempfile.mkdtemp(prefix="td_expand_"))
                cleanup_dir = work
                work_proj = work / src.name
                _shutil.copy2(src, work_proj)
                # toeexpand returns rc 1 even on success on some builds.
                proc = _subprocess.run([str(exe), str(work_proj)], cwd=str(work),
                                       capture_output=True, text=True)
                toe_dir = work / f"{src.name}.dir"
                if not toe_dir.exists():
                    alts = list(work.glob("*.dir"))
                    if alts:
                        toe_dir = alts[0]
                    else:
                        _shutil.rmtree(work, ignore_errors=True)
                        return _expand_err(
                            f"toeexpand produced no .dir output (rc={proc.returncode}).",
                            (proc.stderr or proc.stdout or "").strip()[:500] or None)
            else:
                return _expand_err(f"Unsupported input: {src}",
                                   "Expected a .toe/.tox file or an expanded .toe.dir/.tox.dir.")

            try:
                from parsers.lossless_parser import parse_toe_lossless
                network = parse_toe_lossless(toe_dir, registry=None, verbose=False)
                if out_mode == "full":
                    from core.lossless_json import to_lossless_json_dict
                    data = to_lossless_json_dict(network)
                else:
                    data = _summarize_td_network(network)
            except Exception as pe:
                return _expand_err(f"Failed to parse expanded network: {pe}")
            finally:
                if cleanup_dir is not None:
                    _shutil.rmtree(cleanup_dir, ignore_errors=True)

            return [TextContent(type="text", text=json.dumps({
                "ok": True, "data": data,
                "meta": {"tool": "expand_toe_file", "server": SERVER_NAME, "mode": out_mode},
            }, indent=2, default=str))]

        # TD Live Client tools (visual feedback + CRUD)
        elif TD_LIVE_ENABLED and name in TD_LIVE_HANDLERS:
            handler = TD_LIVE_HANDLERS[name]
            return await handler(arguments)

        else:
            return [TextContent(
                type="text",
                text=f"Error: Unknown tool '{name}'"
            )]
            
    except Exception as e:
        import traceback
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}\n{traceback.format_exc()}"
        )]


async def main():
    """Run the MCP server"""
    # Restore real stdout for MCP JSON-RPC protocol. See top-of-file
    # stdout-pollution guard.
    sys.stdout = _real_stdout
    print(
        f"[td-builder] {SERVER_NAME} v{SERVER_VERSION} starting | "
        f"script={Path(__file__).resolve()} | cwd={os.getcwd()} | "
        f"td_live={TD_LIVE_ENABLED}",
        file=sys.stderr,
    )
    # Warm the KB in the background so the first KB-dependent tool call
    # doesn't pay the ~1-2 min load on a silent socket (clients time out at
    # ~4 min). Non-blocking: get_server_info / live-TD stay instant; a first
    # KB call either finds it already warm or briefly waits on _kb_lock.
    #
    # Delay 2s before kicking off the load: _load_kb() mutates sys.stdout
    # process-wide for the duration of the load (see stdout-pollution guard
    # at line 446), so if it fires before the MCP `initialize` response is
    # flushed, that response gets written to stderr and Claude Desktop's
    # 60s handshake timeout fires. The sleep ensures stdio_server has
    # already completed the handshake by the time the swap happens.
    def _delayed_kb_warmup():
        time.sleep(2.0)
        _ensure_kb()
    threading.Thread(target=_delayed_kb_warmup, name="kb-warmup", daemon=True).start()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
