"""Network Summarizer - Analyze expanded .tox.dir and generate semantic summaries.

This module implements the summary_generator expert's functionality for
analyzing TouchDesigner networks and producing LLM-friendly summaries.
"""

import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


def summarize_network(tox_dir: Path) -> Dict[str, Any]:
    """
    Analyze a TOX directory and return a semantic summary.

    Args:
        tox_dir: Path to expanded .tox.dir directory

    Returns:
        dict with: inputs, outputs, parameters, network_flow, key_operators,
                   operator_count, connection_count
    """
    tox_dir = Path(tox_dir)
    if not tox_dir.exists():
        raise FileNotFoundError(f"TOX directory not found: {tox_dir}")

    # Parse all operators
    operators = {}
    connections = []

    for n_file in tox_dir.rglob("*.n"):
        op_data = parse_n_file(n_file)
        if op_data:
            rel_path = n_file.relative_to(tox_dir).as_posix()
            op_name = n_file.stem
            operators[rel_path] = {
                'name': op_name,
                'path': rel_path,
                **op_data
            }
            # Extract connections from inputs
            for conn in op_data.get('inputs', []):
                connections.append({
                    'from': conn['source'],
                    'to': op_name,
                    'to_input': conn['index']
                })

    # Find input/output operators
    inputs = find_io_operators(operators, 'in')
    outputs = find_io_operators(operators, 'out')

    # Parse custom parameters from .cparm files
    parameters = {}
    for cparm_file in tox_dir.rglob("*.cparm"):
        params = parse_cparm_file(cparm_file)
        if params:
            op_name = cparm_file.stem
            parameters[op_name] = params

    # Parse .network files for COMP routing
    network_routing = {}
    for network_file in tox_dir.rglob("*.network"):
        routing = parse_network_file(network_file)
        if routing:
            op_name = network_file.stem
            network_routing[op_name] = routing

    # Generate data flow summary
    flow_summary = trace_data_flow(operators, connections)

    # Find key operators (non-trivial types)
    key_operators = find_key_operators(operators)

    return {
        'inputs': inputs,
        'outputs': outputs,
        'parameters': parameters,
        'network_routing': network_routing,
        'network_flow': flow_summary,
        'key_operators': key_operators,
        'operator_count': len(operators),
        'connection_count': len(connections),
        'operators': operators,
        'connections': connections
    }


