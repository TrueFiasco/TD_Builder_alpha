#!/usr/bin/env python3
"""
TouchDesigner MCP Server with Multi-Agent System
Spawns specialized engineer agents for knowledge extraction
"""

import sys
import json
import asyncio
import os
from pathlib import Path
from typing import Any, Sequence, Dict, Callable, List, Union
import base64
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))

# Add unified_system to path for validation and format conversion
UNIFIED_SYSTEM_ROOT = Path(__file__).parent.parent / "unified_system"
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
    print("TD Live Client enabled (20 tools for running TD)", file=sys.stderr)
except ImportError as e:
    TD_LIVE_ENABLED = False
    TD_LIVE_TOOLS = []
    TD_LIVE_HANDLERS = {}
    print(f"WARNING: TD Live Client not available: {e}", file=sys.stderr)

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

try:
    import anthropic
except ImportError:
    print("WARNING: anthropic package not installed - agent spawning will not work", file=sys.stderr)
    anthropic = None

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
except ImportError as e:
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

ENGINEER_SKILLS = {
    "snippet_extractor": {
        "skill_file": "snippet_extractor.md",
        "description": "Extract operator examples and knowledge from .tox files",
        "output_format": "json"
    },
    "workflow_analyzer": {
        "skill_file": "workflow_analyzer.md",
        "description": "Analyze .toe files to find common operator chain patterns",
        "output_format": "json"
    },
    "concept_generator": {
        "skill_file": "concept_generator.md",
        "description": "Generate semantic concept taxonomy from operators",
        "output_format": "json"
    },
    "knowledge_validator": {
        "skill_file": "knowledge_validator.md",
        "description": "Validate extracted knowledge against documentation",
        "output_format": "json"
    }
,
    
    "data_source_auditor": {
        "skill_file": "data_source_auditor.md",
        "description": "Audit all data sources and create extraction strategy",
        "output_format": "json"
    }}

# Expert prompts for td_designer, network_builder, etc.
EXPERTS_DIR = Path(__file__).parent / "meta_agentic" / "experts"

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
    "cg_expert": {
        "description": "Computer graphics and 3D rendering expert. Knows geometry, materials, lighting, cameras.",
        "files": ["build.md"]
    },
    "creative_expert": {
        "description": "Creative direction and artistic design. Guides visual and aesthetic decisions.",
        "files": ["build.md"]
    },
}
# Roster cleanup (H1/M20/M21): summary_generator, format_reverse_engineer, and
# creative_orchestrator were registered here historically but never invoked by
# V2-V6 strategies and not reachable via the standard expert loader. Moved to
# archive/experts_unused/ — keep this dict in sync with EXPERT_IDS.

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


