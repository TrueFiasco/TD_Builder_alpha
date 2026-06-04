#!/usr/bin/env python3
"""
Create vector embeddings for TouchDesigner knowledge base.
Uses ChromaDB for storage and sentence-transformers for embeddings.

Install requirements:
    pip install chromadb sentence-transformers

Usage:
    python create_embeddings.py           # Create embeddings
    python create_embeddings.py --query "blur an image"  # Test query
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Lazy imports for faster startup
chromadb = None
SentenceTransformer = None

DOCS_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\embedding_docs\all_embedding_docs.json")
CHROMA_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\chroma_db")
COLLECTION_NAME = "touchdesigner_knowledge"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Fast, good quality, free
BATCH_SIZE = 500  # Documents per batch


def lazy_import():
    """Import heavy libraries only when needed."""
    global chromadb, SentenceTransformer
    if chromadb is None:
        import chromadb as _chromadb
        from sentence_transformers import SentenceTransformer as _ST
        chromadb = _chromadb
        SentenceTransformer = _ST


def load_documents() -> List[Dict[str, Any]]:
    """Load prepared embedding documents."""
    with open(DOCS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('documents', [])


def create_embeddings():
    """Create embeddings and store in ChromaDB."""
    lazy_import()

    print(f"Loading documents from {DOCS_PATH}...")
    documents = load_documents()
    print(f"Loaded {len(documents)} documents")

    print(f"\nLoading embedding model: {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    print(f"\nInitializing ChromaDB at {CHROMA_PATH}...")
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Delete existing collection if it exists
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection: {COLLECTION_NAME}")
    except:
        pass

    # Create new collection
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "TouchDesigner knowledge base for semantic search"}
    )

    print(f"\nGenerating embeddings and storing (batch size: {BATCH_SIZE})...")

    total_batches = (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(documents), BATCH_SIZE):
        batch = documents[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1

        # Extract data for this batch
        ids = [doc['id'] for doc in batch]
        texts = [doc['text'] for doc in batch]
        metadatas = [doc.get('metadata', {}) for doc in batch]

        # Add type and family to metadata, filter out None values and convert lists
        for i, doc in enumerate(batch):
            metadatas[i]['type'] = doc.get('type', '')
            metadatas[i]['family'] = doc.get('family', '')
            # ChromaDB doesn't accept None values or lists - filter/convert them
            cleaned = {}
            for k, v in metadatas[i].items():
                if v is None or v == '':
                    continue
                if isinstance(v, list):
                    v = ', '.join(str(x) for x in v)
                cleaned[k] = v
            metadatas[i] = cleaned

        # Generate embeddings
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        # Add to collection
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

        print(f"  Batch {batch_num}/{total_batches}: {len(batch)} documents")

    print(f"\n=== Complete ===")
    print(f"Total documents embedded: {len(documents)}")
    print(f"ChromaDB path: {CHROMA_PATH}")
    print(f"Collection: {COLLECTION_NAME}")


def query_knowledge(query: str, n_results: int = 5, filter_type: str = None):
    """Query the knowledge base."""
    lazy_import()

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)

    # Load model for query embedding
    model = SentenceTransformer(EMBEDDING_MODEL)
    query_embedding = model.encode([query]).tolist()

    # Build where filter
    where_filter = None
    if filter_type:
        where_filter = {"type": filter_type}

    # Query
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"]
    )

    return results


def print_results(results: dict, query: str):
    """Pretty print query results."""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")

    docs = results.get('documents', [[]])[0]
    metas = results.get('metadatas', [[]])[0]
    dists = results.get('distances', [[]])[0]
    ids = results.get('ids', [[]])[0]

    for i, (doc, meta, dist, doc_id) in enumerate(zip(docs, metas, dists, ids)):
        similarity = 1 - dist  # Convert distance to similarity
        doc_type = meta.get('type', 'unknown')
        family = meta.get('family', '')

        print(f"\n[{i+1}] {doc_type.upper()} ({family}) - Score: {similarity:.3f}")
        print(f"    ID: {doc_id}")
        print(f"    {doc[:200]}{'...' if len(doc) > 200 else ''}")


def interactive_query():
    """Interactive query mode."""
    print("\n=== TouchDesigner Knowledge Query ===")
    print("Type your query, or 'quit' to exit")
    print("Prefix with 'op:' for operators only, 'param:' for parameters, etc.")

    while True:
        try:
            query = input("\nQuery> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not query or query.lower() == 'quit':
            break

        # Check for type filter
        filter_type = None
        if query.startswith('op:'):
            filter_type = 'operator'
            query = query[3:].strip()
        elif query.startswith('param:'):
            filter_type = 'parameter'
            query = query[6:].strip()
        elif query.startswith('concept:'):
            filter_type = 'concept'
            query = query[8:].strip()
        elif query.startswith('py:'):
            filter_type = 'python_pattern'
            query = query[3:].strip()

        results = query_knowledge(query, n_results=5, filter_type=filter_type)
        print_results(results, query)


def main():
    parser = argparse.ArgumentParser(description="TouchDesigner Knowledge Embeddings")
    parser.add_argument('--create', action='store_true', help="Create embeddings")
    parser.add_argument('--query', type=str, help="Query the knowledge base")
    parser.add_argument('--interactive', action='store_true', help="Interactive query mode")
    parser.add_argument('--n', type=int, default=5, help="Number of results")
    parser.add_argument('--type', type=str, help="Filter by type (operator, parameter, concept, etc.)")

    args = parser.parse_args()

    if args.create:
        create_embeddings()
    elif args.query:
        results = query_knowledge(args.query, n_results=args.n, filter_type=args.type)
        print_results(results, args.query)
    elif args.interactive:
        interactive_query()
    else:
        # Default: create if DB doesn't exist, otherwise interactive
        if not CHROMA_PATH.exists():
            print("No embedding database found. Creating...")
            create_embeddings()
        interactive_query()


if __name__ == '__main__':
    main()
