#!/usr/bin/env python3
"""
Build a unified vector index from docs + snippet/palette semantic summaries.

ENHANCED with:
- Multiple embedding providers (Voyage, OpenAI, Cohere, local)
- Hierarchical chunking for better search quality
- Async batch processing for API efficiency
- Metadata enrichment
- Index.tsv curator summaries

Inputs:
- Docs: td_universal_parsed.json (operator summaries)
- Snippets: index.tsv + semantic JSONs
- Operator index (optional) to enrich metadata

Outputs:
- vector_db/ (Chroma with configured embedding provider)
- vector_db/vector_index.json (fallback plain index if embedding backend unavailable)
"""

import argparse
import json
import asyncio
import sys
import csv
from pathlib import Path
from typing import List, Dict, Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import configuration
from META_AGENTIC_TOOL.config import SearchConfig

# Import hierarchical chunking
from kb_pipeline.chunking.semantic_chunker import create_hierarchical_chunks
from kb_pipeline.extract_palette_summaries import collect_palette_chunks

KB_ROOT = Path(r"C:\TD_Projects\kb_pipeline")
DEFAULT_DOCS = Path(r"C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca\td_universal_parsed.json")
DEFAULT_INDEX_TSV = KB_ROOT / "data" / "snippets" / "index.tsv"
DEFAULT_SNIPPET_SEM = KB_ROOT / "data" / "snippets" / "semantic"
DEFAULT_PALETTE_WIKI = KB_ROOT / "data" / "palette_wiki"
DEFAULT_PALETTE_SEM = KB_ROOT / "data" / "palette_semantic"
DEFAULT_PALETTE_ENRICHED = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\data\palette_lossless\enriched_index.json")
DEFAULT_INDEX = KB_ROOT / "index" / "operator_index.json"