class AgentWithTools:
    """Agent that can request tool executions via structured protocol"""
    
    def __init__(self, api_key: str = None):
        if anthropic is None:
            raise ImportError("anthropic package required for agent spawning")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
    def spawn_agent_with_tool_access(
        self,
        agent_name: str,
        agent_skill: str,
        input_data: Dict,
        tool_executor: Callable,
        max_tool_calls: int = 100
    ) -> Dict:
        """Spawn an agent that can make tool requests"""
        
        system_prompt = f"""
{agent_skill}

TOOL ACCESS PROTOCOL:

When you need a tool, output: TOOL_REQUEST: {{"tool": "tool_name", "params": {{...}}}}
You will receive: TOOL_RESULT: {{"result": ...}}

AVAILABLE TOOLS:
- hybrid_search: Search TD docs
  Params: {{"query": "search text", "n_results": 5}}

- get_operator_info: Get complete operator details
  Params: {{"operator_name": "Grid SOP"}}

- query_graph: Query knowledge graph
  Params: {{"command": "params"|"related"|"family", "operator": "Name", "family": "SOP"}}

- list_pop_operators: List all POP operators
  Params: {{}}

- find_operator_examples: Find real examples of an operator
  Params: {{"operator": "analyze", "limit": 10}}

- find_operator_combination: Find examples using multiple operators
  Params: {{"operator_types": ["noise", "analyze"], "require_connection": true, "limit": 5}}

- find_parameter_usage: Find real parameter values from examples
  Params: {{"operator_type": "analyze", "parameter_name": "function", "limit": 10}}

- find_similar_networks: Find similar network patterns
  Params: {{"example_id": "analyzeCHOP/example1", "limit": 5}}

- get_network_patterns: Get common network patterns
  Params: {{"min_frequency": 5}}

- write_file: Write content to file
  Params: {{"file_path": "path", "content": "data"}}

- list_directory: List directory contents
  Params: {{"path": "path/to/dir"}}

After all tool calls, output your final deliverable as JSON.

Your task begins below:
"""
        
        conversation = [
            {"role": "user", "content": json.dumps(input_data, indent=2)}
        ]
        
        tool_calls_made = 0
        
        print(f"Spawning {agent_name}...", file=sys.stderr)
        
        while tool_calls_made < max_tool_calls:
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8000,
                    system=system_prompt,
                    messages=conversation
                )
                
                assistant_message = response.content[0].text
                
                if "TOOL_REQUEST:" in assistant_message:
                    start_idx = assistant_message.index("TOOL_REQUEST:") + len("TOOL_REQUEST:")
                    json_start = assistant_message.index("{", start_idx)
                    brace_count = 0
                    json_end = json_start
                    for i, char in enumerate(assistant_message[json_start:], json_start):
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    
                    tool_request_str = assistant_message[json_start:json_end]
                    tool_request = json.loads(tool_request_str)
                    
                    print(f"Tool: {tool_request['tool']}", file=sys.stderr)
                    
                    tool_result = tool_executor(
                        tool_name=tool_request["tool"],
                        tool_params=tool_request.get("params", {})
                    )
                    
                    conversation.append({
                        "role": "assistant",
                        "content": assistant_message
                    })
                    conversation.append({
                        "role": "user", 
                        "content": f"TOOL_RESULT: {json.dumps({'result': tool_result}, indent=2)}"
                    })
                    
                    tool_calls_made += 1
                    
                else:
                    print(f"{agent_name} complete", file=sys.stderr)
                    
                    try:
                        if "{" in assistant_message and "}" in assistant_message:
                            json_start = assistant_message.index("{")
                            json_end = assistant_message.rindex("}") + 1
                            result = json.loads(assistant_message[json_start:json_end])
                            return result
                        else:
                            return {"output": assistant_message, "raw": True}
                    except json.JSONDecodeError:
                        return {"output": assistant_message, "raw": True}
                        
            except Exception as e:
                print(f"Error in {agent_name}: {e}", file=sys.stderr)
                return {"error": str(e)}
        
        return {"error": f"Max tool calls ({max_tool_calls}) reached", "partial_output": assistant_message}


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
    _kb = Path(__file__).parent.parent / "KB"
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
_KB_READY = False
_kb_lock = threading.Lock()  # serializes warm-up thread vs first KB tool call


def _ensure_kb():
    """Build the knowledge graph + unified search on first use (idempotent).

    One-time ~1-2 min cost on the FIRST KB-dependent tool call; instant
    afterwards. Keeps startup, the MCP handshake, get_server_info and the
    live-TD tools fast and responsive.
    """
    global _KB_READY
    if _KB_READY:
        return
    with _kb_lock:
        if _KB_READY:  # double-checked: warm-up thread vs first KB call
            return
        _load_kb()


