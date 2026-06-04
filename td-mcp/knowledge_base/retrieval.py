#!/usr/bin/env python3
"""
Enhanced Hybrid Retrieval Pipeline

Multi-stage retrieval with caching and parallel execution:
1. Vector search (semantic similarity)
2. Graph expansion (relationships)
3. Reciprocal Rank Fusion
"""

import json
import numpy as np
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import sys
import os

# Force UTF-8 console output
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from .graph import SimpleGraph
from .cache.query_cache import QueryCache

# Paths relative to this module
KB_ROOT = Path(__file__).parent
VECTOR_DB = KB_ROOT / "vector_db"
GRAPH_PATH = KB_ROOT / "graph" / "knowledge_graph.json"


class EnhancedHybridRetrieval:
    """
    Multi-stage retrieval with caching and parallel execution.

    Features:
    - Stage 1: Vector search (semantic similarity)
    - Stage 2: Graph expansion (relationships)
    - Stage 3: Reciprocal Rank Fusion
    - Query caching for performance
    - Error handling with fallback
    """

    def __init__(self, enable_cache: bool = True, cache_ttl_hours: int = 24):
        print("Initializing Enhanced Hybrid Retrieval System...")

        self._load_vector_search()
        self._load_graph()

        self.cache = None
        if enable_cache:
            try:
                self.cache = QueryCache(ttl_hours=cache_ttl_hours)
                print("  [OK] Query cache enabled")
            except Exception as e:
                print(f"  Warning: Could not initialize cache: {e}")

        self.stats = {
            'total_queries': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'vector_search_times': [],
            'graph_expansion_times': [],
            'total_query_times': []
        }

        print("[OK] Enhanced hybrid retrieval system ready!\n")

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
        """Stage 1: Vector search for semantic similarity."""
        start_time = time.time()

        try:
            query_embedding = self.model.encode([query], convert_to_numpy=True)
            similarities = cosine_similarity(query_embedding, self.embeddings)[0]
            top_indices = np.argsort(similarities)[::-1][:n_results]

            results = []
            for idx in top_indices:
                chunk = self.chunks[idx]
                score = float(similarities[idx])
                results.append((chunk, score))

            elapsed = time.time() - start_time
            self.stats['vector_search_times'].append(elapsed)

            return results

        except Exception as e:
            print(f"Error in vector search: {e}")
            return []

    def graph_expand(self, initial_results: List[Tuple[Dict, float]],
                     max_expansions: int = 10) -> List[Tuple[Dict, float]]:
        """Stage 2: Graph expansion to find related operators."""
        if not self.graph:
            return []

        start_time = time.time()

        try:
            operators = set()
            for chunk, score in initial_results[:5]:
                op_name = chunk.get('meta', {}).get('operator_name')
                if op_name:
                    operators.add(op_name)

            related_operators = set()
            for op_name in operators:
                node_id = op_name.lower().replace(' ', '_')

                if node_id not in self.graph:
                    continue

                neighbors = self.graph.neighbors(node_id)
                operator_neighbors = [n for n in neighbors if ':param:' not in n]
                related_operators.update(operator_neighbors[:3])

            related_operators = list(related_operators)[:max_expansions]

            expanded_results = []
            for node_id in related_operators:
                op_name = self.graph.get_node_data(node_id).get('name')

                if op_name and op_name in self.operator_chunks:
                    for chunk_idx in self.operator_chunks[op_name]:
                        chunk = self.chunks[chunk_idx]
                        if chunk.get('meta', {}).get('tier') == 1:
                            expanded_results.append((chunk, 0.4))
                            break

            elapsed = time.time() - start_time
            self.stats['graph_expansion_times'].append(elapsed)

            return expanded_results

        except Exception as e:
            print(f"Error in graph expansion: {e}")
            return []

    def reciprocal_rank_fusion(self,
                               vector_results: List[Tuple[Dict, float]],
                               graph_results: List[Tuple[Dict, float]],
                               k: int = 60) -> List[Tuple[Dict, float]]:
        """Stage 3: Reciprocal Rank Fusion (RRF) to combine results."""
        try:
            scores = defaultdict(float)
            chunk_map = {}

            for rank, (chunk, _) in enumerate(vector_results):
                chunk_id = chunk['id']
                scores[chunk_id] += 1.0 / (k + rank + 1)
                chunk_map[chunk_id] = chunk

            for rank, (chunk, _) in enumerate(graph_results):
                chunk_id = chunk['id']
                scores[chunk_id] += 0.5 / (k + rank + 1)
                chunk_map[chunk_id] = chunk

            sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

            fused_results = []
            for chunk_id, score in sorted_results:
                chunk = chunk_map[chunk_id]
                fused_results.append((chunk, score))

            return fused_results

        except Exception as e:
            print(f"Error in RRF: {e}")
            return vector_results

    async def hybrid_search_async(self, query: str, n_results: int = 5) -> List[Tuple[Dict, float]]:
        """Async hybrid search with parallel execution and caching."""
        start_time = time.time()
        self.stats['total_queries'] += 1

        if self.cache:
            cached_results = self.cache.get(query, n_results)
            if cached_results is not None:
                self.stats['cache_hits'] += 1
                elapsed = time.time() - start_time
                self.stats['total_query_times'].append(elapsed)
                return cached_results
            else:
                self.stats['cache_misses'] += 1

        loop = asyncio.get_running_loop()

        if self.graph:
            vector_task = loop.run_in_executor(None, self.vector_search, query, 20)
            vector_results = await vector_task
            graph_results = await loop.run_in_executor(
                None, self.graph_expand, vector_results, 10
            )
        else:
            vector_results = await loop.run_in_executor(None, self.vector_search, query, 20)
            graph_results = []

        if graph_results:
            fused_results = await loop.run_in_executor(
                None, self.reciprocal_rank_fusion, vector_results, graph_results
            )
        else:
            fused_results = vector_results

        results = fused_results[:n_results]

        if self.cache and results:
            try:
                self.cache.set(query, results, n_results)
            except Exception as e:
                print(f"Warning: Could not cache results: {e}")

        elapsed = time.time() - start_time
        self.stats['total_query_times'].append(elapsed)

        return results

    def hybrid_search(self, query: str, n_results: int = 5) -> List[Tuple[Dict, float]]:
        """Full hybrid search pipeline with caching."""
        start_time = time.time()
        self.stats['total_queries'] += 1

        if self.cache:
            cached_results = self.cache.get(query, n_results)
            if cached_results is not None:
                self.stats['cache_hits'] += 1
                elapsed = time.time() - start_time
                self.stats['total_query_times'].append(elapsed)
                return cached_results
            else:
                self.stats['cache_misses'] += 1

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self.hybrid_search_async(query, n_results))
            loop.close()
        except Exception as e:
            print(f"Error in async search: {e}")
            results = self._hybrid_search_sync(query, n_results)

        if self.cache and results:
            try:
                self.cache.set(query, results, n_results)
            except Exception as e:
                print(f"Warning: Could not cache results: {e}")

        elapsed = time.time() - start_time
        self.stats['total_query_times'].append(elapsed)

        return results

    def _hybrid_search_sync(self, query: str, n_results: int = 5) -> List[Tuple[Dict, float]]:
        """Synchronous fallback for hybrid search."""
        vector_results = self.vector_search(query, n_results=20)

        graph_results = []
        if self.graph:
            graph_results = self.graph_expand(vector_results, max_expansions=10)

        if graph_results:
            fused_results = self.reciprocal_rank_fusion(vector_results, graph_results)
        else:
            fused_results = vector_results

        return fused_results[:n_results]

    def get_performance_stats(self) -> Dict:
        """Get performance statistics."""
        cache_hit_rate = 0
        if self.stats['total_queries'] > 0:
            cache_hit_rate = self.stats['cache_hits'] / self.stats['total_queries']

        avg_vector_time = 0
        if self.stats['vector_search_times']:
            avg_vector_time = sum(self.stats['vector_search_times']) / len(self.stats['vector_search_times'])

        avg_graph_time = 0
        if self.stats['graph_expansion_times']:
            avg_graph_time = sum(self.stats['graph_expansion_times']) / len(self.stats['graph_expansion_times'])

        avg_total_time = 0
        if self.stats['total_query_times']:
            avg_total_time = sum(self.stats['total_query_times']) / len(self.stats['total_query_times'])

        return {
            'total_queries': self.stats['total_queries'],
            'cache_hits': self.stats['cache_hits'],
            'cache_misses': self.stats['cache_misses'],
            'cache_hit_rate': f"{cache_hit_rate:.1%}",
            'avg_vector_search_ms': f"{avg_vector_time * 1000:.1f}",
            'avg_graph_expansion_ms': f"{avg_graph_time * 1000:.1f}",
            'avg_total_query_ms': f"{avg_total_time * 1000:.1f}"
        }
