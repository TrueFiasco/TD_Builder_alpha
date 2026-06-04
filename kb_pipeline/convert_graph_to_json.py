#!/usr/bin/env python3
"""
Convert NetworkX graph from pickle to JSON format for Python 3.14 compatibility.

Workaround for networkx 3.6 dataclass compatibility issue with Python 3.14.
"""

import sys
import json
from pathlib import Path

# Temporarily patch the issue before importing networkx
import dataclasses

# Monkey-patch wrapper_descriptor to have __annotate__ attribute
if not hasattr(type(object.__init__), '__annotate__'):
    original_init = dataclasses._process_class

    def patched_process_class(cls, *args, **kwargs):
        # Add __annotate__ to wrapper_descriptor if missing
        if hasattr(cls.__init__, '__func__'):
            if not hasattr(cls.__init__, '__annotate__'):
                cls.__init__.__annotate__ = lambda: {}
        return original_init(cls, *args, **kwargs)

    dataclasses._process_class = patched_process_class

# Now safe to import networkx
import networkx as nx

KB_ROOT = Path(__file__).parent
GRAPH_PATH = KB_ROOT / "graph" / "td_knowledge_graph_merged.gpickle"
JSON_GRAPH_PATH = KB_ROOT / "graph" / "td_knowledge_graph.json"


def convert_graph_to_json():
    """Convert pickle graph to JSON format."""
    print("=" * 80)
    print("GRAPH FORMAT CONVERSION")
    print("=" * 80)

    print(f"\nLoading graph from: {GRAPH_PATH}")

    try:
        # Load with patch
        graph = nx.read_gpickle(GRAPH_PATH)
        print(f"  Loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    except Exception as e:
        print(f"  Error loading graph: {e}")
        return False

    # Convert to JSON-serializable format
    print("\nConverting to JSON format...")

    graph_data = {
        'directed': graph.is_directed(),
        'multigraph': graph.is_multigraph(),
        'nodes': [],
        'edges': []
    }

    # Serialize nodes
    for node, data in graph.nodes(data=True):
        node_data = {'id': node}
        # Convert any non-serializable values
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                node_data[key] = value
            elif isinstance(value, (list, dict)):
                node_data[key] = value
            else:
                node_data[key] = str(value)
        graph_data['nodes'].append(node_data)

    # Serialize edges
    for source, target, data in graph.edges(data=True):
        edge_data = {
            'source': source,
            'target': target
        }
        # Convert any non-serializable values
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                edge_data[key] = value
            elif isinstance(value, (list, dict)):
                edge_data[key] = value
            else:
                edge_data[key] = str(value)
        graph_data['edges'].append(edge_data)

    # Save JSON
    print(f"Saving JSON graph to: {JSON_GRAPH_PATH}")
    with open(JSON_GRAPH_PATH, 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2)

    file_size = JSON_GRAPH_PATH.stat().st_size / (1024 * 1024)
    print(f"  Saved: {file_size:.2f} MB")

    print("\n[OK] Graph conversion complete!")
    print(f"  Nodes: {len(graph_data['nodes'])}")
    print(f"  Edges: {len(graph_data['edges'])}")

    return True


def load_json_graph(json_path):
    """Load graph from JSON format."""
    with open(json_path, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)

    # Reconstruct graph
    if graph_data['directed']:
        if graph_data['multigraph']:
            graph = nx.MultiDiGraph()
        else:
            graph = nx.DiGraph()
    else:
        if graph_data['multigraph']:
            graph = nx.MultiGraph()
        else:
            graph = nx.Graph()

    # Add nodes
    for node_data in graph_data['nodes']:
        node_id = node_data.pop('id')
        graph.add_node(node_id, **node_data)

    # Add edges
    for edge_data in graph_data['edges']:
        source = edge_data.pop('source')
        target = edge_data.pop('target')
        graph.add_edge(source, target, **edge_data)

    return graph


if __name__ == '__main__':
    success = convert_graph_to_json()

    if success:
        # Test loading
        print("\nTesting JSON graph loading...")
        graph = load_json_graph(JSON_GRAPH_PATH)
        print(f"  Loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        print("[OK] JSON graph verified!")
    else:
        sys.exit(1)