def _load_kb():
    """One-time KB + search construction. Always runs under _kb_lock."""
    global knowledge_graph, hybrid_search, _KB_READY
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
        try:
            if enhanced_graph_path.exists() and graphrag_json_path.exists():
                print("Loading unified knowledge graph (wiki + examples)", file=sys.stderr)
                knowledge_graph = UnifiedGraphQuery(
                    graphrag_json_path=str(graphrag_json_path),
                    enhanced_graph_path=str(enhanced_graph_path),
                    enriched_wiki_path=str(enriched_wiki_path),
                )
                print(f"Loaded unified TD knowledge graph with {len(knowledge_graph.nodes)} nodes", file=sys.stderr)
            else:
                print("WARNING: KB graph/graphrag files not found", file=sys.stderr)
                knowledge_graph = None

            if UnifiedSearchAdapter is not None and enhanced_graph_path.exists() and vectordb_path.exists():
                try:
                    hybrid_search = UnifiedSearchAdapter(
                        graph_path=str(enhanced_graph_path),
                        vectordb_path=str(vectordb_path),
                        use_legacy=False,
                    )
                    print("Loaded unified search", file=sys.stderr)
                except Exception as e:
                    print(f"WARNING: Could not initialize unified search: {e}", file=sys.stderr)
                    hybrid_search = None
            else:
                hybrid_search = None
        except Exception as e:
            print(f"WARNING: Could not initialize TD search: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            knowledge_graph = None
            hybrid_search = None
    finally:
        sys.stdout = _saved_stdout
        # Mark ready after the attempt (success OR graceful-fail) so
        # concurrent callers waited on _kb_lock and there's no retry-storm.
        _KB_READY = True

app = Server("touchdesigner-mcp-server")

SERVER_NAME = "touchdesigner-mcp-server"
SERVER_VERSION = "0.1.0-alpha"

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


async def spawn_engineer(engineer_type: str, task_spec: Dict) -> Dict:
    """Spawn a specialized engineer agent"""

    if anthropic is None:
        return {
            "status": "ERROR",
            "message": "Anthropic package not installed"
        }

    if engineer_type not in ENGINEER_SKILLS:
        return {
            "status": "ERROR",
            "message": f"Unknown engineer type: {engineer_type}",
            "available": list(ENGINEER_SKILLS.keys())
        }

    try:
        agent_system = AgentWithTools()
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Could not initialize agent system: {e}"
        }

    agents_dir = Path(__file__).parent / "agents"
    skill_file = ENGINEER_SKILLS[engineer_type]["skill_file"]
    skill_path = agents_dir / skill_file

    if not skill_path.exists():
        return {
            "status": "ERROR",
            "message": f"Skill file not found: {skill_path}",
            "expected_path": str(skill_path)
        }

    try:
        with open(skill_path, encoding='utf-8') as f:
            engineer_skill = f.read()
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Could not load skill file: {e}"
        }

    print(f"SPAWNING ENGINEER: {engineer_type}", file=sys.stderr)

    result = agent_system.spawn_agent_with_tool_access(
        agent_name=engineer_type,
        agent_skill=engineer_skill,
        input_data=task_spec,
        tool_executor=execute_tool_for_agent
    )

    if "error" in result:
        return {
            "status": "FAILED",
            "engineer": engineer_type,
            "error": result["error"]
        }

    return {
        "status": "SUCCESS",
        "engineer": engineer_type,
        "output": result
    }