class EmbeddingProvider:
    """Unified interface for multiple embedding providers."""

    def __init__(self, provider: str = "local", model: Optional[str] = None, api_key: Optional[str] = None):
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key
        self.client = None
        self.embedding_dim = None

        self._init_provider()

    def _init_provider(self):
        """Initialize the selected embedding provider."""
        if self.provider == "voyage":
            self._init_voyage()
        elif self.provider == "openai":
            self._init_openai()
        elif self.provider == "cohere":
            self._init_cohere()
        elif self.provider == "local":
            self._init_local()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _init_voyage(self):
        """Initialize Voyage AI embeddings."""
        try:
            import voyageai
            self.client = voyageai.Client(api_key=self.api_key or SearchConfig.VOYAGE_API_KEY)
            self.model = self.model or "voyage-code-2"
            self.embedding_dim = 1024
            print(f"[OK] Voyage AI initialized: {self.model} ({self.embedding_dim} dims)")
        except ImportError:
            raise ImportError("voyageai package required. Install with: pip install voyageai")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Voyage AI: {e}")

    def _init_openai(self):
        """Initialize OpenAI embeddings."""
        try:
            import openai
            self.client = openai.OpenAI(api_key=self.api_key or SearchConfig.OPENAI_API_KEY)
            self.model = self.model or "text-embedding-3-large"
            self.embedding_dim = 3072 if "large" in self.model else 1536
            print(f"[OK] OpenAI initialized: {self.model} ({self.embedding_dim} dims)")
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI: {e}")

    def _init_cohere(self):
        """Initialize Cohere embeddings."""
        try:
            import cohere
            self.client = cohere.Client(api_key=self.api_key or SearchConfig.COHERE_API_KEY)
            self.model = self.model or "embed-english-v3.0"
            self.embedding_dim = 1024
            print(f"[OK] Cohere initialized: {self.model} ({self.embedding_dim} dims)")
        except ImportError:
            raise ImportError("cohere package required. Install with: pip install cohere")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Cohere: {e}")

    def _init_local(self):
        """Initialize local sentence-transformers."""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = self.model or "all-MiniLM-L6-v2"
            self.client = SentenceTransformer(self.model)
            self.embedding_dim = 384
            print(f"[OK] Local embeddings initialized: {self.model} ({self.embedding_dim} dims)")
        except ImportError:
            raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers")

    async def embed_batch(self, texts: List[str], batch_size: int = 128) -> List[List[float]]:
        """
        Embed a batch of texts asynchronously.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embeddings
        """
        if self.provider == "local":
            # Local embeddings are synchronous
            return self.client.encode(texts, convert_to_numpy=True).tolist()

        # API-based embeddings with batching
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await self._embed_api_batch(batch)
            all_embeddings.extend(embeddings)

            if (i + batch_size) % 500 == 0:
                print(f"  Embedded {i + batch_size}/{len(texts)} chunks...")

        return all_embeddings

    async def _embed_api_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch using API."""
        try:
            if self.provider == "voyage":
                result = self.client.embed(texts, model=self.model)
                return result.embeddings

            elif self.provider == "openai":
                result = self.client.embeddings.create(
                    input=texts,
                    model=self.model
                )
                return [item.embedding for item in result.data]

            elif self.provider == "cohere":
                result = self.client.embed(
                    texts=texts,
                    model=self.model,
                    input_type="search_document"
                )
                return result.embeddings

        except Exception as e:
            print(f"Warning: Batch embedding failed: {e}")
            raise


def load_index_tsv(index_path: Path) -> Dict[str, str]:
    """
    Load index.tsv to get curator summaries.

    Returns: dict of {familyoptype/example: curator_text}
    """
    summaries = {}

    if not index_path.exists():
        print(f"Warning: index.tsv not found at {index_path}")
        return summaries

    with open(index_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            # Create key from family/optype/example
            relpath = row.get('relpath', '')
            text = row.get('text', '').strip()

            if relpath and text:
                summaries[relpath] = text

    print(f"Loaded {len(summaries)} curator summaries from index.tsv")
    return summaries


def collect_docs_hierarchical(doc_path: Path) -> List[Dict]:
    """Collect docs with hierarchical chunking."""
    if not doc_path.exists():
        print(f"Warning: Docs not found at {doc_path}")
        return []

    with open(doc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_chunks = []
    operators = data.get("operators", [])

    print(f"Processing {len(operators)} operators with hierarchical chunking...")

    for op in operators:
        # Use hierarchical chunking
        try:
            chunks = create_hierarchical_chunks(op)
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"Warning: Failed to chunk {op.get('name', 'unknown')}: {e}")

    print(f"  Generated {len(all_chunks)} chunks from {len(operators)} operators")
    return all_chunks


def collect_snippets_with_summaries(sem_dir: Path, index_tsv_path: Path) -> List[Dict]:
    """
    Collect snippet examples enhanced with curator summaries from index.tsv.

    Returns chunks with semantic info + curator text.
    """
    rows = []

    if not sem_dir.exists():
        print(f"Warning: Semantic dir not found: {sem_dir}")
        return rows

    # Load curator summaries
    curator_summaries = load_index_tsv(index_tsv_path)

    noisy_param_keys = {
        "pageindex",
        "defaultreadencoding",
        "language",
        "wordwrap",
        "w",
        "h",
        "mousewheel",
        "uvbuttonsleft",
        "uvbuttonsmiddle",
        "uvbuttonsright",
        "topsmoothness",
    }

    numeric_param_whitelist = {
        "gain",
        "speed",
        "freq",
        "frequency",
        "period",
        "amplitude",
        "amp",
        "threshold",
        "resolutionw",
        "resolutionh",
        "fov",
        "tx",
        "ty",
        "tz",
        "rx",
        "ry",
        "rz",
        "scale",
        "scalex",
        "scaley",
        "scalez",
    }

    def _local_name(name_or_path: str) -> str:
        if not name_or_path:
            return ""
        if "/" in name_or_path:
            return name_or_path.rstrip("/").split("/")[-1]
        return name_or_path

    def _format_params(params: Dict[str, Any]) -> str:
        if not params:
            return ""
        pairs: List[str] = []
        for key, value in params.items():
            if key in noisy_param_keys:
                continue
            if isinstance(value, (dict, list)):
                continue
            if isinstance(value, (int, float)) and key not in numeric_param_whitelist:
                continue
            if isinstance(value, str) and len(value) > 80:
                continue
            pairs.append(f"{key}={value}")
            if len(pairs) >= 2:
                break
        return ", ".join(pairs)

    for sem_path in sem_dir.glob("*_semantic.json"):
        with open(sem_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        op_type = data.get("operator_type") or sem_path.stem.replace("_semantic", "")
        examples = data.get("examples", [])

        for idx, ex in enumerate(examples):
            # Get example metadata
            ex_name = ex.get("example_name", "") or ex.get("name", "")
            topic = ex.get("topic", "")
            ops = ex.get("operators", [])
            conns = ex.get("connections", [])

            # Build operator snippet summary (lightweight, low-noise)
            op_snippets = []
            for op in ops:
                name = op.get("name")
                otype = op.get("type")
                if not name or not otype:
                    continue
                if str(name).lower() in {"readme", "readme1"} and str(otype).upper().startswith("DAT:"):
                    continue
                params = op.get("parameters", {}) or {}
                param_text = _format_params(params)
                op_snippets.append(f"{name} ({otype}){(' ' + param_text) if param_text else ''}".strip())

            # Connections summary (limited)
            conn_snippets = []
            for conn in conns:
                src = _local_name(conn.get("from", ""))
                dst = _local_name(conn.get("to", ""))
                if not src or not dst:
                    continue
                to_input = conn.get("to_input", None)
                if to_input in (None, "", "0", 0):
                    conn_snippets.append(f"{src} -> {dst}")
                else:
                    conn_snippets.append(f"{src} -> {dst} (in {to_input})")
                if len(conn_snippets) >= 8:
                    break

            # Construct relpath to match index.tsv format
            # index.tsv format: "CHOP/analyzeCHOP/example1"
            # We need to infer family from operator_type
            family = "UNKNOWN"
            if "CHOP" in op_type.upper():
                family = "CHOP"
            elif "TOP" in op_type.upper():
                family = "TOP"
            elif "SOP" in op_type.upper():
                family = "SOP"
            elif "DAT" in op_type.upper():
                family = "DAT"
            elif "COMP" in op_type.upper():
                family = "COMP"
            elif "POP" in op_type.upper():
                family = "POP"
            elif "MAT" in op_type.upper():
                family = "MAT"

            relpath = f"{family}/{op_type}/{ex_name}"

            # Look up curator summary from index.tsv
            curator_text = curator_summaries.get(relpath, "")

            # Build enhanced text with curator summary
            text_parts = []

            # Start with curator summary if available (most valuable!)
            if curator_text:
                text_parts.append(f"Description: {curator_text}")

            # Add structured info
            text_parts.append(f"Example: {ex_name} for {op_type}")
            if topic:
                text_parts.append(f"Topic: {topic}")

            if conn_snippets:
                text_parts.append("Connections: " + "; ".join(conn_snippets))

            # Add operator details (limit)
            if op_snippets:
                text_parts.append("Operators: " + "; ".join(op_snippets[:8]))

            uid = f"snippet::{op_type}::{ex_name}::{idx}"

            rows.append({
                "id": uid,
                "text": "\n".join(text_parts),
                "meta": {
                    "source": "snippets",
                    "operator_type": op_type,
                    "example": ex_name,
                    "topic": topic,
                    "relpath": relpath,
                    "has_curator_summary": bool(curator_text)
                }
            })

    return rows


def save_fallback_index(rows: List[Dict], out_dir: Path):
    """Save fallback JSON index (no embeddings)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "vector_index.json"

    # Convert Path objects to strings for JSON serialization
    import copy
    serializable_rows = []
    for row in rows:
        row_copy = copy.deepcopy(row)
        if 'meta' in row_copy and row_copy['meta']:
            for key, value in row_copy['meta'].items():
                if hasattr(value, '__fspath__'):  # Check if it's a Path-like object
                    row_copy['meta'][key] = str(value)
        serializable_rows.append(row_copy)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable_rows, f, indent=2)
    print(f"[OK] Saved fallback vector index (no embeddings): {path}")


