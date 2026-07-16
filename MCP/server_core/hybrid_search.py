#!/usr/bin/env python3
"""
Hybrid GraphRAG Search for TouchDesigner
Combines vector search (semantic) + graph queries (relationships)
This is what the AI agents will use!
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional

# Import enhanced_graph_query (required, no dependencies)
import importlib.util

try:
    spec = importlib.util.spec_from_file_location("enhanced_graph_query", "enhanced_graph_query.py")
    graph_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(graph_module)
    EnhancedGraphQuery = graph_module.EnhancedGraphQuery
except Exception as e:
    print(f"Error importing enhanced_graph_query: {e}")
    raise ImportError(f"Could not import enhanced_graph_query: {e}")

class HybridGraphRAG:
    """
    Hybrid search combining:
    - Vector search for semantic similarity
    - Graph traversal for relationships
    """
    
    def __init__(self,
                 vectordb_path: Optional[str] = None,
                 graph_path: Optional[str] = None):
        # Default both paths to artefacts next to this file so standalone use
        # works without configuration. Callers (mcp_server.py, the unified
        # search adapter) override explicitly.
        from pathlib import Path
        _here = Path(__file__).parent
        if vectordb_path is None:
            vectordb_path = str(_here / "data" / "vector_db_merged")
        if graph_path is None:
            graph_path = str(_here / "data" / "td_knowledge_graph_enhanced.gpickle")

        print("[INIT] Initializing Enhanced Hybrid GraphRAG...")

        # Load vector search (for offline wiki HTML data)
        # Import search_docs here (requires sentence_transformers)
        print("  Loading vector database (wiki documentation)...")
        try:
            spec = importlib.util.spec_from_file_location("search_docs", "search_docs.py")
            search_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(search_module)
            TDDocSearch = search_module.TDDocSearch
            self.vector_search = TDDocSearch(vectordb_path)
        except Exception as e:
            raise ImportError(f"Could not load vector search (requires sentence_transformers): {e}")

        # Load enhanced knowledge graph (with real examples and parameters)
        print("  Loading enhanced knowledge graph...")
        self.knowledge_graph = EnhancedGraphQuery(graph_path)

        print("[OK] Enhanced Hybrid GraphRAG ready!\n")
    
    def search(self, query: str, n_results: int = 5, 
               include_relationships: bool = True,
               relationship_depth: int = 1) -> Dict:
        """
        Hybrid search with both semantic and relationship results
        
        Args:
            query: Natural language question
            n_results: Number of vector search results
            include_relationships: Whether to include graph relationships
            relationship_depth: How many hops to traverse in graph
        
        Returns:
            Dict with 'semantic_results' and 'relationships'
        """
        # 1. Vector search for semantic similarity
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
        Find workflows showing how operators are used together
        Returns examples that contain both operators
        """
        # Find examples using both operators
        examples = self.knowledge_graph.find_examples_by_operator_combination(
            [start_op, end_op],
            require_connection=True,
            limit=5
        )
        return examples
    
    def get_operators_for_concept(self, concept: str, n_vector: int = 10) -> Dict:
        """
        Find operators related to a concept using both vector and graph

        Args:
            concept: Concept to search (e.g., "forces", "collision", "rendering")
            n_vector: Number of vector search results

        Returns:
            Dict with vector results and graph examples
        """
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
        Get complete information about an operator from all sources

        Returns: Full operator documentation + real examples + parameters
        """
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
        Answer a question using hybrid search
        Returns formatted answer with sources
        """
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

def interactive_mode(hybrid: HybridGraphRAG):
    """Interactive hybrid search"""
    print("="*70)
    print("HYBRID GRAPHRAG - Interactive Mode")
    print("="*70)
    print("\nCommands:")
    print("  <question>                  - Hybrid search")
    print("  workflow <op1> to <op2>     - Find operator workflow")
    print("  concept <concept>           - Find operators for concept")
    print("  info <operator>             - Complete operator info")
    print("  quit                        - Exit")
    print()
    
    while True:
        try:
            cmd = input("🔍 Query: ").strip()
            
            if cmd.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break
            
            if not cmd:
                continue
            
            # Parse command
            if cmd.startswith('workflow ') and ' to ' in cmd:
                parts = cmd.split(' to ')
                start = parts[0].replace('workflow ', '').strip()
                end = parts[1].strip()
                
                paths = hybrid.find_operator_workflow(start, end)
                print(f"\nWorkflows from {start} to {end}:")
                for i, path in enumerate(paths, 1):
                    print(f"  {i}. {' → '.join(path)}")
            
            elif cmd.startswith('concept '):
                concept = cmd.replace('concept ', '').strip()
                results = hybrid.get_operators_for_concept(concept)
                
                print(f"\nOperators for concept: {concept}")
                print("\nFrom vector search:")
                for r in results['vector_matches'][:5]:
                    meta = r['metadata']
                    print(f"  • {meta.get('operator_name', meta.get('concept_name'))}")
                
                print("\nFrom graph:")
                for r in results['graph_matches'][:5]:
                    print(f"  • {r['name']} ({r['family']})")
            
            elif cmd.startswith('info '):
                operator = cmd.replace('info ', '').strip()
                info = hybrid.get_complete_operator_info(operator)
                
                print(f"\n{info['name']} - Complete Information")
                print(f"\nParameters: {len(info['parameters'])}")
                print(f"Related operators: {len(info['related_operators'])}")
                print(f"Python API: {info['python_api']}")
                
                if info['documentation']:
                    print(f"\nDocumentation snippets:")
                    for i, doc in enumerate(info['documentation'][:3], 1):
                        print(f"  {i}. {doc['content'][:150]}...")
            
            else:
                # Regular hybrid search
                answer = hybrid.answer_question(cmd)
                print(f"\n{answer}")
            
            print()
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
            import traceback
            traceback.print_exc()

def main():
    if len(sys.argv) < 2:
        print("\nHybrid GraphRAG for TouchDesigner")
        print("="*70)
        print("\nUsage:")
        print("  python hybrid_search.py interactive")
        print('  python hybrid_search.py "What POPs work with forces?"')
        print("\n" + "="*70)
        sys.exit(1)
    
    # Initialize
    try:
        hybrid = HybridGraphRAG()
    except Exception as e:
        print(f"\nERROR: Could not initialize Hybrid GraphRAG")
        print(f"  {e}")
        print("\nThis class is the frozen legacy A/B baseline for the retrieval eval")
        print("harness — run it via: python eval/run_eval.py --backend legacy")
        print("(the harness supplies the KB paths and working directory).")
        sys.exit(1)
    
    # Interactive mode
    if sys.argv[1].lower() == 'interactive':
        interactive_mode(hybrid)
        return
    
    # Single query
    question = sys.argv[1]
    answer = hybrid.answer_question(question)
    print(answer)

if __name__ == '__main__':
    main()
