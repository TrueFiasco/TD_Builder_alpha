#!/usr/bin/env python3
"""
Rebuild knowledge graph from td_graphrag.json into SimpleGraph format.

Bypasses NetworkX Python 3.14 compatibility issues.
"""

import json
from pathlib import Path
from simple_graph import SimpleGraph

KB_ROOT = Path(__file__).parent.parent
GRAPHRAG_JSON = KB_ROOT.parent / "td_graphrag.json"
OUTPUT_PATH = KB_ROOT / "graph" / "td_knowledge_graph_simple.json"


def rebuild_graph():
    """Build SimpleGraph from GraphRAG JSON data."""
    print("=" * 80)
    print("REBUILDING GRAPH FROM TD_GRAPHRAG.JSON")
    print("=" * 80)

    print(f"\nLoading GraphRAG data from: {GRAPHRAG_JSON}")

    with open(GRAPHRAG_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    metadata = data.get('metadata', {})
    chunks = data.get('chunks', [])

    print(f"  Chunk count: {metadata.get('chunk_count', len(chunks))}")
    print(f"  Node count: {metadata.get('node_count', 'N/A')}")
    print(f"  Edge count: {metadata.get('edge_count', 'N/A')}")

    # Build graph
    print("\nBuilding SimpleGraph...")
    graph = SimpleGraph()

    # Track operators and their relationships
    operators = {}  # operator_name -> node_id
    operator_parameters = {}  # operator_name -> [param_codes]
    operator_chunks = {}  # operator_name -> [chunk_ids]

    # First pass: collect operators and their metadata
    for chunk in chunks:
        chunk_type = chunk.get('type')
        metadata = chunk.get('metadata', {})
        operator_name = metadata.get('operator_name')

        if not operator_name:
            continue

        # Add operator node
        if operator_name not in operators:
            node_id = metadata.get('node_id', operator_name.lower().replace(' ', '_'))
            operators[operator_name] = node_id

            graph.add_node(
                node_id,
                type='operator',
                name=operator_name,
                family=metadata.get('family', 'Unknown')
            )

            operator_chunks[operator_name] = []
            operator_parameters[operator_name] = []

        # Track chunk association
        operator_chunks[operator_name].append(chunk['id'])

        # Track parameters
        if chunk_type == 'parameter':
            param_code = metadata.get('parameter_code')
            if param_code and param_code not in operator_parameters[operator_name]:
                operator_parameters[operator_name].append(param_code)

    print(f"  Found {len(operators)} operators")

    # Second pass: create parameter nodes and edges
    param_node_count = 0
    param_edge_count = 0

    for operator_name, params in operator_parameters.items():
        op_node_id = operators[operator_name]

        for param_code in params:
            # Create parameter node
            param_node_id = f"{op_node_id}:param:{param_code}"
            graph.add_node(
                param_node_id,
                type='parameter',
                code=param_code,
                operator=operator_name
            )
            param_node_count += 1

            # Link parameter to operator
            graph.add_edge(
                op_node_id,
                param_node_id,
                relationship='HAS_PARAMETER'
            )
            param_edge_count += 1

    print(f"  Created {param_node_count} parameter nodes")
    print(f"  Created {param_edge_count} parameter edges")

    # Third pass: create operator family relationships
    family_groups = {}
    for operator_name, node_id in operators.items():
        node_data = graph.get_node_data(node_id)
        family = node_data.get('family', 'Unknown')

        if family not in family_groups:
            family_groups[family] = []
        family_groups[family].append(node_id)

    # Link operators in same family
    family_edge_count = 0
    for family, op_nodes in family_groups.items():
        for i, node1 in enumerate(op_nodes):
            # Link to next 3 operators in family (for graph expansion)
            for node2 in op_nodes[i+1:i+4]:
                graph.add_edge(
                    node1,
                    node2,
                    relationship='SAME_FAMILY',
                    family=family
                )
                family_edge_count += 1

    print(f"  Created {family_edge_count} family relationship edges")

    # Save
    print(f"\nSaving SimpleGraph to: {OUTPUT_PATH}")
    graph.save_to_json(OUTPUT_PATH)

    file_size = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"  File size: {file_size:.2f} MB")

    print("\n[OK] Graph rebuild complete!")
    print(f"  Total nodes: {graph.number_of_nodes()}")
    print(f"  Total edges: {graph.number_of_edges()}")

    return graph


if __name__ == '__main__':
    graph = rebuild_graph()

    # Test queries
    print("\nTesting graph queries...")

    # Find an operator
    test_operators = ['Speed CHOP', 'Noise TOP', 'Analyze CHOP']
    for op_name in test_operators:
        node_id = op_name.lower().replace(' ', '_')
        if node_id in graph:
            neighbors = graph.neighbors(node_id)
            print(f"  {op_name}: {len(neighbors)} connections")

            # Show neighbor types
            param_count = sum(1 for n in neighbors if 'param:' in n)
            family_count = len(neighbors) - param_count
            print(f"    - {param_count} parameters")
            print(f"    - {family_count} related operators")
        else:
            print(f"  {op_name}: not found")

    print("\n[OK] Graph ready for hybrid retrieval!")