async def build_vector_db(rows: List[Dict], out_dir: Path, provider: str = "local",
                         model: Optional[str] = None, api_key: Optional[str] = None) -> bool:
    """
    Build vector database with specified embedding provider.

    Args:
        rows: List of chunk dicts with id, text, meta
        out_dir: Output directory
        provider: Embedding provider (voyage, openai, cohere, local)
        model: Model name (optional, uses defaults)
        api_key: API key (optional, uses config/env)

    Returns:
        True if successful
    """
    try:
        import chromadb
    except Exception as e:
        print(f"ChromaDB not available: {e}")
        return False

    print(f"\n{'='*80}")
    print(f"BUILDING VECTOR DATABASE")
    print(f"{'='*80}")
    print(f"Provider: {provider}")
    print(f"Output: {out_dir}")
    print(f"Chunks: {len(rows)}")

    # Initialize embedding provider
    try:
        embedder = EmbeddingProvider(provider=provider, model=model, api_key=api_key)
    except Exception as e:
        print(f"Error: Could not initialize {provider}: {e}")
        return False

    # Prepare data
    texts = [row["text"] if isinstance(row, dict) and "text" in row else row.get("text", "") for row in rows]
    ids = [row["id"] if isinstance(row, dict) and "id" in row else row.get("id", f"chunk_{i}") for i, row in enumerate(rows)]
    metas = [row.get("meta", {}) for row in rows]

    # Generate embeddings
    print(f"\nGenerating embeddings...")
    try:
        embeddings = await embedder.embed_batch(texts)
        print(f"[OK] Generated {len(embeddings)} embeddings")
    except Exception as e:
        print(f"Error: Embedding generation failed: {e}")
        return False

    # Create ChromaDB collection
    print(f"\nCreating ChromaDB collection...")
    out_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(out_dir))

    # Delete old collection if exists
    try:
        client.delete_collection("td_unified")
        print("  Deleted old collection")
    except:
        pass

    coll = client.create_collection("td_unified")

    # Upsert in batches
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        coll.upsert(
            ids=ids[i:end],
            embeddings=embeddings[i:end],
            metadatas=metas[i:end],
            documents=texts[i:end]
        )
        print(f"  Upserted {end}/{len(ids)} items...")

    print(f"[OK] ChromaDB collection created: {len(ids)} items")
    print(f"[OK] Vector database saved to: {out_dir}")
    return True


