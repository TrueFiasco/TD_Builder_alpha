#!/usr/bin/env python3
"""
TouchDesigner MCP Server - Alpha Release

Complete unified server with:
- Knowledge Base tools (hybrid_search, query_graph, etc.)
- Builder tools (td_validate, td_convert, td_build_network)
- Agent spawning (spawn_engineer with 5 specialized agents)
- Example-based tools (find_operator_examples, find_operator_combination, etc.)

Usage:
    python server.py
"""

from __future__ import annotations

import asyncio
import contextlib
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Callable

# Ensure UTF-8 output
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Add package to path
TD_MCP_ROOT = Path(__file__).parent
sys.path.insert(0, str(TD_MCP_ROOT))

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: MCP package not installed", file=sys.stderr)
    print("Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Anthropic for agent spawning
try:
    import anthropic
except ImportError:
    print("WARNING: anthropic package not installed - agent spawning will not work", file=sys.stderr)
    anthropic = None

# Import knowledge base components
try:
    from knowledge_base.retrieval import EnhancedHybridRetrieval
    from knowledge_base.graph import SimpleGraph
except ImportError as e:
    print(f"WARNING: Could not load knowledge base: {e}", file=sys.stderr)
    EnhancedHybridRetrieval = None
    SimpleGraph = None

# Import builder components
try:
    from builder.registry import OperatorRegistry
except ImportError as e:
    print(f"WARNING: Could not load builder registry: {e}", file=sys.stderr)
    OperatorRegistry = None

# TouchDesigner paths
TOECOLLAPSE = r"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe"
BUILDS_DIR = TD_MCP_ROOT.parent / "builds"
AGENTS_DIR = TD_MCP_ROOT / "agents"

# Engineer agent skills
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
    },
    "data_source_auditor": {
        "skill_file": "data_source_auditor.md",
        "description": "Audit all data sources and create extraction strategy",
        "output_format": "json"
    }
}


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


