#!/usr/bin/env python3
"""
Simple graph data structure for knowledge graph queries.

Lightweight implementation using adjacency lists.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
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
        self._edges: Dict[str, List[str]] = defaultdict(list)
        self._edge_data: Dict[tuple, Dict[str, Any]] = {}
        self._reverse_edges: Dict[str, List[str]] = defaultdict(list)

    def add_node(self, node_id: str, **attributes):
        """Add a node with optional attributes."""
        if node_id not in self._nodes:
            self._nodes[node_id] = {}
        self._nodes[node_id].update(attributes)

    def add_edge(self, source: str, target: str, **attributes):
        """Add an edge with optional attributes."""
        if source not in self._nodes:
            self.add_node(source)
        if target not in self._nodes:
            self.add_node(target)

        self._edges[source].append(target)
        self._reverse_edges[target].append(source)

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

        for node_data in data['nodes']:
            node_id = node_data.pop('id')
            graph.add_node(node_id, **node_data)

        for edge_data in data['edges']:
            source = edge_data.pop('source')
            target = edge_data.pop('target')
            graph.add_edge(source, target, **edge_data)

        return graph

    def __contains__(self, node_id: str) -> bool:
        """Support 'node_id in graph' syntax."""
        return self.has_node(node_id)
