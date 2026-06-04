#!/usr/bin/env python3
"""
Test semantic search with local embeddings.
"""

import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

KB_ROOT = Path(__file__).parent
VECTOR_DB = KB_ROOT / "vector_db"


class LocalEmbeddingSearch:
    """Simple semantic search using local embeddings."""

    def __init__(self):
        print("Loading vector database...")

        # Load embeddings
        self.embeddings = np.load(VECTOR_DB / "embeddings.npy")
        print(f"  Loaded {self.embeddings.shape[0]} embeddings ({self.embeddings.shape[1]} dims)")

        # Load chunk data
        with open(VECTOR_DB / "vector_index.json", 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        print(f"  Loaded {len(self.chunks)} chunks")

        # Load metadata
        with open(VECTOR_DB / "embeddings_metadata.json", 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # Load model (same one used for embedding)
        model_name = metadata['model_name']
        print(f"  Loading model: {model_name}")
        self.model = SentenceTransformer(model_name)
        print("[OK] Search engine ready!\n")

    def search(self, query: str, n_results: int = 5):
        """
        Search for chunks similar to the query.

        Args:
            query: Search query text
            n_results: Number of results to return

        Returns:
            List of (chunk, score) tuples
        """
        # Embed the query
        query_embedding = self.model.encode([query], convert_to_numpy=True)

        # Calculate cosine similarity with all chunks
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]

        # Get top N indices
        top_indices = np.argsort(similarities)[::-1][:n_results]

        # Build results
        results = []
        for idx in top_indices:
            chunk = self.chunks[idx]
            score = float(similarities[idx])
            results.append((chunk, score))

        return results

    def print_results(self, query: str, results: list):
        """Pretty print search results."""
        print("=" * 80)
        print(f"QUERY: {query}")
        print("=" * 80)
        print()

        for i, (chunk, score) in enumerate(results, 1):
            source = chunk.get('meta', {}).get('source', 'unknown')
            chunk_type = chunk.get('chunk_type', 'unknown')

            print(f"{i}. [{source.upper()}] Score: {score:.4f}")

            # Show chunk type specific info
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
                print(f"   Palette Component: {palette_name}")

            # Show text preview
            text = chunk.get('text', '')
            text_preview = text[:200] + "..." if len(text) > 200 else text
            print(f"   {text_preview}")
            print()


def interactive_search():
    """Interactive search mode."""
    searcher = LocalEmbeddingSearch()

    print("=" * 80)
    print("INTERACTIVE SEARCH MODE")
    print("=" * 80)
    print("Enter your search queries (or 'quit' to exit)")
    print()

    while True:
        query = input("Search> ").strip()

        if query.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break

        if not query:
            continue

        results = searcher.search(query, n_results=5)
        searcher.print_results(query, results)


def run_test_queries():
    """Run a set of test queries."""
    searcher = LocalEmbeddingSearch()

    test_queries = [
        "How do I control animation speed?",
        "particle system effects",
        "audio analysis and visualization",
        "camera movement and controls",
        "noise patterns and generation",
    ]

    print("=" * 80)
    print("RUNNING TEST QUERIES")
    print("=" * 80)
    print()

    for query in test_queries:
        results = searcher.search(query, n_results=3)
        searcher.print_results(query, results)
        print()
        print("-" * 80)
        print()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        # Command line search
        query = ' '.join(sys.argv[1:])
        searcher = LocalEmbeddingSearch()
        results = searcher.search(query, n_results=5)
        searcher.print_results(query, results)
    else:
        # Interactive mode
        choice = input("Run test queries (t) or interactive search (i)? [t/i]: ").strip().lower()

        if choice == 't':
            run_test_queries()
        else:
            interactive_search()