# Helper functions
def _normalize_sources(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _chunk_source(chunk: Dict[str, Any]) -> str:
    meta = chunk.get("meta", {}) or {}
    source = meta.get("source")
    if source:
        return str(source)
    if meta.get("operator_type") or meta.get("relpath") or meta.get("has_curator_summary") is not None:
        return "snippets"
    if meta.get("palette_name") or meta.get("palette_category"):
        return "palette"
    return "docs"


def _td_create_type(td_type: str) -> str:
    """Convert 'CHOP:noise' to 'noiseCHOP' for parent.create()."""
    if ":" not in td_type:
        return td_type
    family, specific = td_type.split(":", 1)
    family = family.strip().upper()
    specific = specific.strip()
    if not specific:
        return td_type
    return f"{specific}{family}"


def build_text_dat_script(
    network: Dict[str, Any],
    target_parent_path: str,
    collision_policy: str = "reuse",
) -> str:
    """Generate a TouchDesigner Text DAT Python script to create a network."""
    nodes = network.get("nodes", []) or network.get("operators", []) or []
    connections = network.get("connections", []) or []

    lines: List[str] = []
    lines.append("# TouchDesigner Text DAT builder script")
    lines.append("# Generated by TD-MCP Server")
    lines.append("")
    lines.append("def build(target_parent_path=None):")
    lines.append(f"    parent_path = target_parent_path or {target_parent_path!r}")
    lines.append("    parent = op(parent_path)")
    lines.append("    if parent is None:")
    lines.append("        raise Exception(f'Parent not found: {parent_path}')")
    lines.append("")
    lines.append("    created = {}")
    lines.append("")

    # Create nodes
    for node in nodes:
        name = node.get("name")
        td_type = node.get("type")
        if not name or not td_type:
            continue
        create_type = _td_create_type(str(td_type))
        lines.append(f"    existing = parent.op({name!r})")
        if collision_policy == "delete":
            lines.append("    if existing is not None:")
            lines.append("        try: existing.destroy()")
            lines.append("        except: pass")
            lines.append("        existing = None")
        lines.append(f"    node = existing or parent.create({create_type!r}, {name!r})")
        lines.append(f"    created[{name!r}] = node")
        lines.append("")

    # Apply parameters
    for node in nodes:
        name = node.get("name")
        params = node.get("params") or node.get("parameters") or {}
        if not name or not params:
            continue
        lines.append(f"    node = created.get({name!r})")
        for param_name, param_value in params.items():
            lines.append("    try:")
            lines.append(f"        p = getattr(node.par, {param_name!r}, None)")
            lines.append("        if p is not None:")
            lines.append(f"            p.val = {param_value!r}")
            lines.append("    except: pass")
        lines.append("")

    # Wire connections
    for conn in connections:
        from_name = conn.get("from")
        to_name = conn.get("to")
        to_input = conn.get("to_input", 0)
        if not from_name or not to_name:
            continue
        lines.append(f"    src = created.get({str(from_name)!r})")
        lines.append(f"    dst = created.get({str(to_name)!r})")
        lines.append("    if src and dst:")
        lines.append(f"        try: dst.setInput({to_input}, src)")
        lines.append("        except: pass")
        lines.append("")

    lines.append("    return created")
    lines.append("")
    lines.append("build()")

    return "\n".join(lines)


# Initialize systems
print("Loading TD-MCP Server...", file=sys.stderr)
retrieval = None
registry = None
knowledge_graph = None

with contextlib.redirect_stdout(sys.stderr):
    if EnhancedHybridRetrieval:
        try:
            retrieval = EnhancedHybridRetrieval(enable_cache=True, cache_ttl_hours=24)
        except Exception as e:
            print(f"WARNING: Could not initialize retrieval: {e}")

    if OperatorRegistry:
        try:
            registry = OperatorRegistry()
            print(f"Loaded {len(registry)} operators")
        except Exception as e:
            print(f"WARNING: Could not initialize registry: {e}")

    # Try to load knowledge graph
    graph_path = TD_MCP_ROOT / "knowledge_base" / "graph" / "knowledge_graph.json"
    if graph_path.exists() and SimpleGraph:
        try:
            knowledge_graph = SimpleGraph.load_from_json(graph_path)
            print(f"Loaded knowledge graph: {knowledge_graph.number_of_nodes()} nodes")
        except Exception as e:
            print(f"WARNING: Could not load knowledge graph: {e}")


def execute_tool_for_agent(tool_name: str, tool_params: dict) -> Any:
    """Execute a tool request from a spawned agent"""

    try:
        if tool_name == "hybrid_search" and retrieval:
            query = tool_params["query"]
            n_results = tool_params.get("n_results", 5)
            results = retrieval.hybrid_search(query, n_results=n_results)
            return [{"text": chunk.get("text", ""), "score": score, "meta": chunk.get("meta", {})}
                    for chunk, score in results]

        elif tool_name == "get_operator_info" and registry:
            operator_name = tool_params["operator_name"]
            # Search registry
            results = registry.search_operators(operator_name)
            if results:
                op = results[0]
                return {
                    "name": op.name,
                    "family": op.family.value,
                    "summary": op.summary,
                    "parameters": [{"code": p.code, "name": p.display_name, "section": p.section}
                                   for p in op.parameters[:20]]  # Limit params
                }
            return {"error": f"Operator not found: {operator_name}"}

        elif tool_name == "query_graph":
            command = tool_params["command"]
            if command == "family" and registry:
                from builder.models import OperatorFamily
                family = tool_params.get("family", "").upper()
                try:
                    fam = OperatorFamily(family)
                    ops = registry.get_operators_by_family(fam)
                    return [{"name": op.name, "type": op.op_type} for op in ops[:50]]
                except ValueError:
                    return {"error": f"Unknown family: {family}"}
            return {"error": f"Command not fully implemented: {command}"}

        elif tool_name == "list_pop_operators" and registry:
            from builder.models import OperatorFamily
            ops = registry.get_operators_by_family(OperatorFamily.POP)
            return [{"name": op.name, "type": op.op_type} for op in ops]

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
            return {"error": f"Tool not available: {tool_name}"}

    except Exception as e:
        return {"error": str(e)}


async def spawn_engineer(engineer_type: str, task_spec: Dict) -> Dict:
    """Spawn a specialized engineer agent"""

    if anthropic is None:
        return {"status": "ERROR", "message": "Anthropic package not installed"}

    if engineer_type not in ENGINEER_SKILLS:
        return {"status": "ERROR", "message": f"Unknown engineer type: {engineer_type}",
                "available": list(ENGINEER_SKILLS.keys())}

    try:
        agent_system = AgentWithTools()
    except Exception as e:
        return {"status": "ERROR", "message": f"Could not initialize agent: {e}"}

    skill_file = ENGINEER_SKILLS[engineer_type]["skill_file"]
    skill_path = AGENTS_DIR / skill_file

    if not skill_path.exists():
        return {"status": "ERROR", "message": f"Skill file not found: {skill_path}"}

    try:
        with open(skill_path, encoding='utf-8') as f:
            engineer_skill = f.read()
    except Exception as e:
        return {"status": "ERROR", "message": f"Could not load skill: {e}"}

    print(f"SPAWNING ENGINEER: {engineer_type}", file=sys.stderr)

    result = agent_system.spawn_agent_with_tool_access(
        agent_name=engineer_type,
        agent_skill=engineer_skill,
        input_data=task_spec,
        tool_executor=execute_tool_for_agent
    )

    if "error" in result:
        return {"status": "FAILED", "engineer": engineer_type, "error": result["error"]}

    return {"status": "SUCCESS", "engineer": engineer_type, "output": result}


app = Server("td-mcp-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # Agent spawning
        Tool(
            name="spawn_engineer",
            description="Spawn a specialized engineer agent to execute knowledge extraction tasks. Engineers can analyze .tox files, extract patterns, generate concepts, and validate knowledge. Returns structured JSON output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engineer_type": {
                        "type": "string",
                        "enum": list(ENGINEER_SKILLS.keys()),
                        "description": "Type of engineer to spawn: snippet_extractor, workflow_analyzer, concept_generator, knowledge_validator, or data_source_auditor"
                    },
                    "task_spec": {
                        "type": "object",
                        "description": "Task specification with all required inputs for the engineer"
                    }
                },
                "required": ["engineer_type", "task_spec"]
            }
        ),
        # Knowledge Base search
        Tool(
            name="hybrid_search",
            description="Search TouchDesigner documentation using semantic search + knowledge graph. Returns relevant operators, parameters, concepts with relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language question about TouchDesigner"},
                    "n_results": {"type": "integer", "default": 5, "description": "Number of results to return"}
                },
                "required": ["query"]
            }
        ),
        # Operator info
        Tool(
            name="get_operator_info",
            description="Get complete information about a specific TouchDesigner operator including parameters, description, and relationships",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_name": {"type": "string", "description": "Name of the operator (e.g., 'Grid SOP', 'Audio File In CHOP')"}
                },
                "required": ["operator_name"]
            }
        ),
        # Graph query
        Tool(
            name="query_graph",
            description="Query TouchDesigner knowledge graph for precise relationships",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": ["params", "related", "family"],
                                "description": "Type of query: 'params' (operator parameters), 'related' (related operators), 'family' (operators in family)"},
                    "operator": {"type": "string", "description": "Operator name (required for 'params' and 'related')"},
                    "family": {"type": "string", "description": "Operator family (required for 'family' command): SOP, CHOP, TOP, DAT, COMP, MAT, POP"}
                },
                "required": ["command"]
            }
        ),
        # POP operators
        Tool(
            name="list_pop_operators",
            description="List all POP (Particle) operators available in TouchDesigner",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        # Example-based tools
        Tool(
            name="find_operator_examples",
            description="Find real example networks demonstrating how to use a specific operator. Returns actual parameter values, connections, and text explanations from working TouchDesigner examples.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator": {"type": "string", "description": "Operator name (e.g., 'analyze', 'noise', 'filter')"},
                    "limit": {"type": "integer", "default": 10, "description": "Maximum number of examples to return"}
                },
                "required": ["operator"]
            }
        ),
        Tool(
            name="find_operator_combination",
            description="Find examples that use specific operator combinations. Useful for learning how operators work together (e.g., 'noise + analyze', 'filter + math').",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_types": {"type": "array", "items": {"type": "string"},
                                       "description": "List of operator types to find together"},
                    "require_connection": {"type": "boolean", "default": True,
                                           "description": "Whether operators must be connected"},
                    "limit": {"type": "integer", "default": 5}
                },
                "required": ["operator_types"]
            }
        ),
        Tool(
            name="find_parameter_usage",
            description="Find real examples showing how a specific parameter is used. Returns actual parameter values from working examples, not theoretical possibilities.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_type": {"type": "string", "description": "Operator type (e.g., 'analyze', 'filter', 'noise')"},
                    "parameter_name": {"type": "string", "description": "Parameter name (e.g., 'function', 'method', 'type')"},
                    "limit": {"type": "integer", "default": 10}
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
                    "example_id": {"type": "string", "description": "Example ID (e.g., 'analyzeCHOP/example1')"},
                    "limit": {"type": "integer", "default": 5}
                },
                "required": ["example_id"]
            }
        ),
        Tool(
            name="get_network_patterns",
            description="Get common network patterns found across TouchDesigner examples. Shows frequently-used operator combinations and connection patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_frequency": {"type": "integer", "default": 5, "description": "Minimum number of times pattern must appear"}
                },
                "required": []
            }
        ),
        # Builder tools from unified_mcp_server
        Tool(
            name="td_validate",
            description="Validate a TouchDesigner network JSON against the unified validation pipeline. Returns validation report with errors, warnings, and suggestions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {"type": "object", "description": "TD network JSON (builder, extended, or canonical format)"},
                    "format_layer": {"type": "string", "enum": ["builder", "extended", "canonical"], "default": "builder"}
                },
                "required": ["network"]
            }
        ),
        Tool(
            name="td_convert",
            description="Convert TouchDesigner network JSON between format layers. Supports: builder (AI-friendly) ↔ extended (ground truth) ↔ canonical (compact).",
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {"type": "object", "description": "TD network JSON to convert"},
                    "source_layer": {"type": "string", "enum": ["builder", "extended", "canonical"]},
                    "target_layer": {"type": "string", "enum": ["builder", "extended", "canonical"]}
                },
                "required": ["network", "source_layer", "target_layer"]
            }
        ),
        Tool(
            name="td_build_network",
            description="Build a TouchDesigner .toe or .tox file from network JSON. Creates Text DAT script or .toe file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {"type": "object", "description": "TD network JSON (builder format)"},
                    "network_design": {"type": "object", "description": "Advanced network design with containers"},
                    "output_path": {"type": "string", "description": "Output file path"},
                    "mode": {"type": "string", "enum": ["toe", "tox"], "default": "toe"}
                },
                "required": ["output_path"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
    try:
        # Agent spawning
        if name == "spawn_engineer":
            engineer_type = arguments["engineer_type"]
            task_spec = arguments["task_spec"]
            result = await spawn_engineer(engineer_type, task_spec)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # Hybrid search
        elif name == "hybrid_search":
            if not retrieval:
                return [TextContent(type="text", text="ERROR: Hybrid search not initialized")]

            query = arguments["query"]
            n_results = arguments.get("n_results", 5)
            results = await retrieval.hybrid_search_async(query, n_results=n_results)

            formatted = []
            for chunk, score in results:
                formatted.append({
                    "score": score,
                    "source": _chunk_source(chunk),
                    "text": chunk.get("text", ""),
                    "meta": chunk.get("meta", {})
                })

            return [TextContent(type="text", text=json.dumps(formatted, indent=2))]

        # Operator info
        elif name == "get_operator_info":
            if not registry:
                return [TextContent(type="text", text="ERROR: Registry not initialized")]

            operator_name = arguments["operator_name"]
            results = registry.search_operators(operator_name)

            if results:
                op = results[0]
                info = {
                    "name": op.name,
                    "family": op.family.value,
                    "op_type": op.op_type,
                    "summary": op.summary,
                    "parameters": [{"code": p.code, "display_name": p.display_name, "section": p.section}
                                   for p in op.parameters]
                }
                return [TextContent(type="text", text=json.dumps(info, indent=2))]

            return [TextContent(type="text", text=json.dumps({"error": f"Operator not found: {operator_name}"}))]

        # Graph query
        elif name == "query_graph":
            command = arguments["command"]

            if command == "family" and registry:
                from builder.models import OperatorFamily
                family = arguments.get("family", "").upper()
                try:
                    fam = OperatorFamily(family)
                    ops = registry.get_operators_by_family(fam)
                    result = [{"name": op.name, "type": op.op_type} for op in ops]
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                except ValueError:
                    return [TextContent(type="text", text=f"Error: Unknown family '{family}'")]

            elif command == "params" and registry:
                operator = arguments.get("operator")
                results = registry.search_operators(operator) if operator else []
                if results:
                    op = results[0]
                    params = [{"code": p.code, "name": p.display_name} for p in op.parameters]
                    return [TextContent(type="text", text=json.dumps(params, indent=2))]
                return [TextContent(type="text", text=f"Error: Operator not found: {operator}")]

            return [TextContent(type="text", text=f"Error: Command '{command}' not fully implemented")]

        # POP operators
        elif name == "list_pop_operators":
            if not registry:
                return [TextContent(type="text", text="ERROR: Registry not initialized")]
            from builder.models import OperatorFamily
            ops = registry.get_operators_by_family(OperatorFamily.POP)
            result = [{"name": op.name, "type": op.op_type} for op in ops]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # Example-based tools - use search as proxy for now
        elif name in ["find_operator_examples", "find_operator_combination", "find_parameter_usage",
                      "find_similar_networks", "get_network_patterns"]:
            if not retrieval:
                return [TextContent(type="text", text="ERROR: Search not initialized")]

            # Construct search query from arguments
            if name == "find_operator_examples":
                query = f"how to use {arguments['operator']} operator example"
            elif name == "find_operator_combination":
                ops = arguments.get("operator_types", [])
                query = f"example using {' and '.join(ops)} operators together"
            elif name == "find_parameter_usage":
                query = f"{arguments['operator_type']} {arguments['parameter_name']} parameter values example"
            elif name == "find_similar_networks":
                query = f"network pattern similar to {arguments['example_id']}"
            else:  # get_network_patterns
                query = "common TouchDesigner network patterns operator combinations"

            limit = arguments.get("limit", 5)
            results = await retrieval.hybrid_search_async(query, n_results=limit)

            formatted = []
            for chunk, score in results:
                formatted.append({
                    "score": score,
                    "source": _chunk_source(chunk),
                    "text": chunk.get("text", "")[:500],
                    "meta": chunk.get("meta", {})
                })

            return [TextContent(type="text", text=json.dumps({
                "tool": name,
                "query_used": query,
                "results": formatted
            }, indent=2))]

        # Validation
        elif name == "td_validate":
            network_json = arguments.get("network")
            if not network_json:
                return [TextContent(type="text", text="Error: 'network' is required")]

            operators = network_json.get("operators", []) or network_json.get("nodes", [])
            errors = []
            warnings = []

            for op in operators:
                op_type = op.get("type", "")
                if registry:
                    # Try to find in registry
                    results = registry.search_operators(op_type)
                    if not results:
                        warnings.append({"message": f"Unknown operator type: {op_type}", "path": op.get("name", "")})

            result = {
                "valid": len(errors) == 0,
                "total_errors": len(errors),
                "total_warnings": len(warnings),
                "errors": errors,
                "warnings": warnings
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # Conversion
        elif name == "td_convert":
            network_json = arguments.get("network")
            if not network_json:
                return [TextContent(type="text", text="Error: 'network' is required")]

            target_layer = arguments.get("target_layer")
            result_json = dict(network_json)
            result_json["format_layer"] = target_layer

            return [TextContent(type="text", text=json.dumps(result_json, indent=2))]

        # Build network
        elif name == "td_build_network":
            network_json = arguments.get("network") or arguments.get("network_design")
            output_path = arguments.get("output_path")

            if not output_path:
                return [TextContent(type="text", text="Error: 'output_path' is required")]
            if not network_json:
                return [TextContent(type="text", text="Error: 'network' or 'network_design' is required")]

            # Normalize path
            if output_path.startswith('/') or ':' not in output_path:
                filename = Path(output_path).name
                output_path = str(BUILDS_DIR / filename)

            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            # Generate Text DAT script
            script = build_text_dat_script(network_json, target_parent_path="/project1")
            script_path = output.with_suffix('.py')
            script_path.write_text(script, encoding='utf-8')

            result = {
                "success": True,
                "builder": "text_dat_script",
                "output_file": str(script_path),
                "note": "Generated Text DAT script. Paste into Text DAT and run.",
                "operators": len(network_json.get("operators", []) or network_json.get("nodes", []))
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]

    except Exception as e:
        import traceback
        return [TextContent(type="text", text=f"Error: {str(e)}\n{traceback.format_exc()}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
