#!/usr/bin/env python3
"""
Simple graph data structure for Python 3.14 compatibility.

Replaces NetworkX for basic graph queries without pickle dependencies.
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict


class SimpleGraph:
    """
    Lightweight graph implementation using adjacency lists.

    Optimized for the specific queries needed by hybrid retrieval:
    - Get neighbors of a node
    - Check if node exists
    - Get node/edge attributes
    """

    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, List[tuple]] = defaultdict(list)
        self._edge_data: Dict[tuple, Dict[str, Any]] = {}
        self._reverse_edges: Dict[str, List[tuple]] = defaultdict(list)

    def add_node(self, node_id: str, **attributes):
        """Add a node with optional attributes."""
        if node_id not in self._nodes:
            self._nodes[node_id] = {}
        self._nodes[node_id].update(attributes)

    def add_edge(self, source: str, target: str, **attributes):
        """Add an edge with optional attributes."""
        # Ensure nodes exist
        if source not in self._nodes:
            self.add_node(source)
        if target not in self._nodes:
            self.add_node(target)

        # Add edge
        self._edges[source].append(target)
        self._reverse_edges[target].append(source)

        # Store edge attributes
        edge_key = (source, target)
        if edge_key not in self._edge_data:
            self._edge_data[edge_key] = {}
        self._edge_data[edge_key].update(attributes)

    def has_node(self, node_id: str) -> bool:
        """Check if node exists."""
        return node_id in self._nodes

    def neighbors(self, node_id: str) -> List[str]:
        """Get all neighbors (outgoing edges)."""
        return self._edges.get(node_id, [])

    def predecessors(self, node_id: str) -> List[str]:
        """Get all predecessors (incoming edges)."""
        return self._reverse_edges.get(node_id, [])

    def get_node_data(self, node_id: str) -> Dict[str, Any]:
        """Get node attributes."""
        return self._nodes.get(node_id, {})

    def get_edge_data(self, source: str, target: str) -> Dict[str, Any]:
        """Get edge attributes."""
        return self._edge_data.get((source, target), {})

    def nodes(self) -> List[str]:
        """Get all node IDs."""
        return list(self._nodes.keys())

    def number_of_nodes(self) -> int:
        """Get number of nodes."""
        return len(self._nodes)

    def number_of_edges(self) -> int:
        """Get number of edges."""
        return sum(len(neighbors) for neighbors in self._edges.values())

    def get_neighbors_by_edge_type(self, node_id: str, edge_type: str) -> List[str]:
        """Get neighbors connected by specific edge type."""
        neighbors = []
        for target in self.neighbors(node_id):
            edge_data = self.get_edge_data(node_id, target)
            if edge_data.get('relationship') == edge_type:
                neighbors.append(target)
        return neighbors

    def save_to_json(self, filepath: Path):
        """Save graph to JSON file."""
        data = {
            'nodes': [
                {'id': node_id, **attributes}
                for node_id, attributes in self._nodes.items()
            ],
            'edges': [
                {'source': source, 'target': target, **self._edge_data.get((source, target), {})}
                for source, targets in self._edges.items()
                for target in targets
            ]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_json(cls, filepath: Path) -> 'SimpleGraph':
        """Load graph from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        graph = cls()

        # Add nodes
        for node_data in data['nodes']:
            node_id = node_data.pop('id')
            graph.add_node(node_id, **node_data)

        # Add edges
        for edge_data in data['edges']:
            source = edge_data.pop('source')
            target = edge_data.pop('target')
            graph.add_edge(source, target, **edge_data)

        return graph

    def __contains__(self, node_id: str) -> bool:
        """Support 'node_id in graph' syntax."""
        return self.has_node(node_id)


def build_simple_graph_from_enhanced_graph():
    """
    Build simple graph from the enhanced graph pickle.

    This is a one-time conversion utility. Uses pickle loading workaround.
    """
    import pickle

    KB_ROOT = Path(__file__).parent.parent
    ENHANCED_GRAPH_PATH = KB_ROOT / "graph" / "td_knowledge_graph_merged.gpickle"
    OUTPUT_PATH = KB_ROOT / "graph" / "td_knowledge_graph_simple.json"

    print("=" * 80)
    print("BUILDING SIMPLE GRAPH FROM ENHANCED GRAPH")
    print("=" * 80)

    print(f"\nLoading enhanced graph from: {ENHANCED_GRAPH_PATH}")

    # Try direct pickle load
    try:
        with open(ENHANCED_GRAPH_PATH, 'rb') as f:
            nx_graph = pickle.load(f)
        print(f"  Loaded pickle successfully")
    except Exception as e:
        print(f"  Error: {e}")
        return None

    print(f"  Nodes: {len(nx_graph.nodes())}")
    print(f"  Edges: {len(nx_graph.edges())}")

    # Convert to SimpleGraph
    print("\nConverting to SimpleGraph...")
    simple_graph = SimpleGraph()

    # Add nodes
    for node_id, data in nx_graph.nodes(data=True):
        simple_graph.add_node(node_id, **data)

    # Add edges
    for source, target, data in nx_graph.edges(data=True):
        simple_graph.add_edge(source, target, **data)

    print(f"  Converted: {simple_graph.number_of_nodes()} nodes, {simple_graph.number_of_edges()} edges")

    # Save
    print(f"\nSaving to: {OUTPUT_PATH}")
    simple_graph.save_to_json(OUTPUT_PATH)

    file_size = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"  Saved: {file_size:.2f} MB")

    print("\n[OK] Conversion complete!")

    return simple_graph


if __name__ == '__main__':
    # Build simple graph from enhanced graph
    graph = build_simple_graph_from_enhanced_graph()

    if graph:
        # Test loading
        print("\nTesting JSON loading...")
        KB_ROOT = Path(__file__).parent.parent
        json_path = KB_ROOT / "graph" / "td_knowledge_graph_simple.json"

        loaded_graph = SimpleGraph.load_from_json(json_path)
        print(f"  Loaded: {loaded_graph.number_of_nodes()} nodes, {loaded_graph.number_of_edges()} edges")

        # Test queries
        print("\nTesting queries...")
        test_node = loaded_graph.nodes()[0] if loaded_graph.nodes() else None
        if test_node:
            neighbors = loaded_graph.neighbors(test_node)
            print(f"  Node '{test_node}' has {len(neighbors)} neighbors")

        print("[OK] SimpleGraph verified!")