def parse_n_file(n_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a .n file and extract operator info.

    Returns dict with: type, family, tile, flags, inputs, exports, dict, color
    """
    try:
        content = n_path.read_text(encoding='utf-8')
    except Exception:
        return None

    lines = content.strip().split('\n')
    if not lines:
        return None

    result = {
        'type': None,
        'family': None,
        'tile': None,
        'flags': {},
        'inputs': [],
        'exports': [],
        'dict': None,
        'color': None
    }

    # Line 1: FAMILY:type
    type_line = lines[0].strip()
    if ':' in type_line:
        family, op_type = type_line.split(':', 1)
        result['family'] = family.upper()
        result['type'] = op_type
    else:
        result['type'] = type_line

    i = 1
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line or line == 'end':
            continue

        if line.startswith('tile '):
            parts = line.split()[1:]
            if len(parts) >= 4:
                result['tile'] = [int(x) for x in parts[:4]]

        elif line.startswith('flags ='):
            flags_str = line.replace('flags =', '').strip()
            parts = flags_str.split()
            for j in range(0, len(parts) - 1, 2):
                result['flags'][parts[j]] = parts[j + 1]

        elif line == 'inputs' or line == 'inputs:':
            # Parse inputs block
            while i < len(lines) and lines[i].strip() != '{':
                i += 1
            i += 1  # Skip {

            while i < len(lines):
                inp_line = lines[i].strip()
                i += 1
                if inp_line == '}':
                    break
                if inp_line and not inp_line.startswith('#'):
                    parts = inp_line.split(None, 1)
                    if len(parts) >= 2:
                        result['inputs'].append({
                            'index': int(parts[0]),
                            'source': parts[1].strip()
                        })

        elif line == 'exports' or line == 'exports:':
            # Parse exports block
            while i < len(lines) and lines[i].strip() != '{':
                i += 1
            i += 1  # Skip {

            while i < len(lines):
                exp_line = lines[i].strip()
                i += 1
                if exp_line == '}':
                    break
                if exp_line and not exp_line.startswith('#'):
                    result['exports'].append(exp_line)

        elif line.startswith('dict '):
            result['dict'] = line[5:].strip()

        elif line.startswith('color '):
            parts = line[6:].strip().split()
            if parts:
                result['color'] = [float(c) for c in parts]

    return result


def parse_network_file(network_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a .network file to extract COMP input/output routing.

    Format:
        1
        compinputs
        {
        0   external_source
            internal_target
            TYPE
        }
        end
    """
    try:
        content = network_path.read_text(encoding='utf-8')
    except Exception:
        return None

    lines = content.strip().split('\n')
    result = {
        'compinputs': [],
        'compoutputs': []
    }

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if line == 'compinputs':
            # Skip to {
            while i < len(lines) and lines[i].strip() != '{':
                i += 1
            i += 1

            # Parse input mappings
            current_input = {}
            while i < len(lines):
                inp_line = lines[i].strip()
                i += 1
                if inp_line == '}':
                    if current_input:
                        result['compinputs'].append(current_input)
                    break
                if inp_line == 'end':
                    break

                # Format: index \t source \n \t target \n \t TYPE
                parts = inp_line.split()
                if parts and parts[0].isdigit():
                    if current_input:
                        result['compinputs'].append(current_input)
                    current_input = {
                        'index': int(parts[0]),
                        'source': parts[1] if len(parts) > 1 else None
                    }
                elif current_input and not current_input.get('target'):
                    current_input['target'] = inp_line
                elif current_input and not current_input.get('type'):
                    current_input['type'] = inp_line

        elif line == 'compoutputs':
            # Similar parsing for outputs
            while i < len(lines) and lines[i].strip() != '{':
                i += 1
            i += 1

            while i < len(lines):
                out_line = lines[i].strip()
                i += 1
                if out_line == '}' or out_line == 'end':
                    break
                # Parse output mappings...

    return result if result['compinputs'] or result['compoutputs'] else None


def parse_cparm_file(cparm_path: Path) -> Optional[List[Dict[str, Any]]]:
    """
    Parse a .cparm file to extract custom parameter definitions.

    Returns list of parameter definitions with name, type, default, etc.
    """
    try:
        content = cparm_path.read_text(encoding='utf-8')
    except Exception:
        return None

    params = []
    lines = content.strip().split('\n')

    current_page = None
    current_param = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Page definition
        if line.startswith('page '):
            current_page = line[5:].strip()
            continue

        # Parameter line format varies - basic parsing
        if line.startswith('float ') or line.startswith('int ') or line.startswith('str '):
            parts = line.split(None, 2)
            if len(parts) >= 2:
                params.append({
                    'type': parts[0],
                    'name': parts[1],
                    'page': current_page,
                    'raw': line
                })
        elif line.startswith('xy ') or line.startswith('xyz ') or line.startswith('rgb '):
            parts = line.split(None, 2)
            if len(parts) >= 2:
                params.append({
                    'type': parts[0],
                    'name': parts[1],
                    'page': current_page,
                    'raw': line
                })

    return params if params else None


def find_io_operators(operators: Dict, prefix: str) -> List[Dict[str, Any]]:
    """Find input or output operators by name prefix."""
    io_ops = []
    for path, op in operators.items():
        name = op.get('name', '')
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            io_ops.append({
                'name': name,
                'type': f"{op.get('family', '')}:{op.get('type', '')}",
                'path': path
            })
    return sorted(io_ops, key=lambda x: x['name'])


def find_key_operators(operators: Dict) -> List[Dict[str, Any]]:
    """
    Find key operators - those that do significant processing.
    Excludes: null, in, out, constant, select, rename, merge
    """
    trivial_types = {'null', 'in', 'out', 'constant', 'select', 'rename',
                     'merge', 'switch', 'math', 'logic', 'extend'}

    key_ops = []
    for path, op in operators.items():
        op_type = op.get('type', '').lower()
        if op_type not in trivial_types:
            key_ops.append({
                'name': op.get('name'),
                'type': f"{op.get('family', '')}:{op.get('type', '')}",
                'path': path
            })

    return key_ops[:20]  # Limit to top 20


def trace_data_flow(operators: Dict, connections: List) -> str:
    """
    Trace the main data flow path and return a human-readable summary.
    """
    if not connections:
        return "No connections found"

    # Build connection graph
    outgoing = {}  # source -> [targets]
    incoming = {}  # target -> [sources]

    for conn in connections:
        src = conn.get('from', '')
        tgt = conn.get('to', '')
        if src and tgt:
            outgoing.setdefault(src, []).append(tgt)
            incoming.setdefault(tgt, []).append(src)

    # Find roots (no incoming) and leaves (no outgoing)
    all_nodes = set(outgoing.keys()) | set(incoming.keys())
    roots = [n for n in all_nodes if n not in incoming]
    leaves = [n for n in all_nodes if n not in outgoing]

    # Build flow description
    flow_parts = []

    if roots:
        flow_parts.append(f"Input: {', '.join(roots[:3])}")

    # Find main chain
    if roots:
        chain = trace_chain(roots[0], outgoing, max_depth=10)
        if len(chain) > 1:
            flow_parts.append(f"Chain: {' → '.join(chain)}")

    if leaves:
        flow_parts.append(f"Output: {', '.join(leaves[:3])}")

    return " | ".join(flow_parts) if flow_parts else "Complex network topology"


def trace_chain(start: str, outgoing: Dict, max_depth: int = 10) -> List[str]:
    """Trace a single chain from start node."""
    chain = [start]
    current = start

    for _ in range(max_depth):
        targets = outgoing.get(current, [])
        if not targets:
            break
        current = targets[0]  # Follow first connection
        chain.append(current)

    return chain


def generate_semantic_summary(tox_dir: Path) -> str:
    """
    Generate a complete semantic summary for embedding/search.
    """
    summary_data = summarize_network(tox_dir)

    lines = []
    lines.append(f"## Network Summary")
    lines.append(f"Operators: {summary_data['operator_count']}")
    lines.append(f"Connections: {summary_data['connection_count']}")
    lines.append("")

    if summary_data['inputs']:
        lines.append("### Inputs")
        for inp in summary_data['inputs']:
            lines.append(f"- {inp['name']} ({inp['type']})")
        lines.append("")

    if summary_data['outputs']:
        lines.append("### Outputs")
        for out in summary_data['outputs']:
            lines.append(f"- {out['name']} ({out['type']})")
        lines.append("")

    if summary_data['network_flow']:
        lines.append("### Data Flow")
        lines.append(summary_data['network_flow'])
        lines.append("")

    if summary_data['key_operators']:
        lines.append("### Key Operators")
        for op in summary_data['key_operators'][:10]:
            lines.append(f"- {op['name']} ({op['type']})")
        lines.append("")

    if summary_data['parameters']:
        lines.append("### Custom Parameters")
        for op_name, params in list(summary_data['parameters'].items())[:5]:
            lines.append(f"**{op_name}**:")
            for p in params[:5]:
                lines.append(f"  - {p['name']} ({p['type']})")
        lines.append("")

    return "\n".join(lines)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        tox_path = Path(sys.argv[1])
        if tox_path.exists():
            print(generate_semantic_summary(tox_path))
        else:
            print(f"Not found: {tox_path}")
    else:
        print("Usage: python network_summarizer.py <path_to_tox.dir>")