async def spawn_expert(expert_type: str, task: str, phase: str = "build") -> Dict:
    """Spawn a specialized expert agent from meta_agentic/experts"""

    if anthropic is None:
        return {
            "status": "ERROR",
            "message": "Anthropic package not installed"
        }

    if expert_type not in AVAILABLE_EXPERTS:
        return {
            "status": "ERROR",
            "message": f"Unknown expert type: {expert_type}",
            "available": list(AVAILABLE_EXPERTS.keys())
        }

    try:
        agent_system = AgentWithTools()
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Could not initialize agent system: {e}"
        }

    # Load expert prompt from meta_agentic/experts/{expert_type}/{phase}.md
    expert_prompt = load_expert_prompt(expert_type, phase)

    if expert_prompt.startswith("ERROR"):
        return {
            "status": "ERROR",
            "message": expert_prompt
        }

    print(f"SPAWNING EXPERT: {expert_type} ({phase} phase)", file=sys.stderr)

    # Prepare task input
    task_input = {
        "task": task,
        "expert_type": expert_type,
        "phase": phase
    }

    result = agent_system.spawn_agent_with_tool_access(
        agent_name=f"{expert_type}_{phase}",
        agent_skill=expert_prompt,
        input_data=task_input,
        tool_executor=execute_tool_for_agent
    )

    if "error" in result:
        return {
            "status": "FAILED",
            "expert": expert_type,
            "phase": phase,
            "error": result["error"]
        }

    return {
        "status": "SUCCESS",
        "expert": expert_type,
        "phase": phase,
        "output": result
    }


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

        # Handle palette embedding
        if 'palette' in design:
            palette_name = design['palette']
            palette_dir = Path(__file__).parent / "data" / "palette_lossless"
            palette_file = palette_dir / f"{palette_name}.json.gz"

            print(f"Loading palette: {palette_name} from {palette_file}", file=sys.stderr)

            if not palette_file.exists():
                return {
                    "status": "ERROR",
                    "message": f"Palette '{palette_name}' not found at {palette_file}"
                }

            # Load and decompress palette JSON
            with gzip.open(palette_file, 'rt', encoding='utf-8') as f:
                palette_data = json.load(f)

            print(f"Loaded palette with {len(palette_data.get('operators', {}))} operators", file=sys.stderr)

            # Build using lossless builder for palette
            # Import the lossless builder
            lossless_builder_path = Path(__file__).parent / "builders"
            sys.path.insert(0, str(lossless_builder_path))
            from json_to_dir_LOSSLESS import LosslessJsonToDirConverter

            # Build palette TOX
            tox_name = project_name or palette_name
            converter = LosslessJsonToDirConverter(palette_data)
            tox_path = Path(output_dir) / f"{tox_name}.tox"
            converter.convert(str(tox_path))

            # Collapse to .tox
            import subprocess
            toc_path = Path(output_dir) / f"{tox_name}.tox.toc"
            if toc_path.exists():
                subprocess.run([
                    "C:/Program Files/Derivative/TouchDesigner/bin/toecollapse.exe",
                    str(toc_path)
                ], capture_output=True)

            if tox_path.exists():
                return {
                    "status": "SUCCESS",
                    "file": str(tox_path),
                    "size": tox_path.stat().st_size,
                    "operators": len(palette_data.get('operators', {})),
                    "connections": len(palette_data.get('connections', [])),
                    "palette": palette_name
                }
            else:
                return {
                    "status": "ERROR",
                    "message": f"Failed to build palette TOX"
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
            name="spawn_engineer",
            description="Spawn a specialized engineer agent to execute knowledge extraction tasks. Engineers can analyze .tox files, extract patterns, generate concepts, and validate knowledge. Returns structured JSON output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engineer_type": {
                        "type": "string",
                        "enum": list(ENGINEER_SKILLS.keys()),
                        "description": "Type of engineer to spawn: snippet_extractor, workflow_analyzer, concept_generator, or knowledge_validator"
                    },
                    "task_spec": {
                        "type": "object",
                        "description": "Task specification with all required inputs for the engineer"
                    }
                },
                "required": ["engineer_type", "task_spec"]
            }
        ),
        Tool(
            name="spawn_expert",
            description="""Spawn a specialized expert agent for complex TouchDesigner tasks.

Experts have deep domain knowledge loaded from comprehensive build.md prompts. They can perform sophisticated tasks that require understanding of TD conventions, best practices, and common pitfalls.

Available experts:
- td_designer: Network design and operator selection. Knows TD operators, parameters, menu values, connection patterns, and build validation rules.
- network_builder: Build .toe/.tox files from network specifications. Handles parameter values, connections, file generation, and mandatory td_build_project tool calls.
- td_glsl_expert: GLSL shader development for TouchDesigner. Knows GLSL TOP patterns, uniforms, TD-specific shader conventions.
- td_python_expert: Python scripting for TouchDesigner automation. Knows TD Python API, callbacks, extensions, and module patterns.
- ui_expert: TouchDesigner UI and control panel design. Knows widget patterns, container layouts, parameter binding.
- critic: Review and score outputs. Flags issues, validates against requirements, suggests improvements.
- cg_expert: Computer graphics and 3D rendering expert. Knows geometry, materials, lighting, cameras.
- creative_expert: Creative direction and artistic design. Guides visual and aesthetic decisions.
- creative_orchestrator: Orchestrates multiple experts for complex creative projects.
- format_reverse_engineer: Reverse engineers TD file formats and binary structures.
- summary_generator: Generates summaries and documentation for TD networks and operators.

Use spawn_expert when:
- Task requires deep TD domain knowledge
- Need validation of parameter values before building
- Building complex networks with multiple operators
- Need expert review of designs or code
- Require understanding of TD conventions and best practices""",
            inputSchema={
                "type": "object",
                "properties": {
                    "expert_type": {
                        "type": "string",
                        "enum": list(AVAILABLE_EXPERTS.keys()),
                        "description": "Type of expert to spawn"
                    },
                    "task": {
                        "type": "string",
                        "description": "Task description for the expert to complete"
                    },
                    "phase": {
                        "type": "string",
                        "enum": ["build", "plan", "self_improve"],
                        "default": "build",
                        "description": "Expert phase to run (build is most common)"
                    }
                },
                "required": ["expert_type", "task"]
            }
        ),
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
                "required": ["operator_type", "parameter_name"]
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
            name="td_compact_expertise",
            description=(
                "Compact meta-agentic expertise event log into expertise_state.yaml and optionally refresh legacy YAML "
                "views. Uses append-only JSONL -> YAML compaction per INTEROP_AND_POLICY.md."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "refresh_yaml": {
                        "type": "boolean",
                        "default": True,
                        "description": "Also refresh legacy YAML views after compaction"
                    },
                    "events_path": {
                        "type": "string",
                        "description": "Optional override for events JSONL path"
                    },
                    "state_path": {
                        "type": "string",
                        "description": "Optional override for state YAML path"
                    }
                },
                "required": []
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
        )
    ]

    # Add TD Live Client tools (visual feedback + CRUD) when available
    if TD_LIVE_ENABLED and TD_LIVE_TOOLS:
        tools.extend(TD_LIVE_TOOLS)
        print(f"Added {len(TD_LIVE_TOOLS)} TD Live tools to MCP server", file=sys.stderr)

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[Union[TextContent, ImageContent]]:
    """Handle tool calls"""
    
    try:
        # Mode-1 / Mode-2 portability: the only API-coupled tools degrade
        # gracefully with no provider key (never crash, never block Mode-1).
        if name in ("spawn_engineer", "spawn_expert") and (
            anthropic is None or not os.environ.get("ANTHROPIC_API_KEY")
        ):
            return [TextContent(type="text", text=json.dumps({
                "ok": False,
                "data": None,
                "error": {
                    "message": f"'{name}' requires an API key (Mode 2)",
                    "hint": "Set ANTHROPIC_API_KEY in the MCP server env. "
                            "See docs/MODES.md. Every other tool works "
                            "key-free (Mode 1).",
                },
                "meta": {"tool": name, "server": SERVER_NAME},
            }, indent=2))]

        # Lazy-load the heavy KB only when a KB-dependent tool is first
        # called. Run it OFF the event loop (asyncio.to_thread): _ensure_kb
        # may block ~1-2 min on _kb_lock while the background warm-up thread
        # finishes the model load. Doing this synchronously would freeze the
        # whole server (no pings/other tools) during that window.
        if name in _KB_DEPENDENT_TOOLS:
            await asyncio.to_thread(_ensure_kb)

        if name == "spawn_engineer":
            engineer_type = arguments["engineer_type"]
            task_spec = arguments["task_spec"]
            result = await spawn_engineer(engineer_type, task_spec)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "spawn_expert":
            expert_type = arguments["expert_type"]
            task = arguments["task"]
            phase = arguments.get("phase", "build")
            result = await spawn_expert(expert_type, task, phase)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "hybrid_search":
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
            operator = arguments.get("operator")
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
                        "hint": "Use td_assistant or query_graph(command='family') to look up valid types.",
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

        elif name == "td_compact_expertise":
            if not HAS_COMPACTION:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Compaction utilities unavailable",
                    "details": COMPACTION_IMPORT_ERROR
                }, indent=2))]

            try:
                refresh_yaml_flag = bool(arguments.get("refresh_yaml", True))
                events_path_arg = arguments.get("events_path")
                state_path_arg = arguments.get("state_path")

                events_path = Path(events_path_arg) if events_path_arg else None
                state_path = Path(state_path_arg) if state_path_arg else None

                success, msg = compact_events_to_state(events_path=events_path, state_path=state_path)
                result = {
                    "success": success,
                    "compaction": msg
                }

                if refresh_yaml_flag:
                    refresh_success, refresh_msg = refresh_legacy_yaml(state_path=state_path)
                    result["refresh_success"] = refresh_success
                    result["refresh"] = refresh_msg

                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except Exception as e:
                import traceback
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": str(e),
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
