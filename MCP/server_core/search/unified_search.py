"""
Unified Search Adapter

Backward-compatible API with HybridGraphRAG over the enhanced backend:
local (key-free) embeddings + the Phase-2 hybrid retrieval stack
(dense + BM25 + RRF + router + rerank), degrading to dense-only when the
Phase-2 artifacts are absent.

This adapter maintains 100% API compatibility with the original HybridGraphRAG class.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
import importlib.util

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SearchConfig


class UnifiedSearchAdapter:
    """
    Drop-in replacement for HybridGraphRAG with enhanced capabilities.

    Maintains identical API signatures while using the improved backend:
    local embeddings + the Phase-2 hybrid retrieval stack.
    """

    def __init__(self,
                 vectordb_path: Optional[str] = None,
                 graph_path: Optional[str] = None,
                 use_legacy: bool = False):
        """
        Initialize search adapter.

        Args:
            vectordb_path: Path to vector database (defaults to config)
            graph_path: Path to knowledge graph (defaults to config)
            use_legacy: If True, use original HybridGraphRAG (for A/B testing)
        """
        print("[INIT] Initializing Unified Search Adapter...")

        # Use config defaults if paths not provided
        self.vectordb_path = vectordb_path or str(SearchConfig.VECTOR_DB_PATH)
        self.graph_path = graph_path or str(SearchConfig.GRAPH_DATA_PATH)
        self.use_legacy = use_legacy

        print(f"  Embedding provider: {SearchConfig.EMBEDDING_PROVIDER}")
        print(f"  Embedding model: {SearchConfig.EMBEDDING_MODEL}")
        print(f"  Vector DB path: {self.vectordb_path}")
        print(f"  Graph path: {self.graph_path}")

        # Initialize backend
        if use_legacy:
            print("  Using LEGACY HybridGraphRAG backend")
            self._init_legacy_backend()
        else:
            print("  Using ENHANCED backend with new embeddings")
            self._init_enhanced_backend()

        # No query cache in this release (kept as an attribute for API compat).
        self.cache = None

        print("[OK] Unified Search Adapter ready!\n")

    def _init_legacy_backend(self):
        """Initialize original HybridGraphRAG for A/B testing."""
        try:
            # Import original HybridGraphRAG
            spec = importlib.util.spec_from_file_location(
                "hybrid_search",
                str(Path(__file__).parent.parent / "hybrid_search.py")
            )
            hybrid_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hybrid_module)

            self.backend = hybrid_module.HybridGraphRAG(
                vectordb_path=self.vectordb_path,
                graph_path=self.graph_path
            )
            self.backend_type = "legacy"
        except Exception as e:
            raise ImportError(f"Could not load legacy HybridGraphRAG: {e}")

    def _init_enhanced_backend(self):
        """Initialize enhanced backend with new embedding providers."""
        print("  Loading enhanced knowledge graph...")

        # Load graph query engine (no dependencies)
        try:
            spec = importlib.util.spec_from_file_location(
                "enhanced_graph_query",
                str(Path(__file__).parent.parent / "enhanced_graph_query.py")
            )
            graph_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(graph_module)
            EnhancedGraphQuery = graph_module.EnhancedGraphQuery

            self.knowledge_graph = EnhancedGraphQuery(self.graph_path)
        except Exception as e:
            raise ImportError(f"Could not load enhanced_graph_query: {e}")

        # Load vector search with provider selection
        print(f"  Loading vector search ({SearchConfig.EMBEDDING_PROVIDER})...")
        self._init_vector_search()

        # Phase 2: hybrid retrieval stack (dense + BM25 + RRF + router + rerank +
        # floor/dedup). Resolves lexical_index/ + models/ relative to the KB root.
        # Degrades to dense-only if those artifacts are absent.
        self._init_retrieval_stack()

        self.backend_type = "enhanced"

    def _init_retrieval_stack(self):
        """Construct the Phase-2 RetrievalStack behind the enhanced search path."""
        self.retrieval_stack = None
        if os.environ.get("RS_DISABLE", "").strip().lower() in ("1", "true", "yes", "on"):
            print("  Retrieval stack DISABLED (RS_DISABLE) — dense-only enhanced path")
            return
        try:
            spec = importlib.util.spec_from_file_location(
                "retrieval_stack", str(Path(__file__).parent / "retrieval_stack.py"))
            rs_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rs_module)
            kb_root = Path(self.vectordb_path).parent
            self.retrieval_stack = rs_module.RetrievalStack(
                kb_root=kb_root,
                vector_search=self.vector_search,
                knowledge_graph=self.knowledge_graph,
            )
            print("  Retrieval stack ready (Phase 2 hybrid)")
        except Exception as e:
            print(f"  Warning: retrieval stack init failed ({e}); dense-only fallback")
            self.retrieval_stack = None

    def _init_vector_search(self):
        """Initialize vector search — local embeddings only (key-free release)."""
        if SearchConfig.EMBEDDING_PROVIDER != "local":
            print(f"  Warning: EMBEDDING_PROVIDER={SearchConfig.EMBEDDING_PROVIDER!r} is not "
                  "supported (key-free/local-only release); using local embeddings")
        self._init_local_vector_search()

    def _init_local_vector_search(self):
        """Initialize local sentence-transformers vector search."""
        try:
            spec = importlib.util.spec_from_file_location(
                "search_docs",
                str(Path(__file__).parent.parent / "search_docs.py")
            )
            search_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(search_module)
            TDDocSearch = search_module.TDDocSearch

            self.vector_search = TDDocSearch(self.vectordb_path)
            self.embedding_provider = "local"
        except Exception as e:
            raise ImportError(f"Could not load local vector search: {e}")

    # ==================================================================
    # PUBLIC API - Maintains backward compatibility with HybridGraphRAG
    # ==================================================================

    def search(self, query: str, n_results: int = 5,
               include_relationships: bool = True,
               relationship_depth: int = 1) -> Dict:
        """
        Hybrid search with both semantic and relationship results.

        BACKWARD COMPATIBLE with HybridGraphRAG.search()

        Args:
            query: Natural language question
            n_results: Number of vector search results
            include_relationships: Whether to include graph relationships
            relationship_depth: How many hops to traverse in graph

        Returns:
            Dict with 'semantic_results' and 'relationships'
        """
        # Delegate to backend
        if self.use_legacy:
            result = self.backend.search(
                query, n_results, include_relationships, relationship_depth
            )
        else:
            result = self._enhanced_search(
                query, n_results, include_relationships, relationship_depth
            )

        return result

    def _enhanced_search(self, query: str, n_results: int,
                        include_relationships: bool, relationship_depth: int) -> Dict:
        """Enhanced search implementation with new backend."""
        # 1. Semantic retrieval: Phase-2 hybrid stack if available, else dense-only.
        if getattr(self, "retrieval_stack", None) is not None:
            semantic_results = self.retrieval_stack.search(query, n_results)
        else:
            semantic_results = self.vector_search.search(query, n_results)

        # 2. Extract operator names from results
        operator_names = set()
        for result in semantic_results:
            meta = result['metadata']
            if 'operator_name' in meta:
                operator_names.add(meta['operator_name'])

        # 3. Enhanced graph traversal with real examples and parameters
        relationships = {}

        if include_relationships and operator_names:
            for op_name in list(operator_names)[:3]:  # Top 3 operators
                # Get comprehensive operator info from enhanced graph
                op_info = self.knowledge_graph.get_operator_info(op_name)

                if op_info:
                    # Get real examples demonstrating this operator
                    examples = self.knowledge_graph.find_examples_by_operator(op_name, limit=3)

                    relationships[op_name] = {
                        'operator_name': op_info['operator_name'],
                        'family': op_info['family'],
                        'example_count': op_info['example_count'],
                        'has_text_knowledge': op_info['has_text_knowledge'],
                        'has_network_knowledge': op_info['has_network_knowledge'],
                        'common_parameters': op_info['common_parameters'],
                        'sample_examples': examples[:2]  # Top 2 examples with real params
                    }
                else:
                    relationships[op_name] = {'error': 'Operator not found in enhanced graph'}

        return {
            'query': query,
            'semantic_results': semantic_results,
            'relationships': relationships,
            'operator_count': len(operator_names)
        }

    def find_operator_workflow(self, start_op: str, end_op: str) -> List[Dict]:
        """
        Find workflows showing how operators are used together.

        BACKWARD COMPATIBLE with HybridGraphRAG.find_operator_workflow()

        Returns examples that contain both operators.
        """
        if self.use_legacy:
            return self.backend.find_operator_workflow(start_op, end_op)

        # Enhanced implementation
        examples = self.knowledge_graph.find_examples_by_operator_combination(
            [start_op, end_op],
            require_connection=True,
            limit=5
        )
        return examples

    def get_operators_for_concept(self, concept: str, n_vector: int = 10) -> Dict:
        """
        Find operators related to a concept using both vector and graph.

        BACKWARD COMPATIBLE with HybridGraphRAG.get_operators_for_concept()

        Args:
            concept: Concept to search (e.g., "forces", "collision", "rendering")
            n_vector: Number of vector search results

        Returns:
            Dict with vector results and graph examples
        """
        if self.use_legacy:
            return self.backend.get_operators_for_concept(concept, n_vector)

        # Enhanced implementation
        # Vector search (searches wiki documentation)
        vector_results = self.vector_search.search(concept, n_vector)

        # Graph search (find examples related to concept via text search)
        graph_examples = self.knowledge_graph.search_by_text(concept, limit=10)

        return {
            'concept': concept,
            'vector_matches': vector_results,
            'graph_examples': graph_examples
        }

    def get_complete_operator_info(self, operator_name: str) -> Dict:
        """
        Get complete information about an operator from all sources.

        BACKWARD COMPATIBLE with HybridGraphRAG.get_complete_operator_info()

        Returns: Full operator documentation + real examples + parameters
        """
        if self.use_legacy:
            return self.backend.get_complete_operator_info(operator_name)

        # Enhanced implementation
        # Vector search for documentation (wiki HTML)
        docs = self.vector_search.search(operator_name, n_results=10)

        # Filter for this specific operator
        operator_docs = [
            d for d in docs
            if d['metadata'].get('operator_name', '').lower() == operator_name.lower()
        ]

        # Enhanced graph data (real examples with parameters)
        op_info = self.knowledge_graph.get_operator_info(operator_name)

        return {
            'name': operator_name,
            'documentation': operator_docs,  # From wiki HTML
            'operator_info': op_info,  # From enhanced graph (with real examples)
            'has_enhanced_data': bool(op_info)
        }

    def answer_question(self, question: str, context_size: int = 10) -> str:
        """
        Answer a question using hybrid search.

        BACKWARD COMPATIBLE with HybridGraphRAG.answer_question()

        Returns formatted answer with sources.
        """
        if self.use_legacy:
            return self.backend.answer_question(question, context_size)

        # Enhanced implementation
        # Search
        results = self.search(question, n_results=context_size, include_relationships=True)

        # Build answer text
        answer = f"## Answer to: {question}\n\n"

        answer += "### Relevant Documentation:\n\n"
        for i, result in enumerate(results['semantic_results'][:5], 1):
            meta = result['metadata']
            title = meta.get('operator_name', meta.get('concept_name', 'Unknown'))
            answer += f"{i}. **{title}** (score: {result['score']:.3f})\n"
            answer += f"   {result['content'][:200]}...\n\n"

        if results['relationships']:
            answer += "### Enhanced Operator Information:\n\n"
            for op_name, rels in results['relationships'].items():
                if 'error' in rels:
                    continue
                answer += f"**{rels['operator_name']}** ({rels['family']})\n"
                answer += f"  - Examples available: {rels['example_count']}\n"
                answer += f"  - Has text knowledge: {rels['has_text_knowledge']}\n"
                answer += f"  - Has network knowledge: {rels['has_network_knowledge']}\n"
                if rels['common_parameters']:
                    answer += f"  - Common parameters: {', '.join(list(rels['common_parameters'].keys())[:5])}\n"
                if rels['sample_examples']:
                    answer += f"  - Sample usage: {rels['sample_examples'][0]['label']}\n"
                answer += "\n"

        return answer

    # ==================================================================
    # ADDITIONAL UTILITIES
    # ==================================================================

    def get_backend_info(self) -> Dict:
        """Get information about current backend configuration."""
        return {
            'backend_type': self.backend_type,
            'embedding_provider': SearchConfig.EMBEDDING_PROVIDER if hasattr(self, 'embedding_provider') else self.embedding_provider,
            'embedding_model': SearchConfig.EMBEDDING_MODEL,
            'vector_db_path': self.vectordb_path,
            'graph_path': self.graph_path,
            'cache_enabled': False,
            'use_legacy': self.use_legacy
        }

    def clear_cache(self):
        """No query cache in this release — kept for API compatibility."""
        return False


# Backward compatibility alias
HybridGraphRAG = UnifiedSearchAdapter
