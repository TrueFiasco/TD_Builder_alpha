#!/usr/bin/env python3
"""
Semantic Search for TouchDesigner Documentation
Search through all TD docs using natural language queries
"""

from sentence_transformers import SentenceTransformer
import chromadb
from typing import List, Dict, Optional
import sys

class TDDocSearch:
    """Semantic search for TouchDesigner documentation"""
    
    def __init__(self, vectordb_path: Optional[str] = None):
        # Default to the merged store next to this file so standalone use works
        # without configuration. Callers can override (e.g. mcp_server.py does).
        if vectordb_path is None:
            from pathlib import Path
            vectordb_path = str(Path(__file__).parent / "data" / "vector_db_merged")
        print("🔍 Loading TouchDesigner documentation search...")
        
        # Load model
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Connect to Chroma
        client = chromadb.PersistentClient(path=vectordb_path)
        self.collection = client.get_collection("td_unified")
        
        count = self.collection.count()
        print(f"✓ Ready! Loaded {count:,} documentation chunks\n")
    
    def search(self, query: str, n_results: int = 5, filter_family: str = None) -> List[Dict]:
        """
        Search documentation with natural language query
        
        Args:
            query: Natural language question
            n_results: Number of results to return
            filter_family: Optional operator family filter (CHOP, TOP, SOP, etc.)
        
        Returns:
            List of results with content, metadata, and relevance scores
        """
        # Embed query
        query_embedding = self.model.encode(query, convert_to_numpy=True)
        
        # Build filter if needed
        where = None
        if filter_family:
            where = {"family": filter_family.upper()}
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where
        )
        
        # Format results
        formatted = []
        for doc, metadata, distance in zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ):
            formatted.append({
                'content': doc,
                'metadata': metadata,
                'score': 1 - distance,  # Convert distance to similarity score
                'distance': distance
            })
        
        return formatted
    
    def print_results(self, query: str, results: List[Dict]):
        """Pretty print search results"""
        print("="*70)
        print(f"🔍 Query: {query}")
        print("="*70)
        print()
        
        if not results:
            print("No results found.")
            return
        
        for i, result in enumerate(results, 1):
            meta = result['metadata']
            
            # Get title
            if 'operator_name' in meta:
                title = f"{meta['operator_name']}"
                if 'parameter_name' in meta:
                    title += f" - {meta['parameter_name']}"
                elif 'family' in meta:
                    title += f" ({meta['family']})"
            elif 'class_name' in meta:
                title = f"{meta['class_name']} Class"
                if 'method_name' in meta:
                    title += f".{meta['method_name']}()"
                elif 'member_name' in meta:
                    title += f".{meta['member_name']}"
            elif 'concept_name' in meta:
                title = meta['concept_name']
                if 'section_title' in meta:
                    title += f" - {meta['section_title']}"
            else:
                title = "Unknown"
            
            # Print result
            print(f"{i}. {title}")
            print(f"   Score: {result['score']:.3f}")
            print(f"   {result['content'][:250]}...")
            print()

def interactive_mode(search_engine: TDDocSearch):
    """Interactive search mode"""
    print("="*70)
    print("TOUCHDESIGNER DOCUMENTATION SEARCH - Interactive Mode")
    print("="*70)
    print("\nType your questions (or 'quit' to exit)")
    print("Examples:")
    print("  - How do I analyze channel peaks?")
    print("  - What POPs work with forces?")
    print("  - How to create particle collisions?")
    print("  - What's the difference between CHOP and TOP?")
    print()
    
    while True:
        try:
            query = input("🔍 Query: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break
            
            if not query:
                continue
            
            # Search
            results = search_engine.search(query, n_results=5)
            print()
            search_engine.print_results(query, results)
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")

def main():
    if len(sys.argv) < 2:
        print("\nTouchDesigner Documentation Search")
        print("="*70)
        print("\nUsage:")
        print("  python search_docs.py <query>              # Single query")
        print("  python search_docs.py interactive          # Interactive mode")
        print("  python search_docs.py <query> --family CHOP  # Filter by family")
        print("\nExamples:")
        print('  python search_docs.py "How do I analyze peaks?"')
        print('  python search_docs.py "particle forces" --family POP')
        print('  python search_docs.py interactive')
        print("\n" + "="*70)
        sys.exit(1)
    
    # Initialize search
    try:
        search_engine = TDDocSearch()
    except Exception as e:
        print(f"\nERROR: Could not load vector database")
        print(f"  {e}")
        print("\nMake sure you've run: python build_embeddings.py td_graphrag.json")
        sys.exit(1)
    
    # Interactive mode
    if sys.argv[1].lower() == 'interactive':
        interactive_mode(search_engine)
        return
    
    # Single query mode
    query = sys.argv[1]
    
    # Check for family filter
    filter_family = None
    if '--family' in sys.argv:
        idx = sys.argv.index('--family')
        if idx + 1 < len(sys.argv):
            filter_family = sys.argv[idx + 1]
    
    # Search
    results = search_engine.search(query, n_results=5, filter_family=filter_family)
    search_engine.print_results(query, results)

if __name__ == '__main__':
    main()