async def main_async():
    """Async main function."""
    parser = argparse.ArgumentParser(description="Build unified vector index with enhanced embeddings.")
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS, help="Path to td_universal_parsed.json")
    parser.add_argument("--index-tsv", type=Path, default=DEFAULT_INDEX_TSV, help="Path to OPSnippets index.tsv")
    parser.add_argument("--snippets", type=Path, default=DEFAULT_SNIPPET_SEM, help="Path to snippet semantics")
    parser.add_argument("--out", type=Path, default=KB_ROOT / "vector_db", help="Output directory")
    parser.add_argument("--provider", type=str, default=None, help="Embedding provider (voyage, openai, cohere, local)")
    parser.add_argument("--model", type=str, default=None, help="Embedding model name")
    parser.add_argument("--api-key", type=str, default=None, help="API key for provider")
    parser.add_argument("--fallback-only", action="store_true", help="Skip embedding backend and just write vector_index.json")
    parser.add_argument("--hierarchical", action="store_true", default=True, help="Use hierarchical chunking (default: True)")
    parser.add_argument("--simple", action="store_true", help="Use simple chunking (legacy)")
    args = parser.parse_args()

    # Use config defaults if not specified
    provider = args.provider or SearchConfig.EMBEDDING_PROVIDER
    model = args.model or SearchConfig.EMBEDDING_MODEL

    print(f"\n{'='*80}")
    print(f"TOUCHDESIGNER VECTOR DATABASE BUILDER")
    print(f"{'='*80}")
    print(f"Embedding provider: {provider}")
    print(f"Embedding model: {model}")
    print(f"Chunking strategy: {'hierarchical' if not args.simple else 'simple'}")
    print(f"Using curator summaries: {args.index_tsv.exists()}")

    # Collect chunks
    rows: List[Dict] = []

    # 1. Collect wiki docs with hierarchical chunking
    if args.hierarchical and not args.simple:
        doc_chunks = collect_docs_hierarchical(args.docs)
        rows.extend(doc_chunks)
        print(f"  Wiki docs: {len(doc_chunks)} hierarchical chunks")
    else:
        print("  Skipping hierarchical wiki docs (use --hierarchical)")

    # 2. Collect snippet examples with curator summaries from index.tsv
    if args.snippets.exists():
        snippet_chunks = collect_snippets_with_summaries(args.snippets, args.index_tsv)
        rows.extend(snippet_chunks)

        # Count how many have curator summaries
        with_summaries = sum(1 for c in snippet_chunks if c.get('meta', {}).get('has_curator_summary'))
        print(f"  Snippets: {len(snippet_chunks)} examples ({with_summaries} with curator summaries)")

    # 3. Collect palette components (with enriched operator data if available)
    palette_chunks = collect_palette_chunks(
        DEFAULT_PALETTE_WIKI,
        DEFAULT_PALETTE_SEM,
        enriched_index_path=DEFAULT_PALETTE_ENRICHED
    )
    if palette_chunks:
        rows.extend(palette_chunks)
        print(f"  Palette: {len(palette_chunks)} components (enriched with operator lists)")

    if not rows:
        print("Error: No rows collected; nothing to index.")
        return

    print(f"\nTotal chunks: {len(rows)}")

    # Build vector database or fallback
    if args.fallback_only:
        save_fallback_index(rows, args.out)
        return

    success = await build_vector_db(rows, args.out, provider=provider, model=model, api_key=args.api_key)

    if not success:
        print("\nFalling back to JSON index...")
        save_fallback_index(rows, args.out)


def main():
    """Main entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
