#!/usr/bin/env python3
"""
Hybrid Retrieval Pipeline - Phase 4

Combines multiple search strategies for better results:
1. Vector search (semantic similarity)
2. Graph traversal (relationship-based)
3. Result fusion and reranking
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import sys
import os

# Force UTF-8 console output (avoids cp1252 UnicodeEncodeError on Windows)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:  # pragma: no cover
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Add graph directory to path for SimpleGraph import
sys.path.insert(0, str(Path(__file__).parent / "graph"))
from simple_graph import SimpleGraph

KB_ROOT = Path(__file__).parent
VECTOR_DB = KB_ROOT / "vector_db"
GRAPH_PATH = KB_ROOT / "graph" / "td_knowledge_graph_simple.json"


class HybridRetrieval:
    """
    Multi-stage retrieval combining vector search and graph queries.
    """

    def __init__(self):
        print("Initializing Hybrid Retrieval System...")

        # Load vector search components
        self._load_vector_search()

        # Load knowledge graph
        self._load_graph()

        print("[OK] Hybrid retrieval system ready!\n")

    def _load_vector_search(self):
        """Load embeddings and vector search components."""
        print("  Loading vector database...")
        self.embeddings = np.load(VECTOR_DB / "embeddings.npy")

        with open(VECTOR_DB / "vector_index.json", 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)

        with open(VECTOR_DB / "embeddings_metadata.json", 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        model_name = metadata['model_name']
        self.model = SentenceTransformer(model_name)

        # Create operator name to chunk index mapping
        self.operator_chunks = defaultdict(list)
        for idx, chunk in enumerate(self.chunks):
            op_name = chunk.get('meta', {}).get('operator_name')
            if op_name:
                self.operator_chunks[op_name].append(idx)

        print(f"    Loaded {len(self.chunks)} chunks")

    def _load_graph(self):
        """Load knowledge graph."""
        if not GRAPH_PATH.exists():
            print(f"    Warning: Graph not found at {GRAPH_PATH}")
            self.graph = None
            return

        print(f"  Loading knowledge graph...")
        try:
            self.graph = SimpleGraph.load_from_json(GRAPH_PATH)
            print(f"    Loaded graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        except Exception as e:
            print(f"    Warning: Could not load graph: {e}")
            self.graph = None

    def vector_search(self, query: str, n_results: int = 20) -> List[Tuple[Dict, float]]:
        """
        Stage 1: Vector search for semantic similarity.

        Args:
            query: Search query
            n_results: Number of results to return

        Returns:
            List of (chunk, score) tuples
        """
        # Embed query
        query_embedding = self.model.encode([query], convert_to_numpy=True)

        # Calculate similarities
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]

        # Get top results
        top_indices = np.argsort(similarities)[::-1][:n_results]

        results = []
        for idx in top_indices:
            chunk = self.chunks[idx]
            score = float(similarities[idx])
            results.append((chunk, score))

        return results

    def graph_expand(self, initial_results: List[Tuple[Dict, float]],
                     max_expansions: int = 10) -> List[Tuple[Dict, float]]:
        """
        Stage 2: Graph expansion to find related operators.

        Args:
            initial_results: Results from vector search
            max_expansions: Maximum number of expansions

        Returns:
            List of (chunk, score) tuples from graph expansion
        """
        if not self.graph:
            return []

        # Extract operator names from initial results
        operators = set()
        for chunk, score in initial_results[:5]:  # Use top 5 for expansion
            op_name = chunk.get('meta', {}).get('operator_name')
            if op_name:
                operators.add(op_name)

        # Find related operators through graph
        related_operators = set()
        for op_name in operators:
            if op_name not in self.graph:
                continue

            # Get neighbors (related operators)
            neighbors = list(self.graph.neighbors(op_name))
            related_operators.update(neighbors[:3])  # Top 3 neighbors per operator

        # Limit expansions
        related_operators = list(related_operators - operators)[:max_expansions]

        # Get chunks for related operators
        expanded_results = []
        for op_name in related_operators:
            if op_name in self.operator_chunks:
                # Get overview chunk (tier 1)
                for chunk_idx in self.operator_chunks[op_name]:
                    chunk = self.chunks[chunk_idx]
                    if chunk.get('meta', {}).get('tier') == 1:
                        # Assign lower score for expanded results
                        expanded_results.append((chunk, 0.4))
                        break

        return expanded_results

    def reciprocal_rank_fusion(self,
                               vector_results: List[Tuple[Dict, float]],
                               graph_results: List[Tuple[Dict, float]],
                               k: int = 60) -> List[Tuple[Dict, float]]:
        """
        Stage 3: Reciprocal Rank Fusion (RRF) to combine results.

        RRF formula: score = sum(1 / (k + rank)) for each result list

        Args:
            vector_results: Results from vector search
            graph_results: Results from graph expansion
            k: RRF constant (default 60)

        Returns:
            Fused and reranked results
        """
        # Build score dictionary
        scores = defaultdict(float)
        chunk_map = {}

        # Add vector search scores
        for rank, (chunk, _) in enumerate(vector_results):
            chunk_id = chunk['id']
            scores[chunk_id] += 1.0 / (k + rank + 1)
            chunk_map[chunk_id] = chunk

        # Add graph expansion scores
        for rank, (chunk, _) in enumerate(graph_results):
            chunk_id = chunk['id']
            scores[chunk_id] += 0.5 / (k + rank + 1)  # Lower weight for graph
            chunk_map[chunk_id] = chunk

        # Sort by fused score
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Build result list
        fused_results = []
        for chunk_id, score in sorted_results:
            chunk = chunk_map[chunk_id]
            fused_results.append((chunk, score))

        return fused_results

    def hybrid_search(self, query: str, n_results: int = 5) -> List[Tuple[Dict, float]]:
        """
        Full hybrid search pipeline.

        Args:
            query: Search query
            n_results: Number of final results

        Returns:
            List of (chunk, score) tuples
        """
        # Stage 1: Vector search
        vector_results = self.vector_search(query, n_results=20)

        # Stage 2: Graph expansion (if graph available)
        graph_results = []
        if self.graph:
            graph_results = self.graph_expand(vector_results, max_expansions=10)

        # Stage 3: Fusion and reranking
        if graph_results:
            fused_results = self.reciprocal_rank_fusion(vector_results, graph_results)
        else:
            fused_results = vector_results

        # Return top N
        return fused_results[:n_results]

    def print_results(self, query: str, results: List[Tuple[Dict, float]]):
        """Pretty print search results."""
        print("=" * 80)
        print(f"HYBRID SEARCH: {query}")
        print("=" * 80)
        print()

        for i, (chunk, score) in enumerate(results, 1):
            source = chunk.get('meta', {}).get('source', 'unknown')
            chunk_type = chunk.get('chunk_type', 'unknown')

            print(f"{i}. [{source.upper()}] Score: {score:.4f}")

            # Show type-specific info
            if source == 'docs':
                op_name = chunk.get('meta', {}).get('operator_name', 'N/A')
                tier = chunk.get('meta', {}).get('tier', '?')
                print(f"   Operator: {op_name} (Tier {tier} - {chunk_type})")
            elif source == 'snippets':
                op_type = chunk.get('meta', {}).get('operator_type', 'N/A')
                example = chunk.get('meta', {}).get('example', 'N/A')
                has_curator = chunk.get('meta', {}).get('has_curator_summary', False)
                curator_mark = " [CURATOR]" if has_curator else ""
                print(f"   Example: {example} ({op_type}){curator_mark}")
            elif source == 'palette':
                palette_name = chunk.get('meta', {}).get('palette_name', 'N/A')
                print(f"   Palette: {palette_name}")

            # Show text preview
            text = chunk.get('text', '')
            text_preview = text[:200] + "..." if len(text) > 200 else text
            print(f"   {text_preview}")
            print()


def test_hybrid_search():
    """Test hybrid search with sample queries."""
    retrieval = HybridRetrieval()

    test_queries = [
        "How do I control animation speed?",
        "audio visualization with FFT",
        "3D camera controls",
    ]

    for query in test_queries:
        results = retrieval.hybrid_search(query, n_results=5)
        retrieval.print_results(query, results)
        print("\n" + "-" * 80 + "\n")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        # Command line search
        query = ' '.join(sys.argv[1:])
        retrieval = HybridRetrieval()
        results = retrieval.hybrid_search(query, n_results=5)
        retrieval.print_results(query, results)
    else:
        # Run tests
        test_hybrid_search()
