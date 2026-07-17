#!/usr/bin/env python3
"""
Semantic Search for TouchDesigner Documentation
Search through all TD docs using natural language queries
"""

from sentence_transformers import SentenceTransformer
import chromadb
import contextlib
import sqlite3
from typing import List, Dict, Optional
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# KF1 — chromadb create-on-open guard.
#
# chromadb has NO read-only open mode: PersistentClient is create-if-missing
# at every construction site, and its rust bindings hold the sqlite file open
# read-write for the life of the process even for pure reads (a filesystem
# read-only attribute breaks every consumer — empirically refuted). So any
# consumer that boots against an absent/empty store silently MANUFACTURES a
# ~188KB bare stub where the real store belongs — the confirmed root cause of
# all 3 vector_db kills on the dev machine. Probe with STDLIB sqlite first
# (read-only URI, deterministically closed) and refuse loudly.
#
# Contract mirrors scripts/fetch_vector_db.py::_vector_db_doc_count (and
# check_deps.py; mcp_server._vector_db_ro_doc_count is the boot-side mirror) —
# keep them in sync:
#   None  -> chroma.sqlite3 does not exist (nothing to open)
#   0     -> file exists but the collection is missing/empty/unreadable
#   N > 0 -> healthy: N embedding rows in the named collection
# ---------------------------------------------------------------------------
class ChromaStoreUnavailable(RuntimeError):
    """The Chroma store is absent/empty/unreadable and MUST NOT be opened with
    chromadb (create-if-missing would manufacture a bare stub in its place)."""


def chroma_store_doc_count(vdb_path, collection: str = "td_unified"):
    """Embedding-row count of `collection`, via a stdlib READ-ONLY probe of
    ``<vdb_path>/chroma.sqlite3`` — deliberately NOT chromadb (see above)."""
    db = Path(vdb_path) / "chroma.sqlite3"
    if not db.exists():
        return None
    try:
        # closing(): a bare `with sqlite3.connect(...)` only ends the
        # transaction — it does NOT release the file handle.
        with contextlib.closing(
                sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM embeddings e"
                " JOIN segments s ON e.segment_id = s.id"
                " WHERE s.collection ="
                "   (SELECT id FROM collections WHERE name = ?)",
                (collection,),
            ).fetchone()[0]
    except Exception:
        return 0


def open_chroma_or_refuse(vdb_path, collection: str = "td_unified",
                          min_docs: int = 1):
    """(client, collection) for an EXISTING healthy store; raises
    ChromaStoreUnavailable otherwise. NEVER creates files — the read-only
    probe runs before anything chromadb-shaped touches the path."""
    n = chroma_store_doc_count(vdb_path, collection)
    if n is None:
        raise ChromaStoreUnavailable(
            f"no Chroma store at {vdb_path} (chroma.sqlite3 missing) — refusing "
            f"to open: a chromadb open would CREATE a bare stub store there. "
            f"Fetch or rebuild the KB first (scripts/fetch_vector_db.py).")
    if n < min_docs:
        raise ChromaStoreUnavailable(
            f"Chroma store at {vdb_path} holds {n} document(s) in "
            f"'{collection}' (need >= {min_docs}) — refusing to serve an "
            f"empty/foreign store. Fetch or rebuild the KB first.")
    client = chromadb.PersistentClient(path=str(vdb_path))
    return client, client.get_collection(collection)

# Phase-3 embedder A/B: the embedder + regime (model id, L2-normalize, query
# instruction prefix) are NOT hardcoded — they are resolved PER-KB so that
# pointing the adapter at a different KB (--kb KB_bge / KB_minilm_norm / …) selects
# the matching query-time embedder automatically. Resolution order:
#   explicit env EMBEDDING_MODEL  >  <kb_root>/manifest.json  >  search_config.json  >  default
# A KB built by kb_build/reembed.py ALWAYS records embedding_model + normalize +
# query_prefix in its manifest, so its regime is authoritative. Legacy KBs that
# predate Phase-3 (no embedding_model in the manifest) fall back to the shipped
# MiniLM / un-normalized regime with a warning (the historical safe default).
_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _derive_regime(model_id: str):
    """(normalize, query_prefix) inferred from a model id — a safety net used only
    when the KB manifest does not record them explicitly."""
    m = (model_id or "").lower()
    if "bge" in m:
        return True, _BGE_QUERY_PREFIX
    if "e5" in m:
        return True, "query: "
    if "gte" in m:
        return True, ""
    return False, ""            # MiniLM and unknowns: shipped un-normalized regime


def _resolve_embedding(kb_root: Path) -> dict:
    """Resolve (model_id, normalize, query_prefix) for the KB at kb_root."""
    manifest = {}
    mpath = kb_root / "manifest.json"
    if mpath.exists():
        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"[search_docs] WARNING: unreadable manifest {mpath} ({e})")

    env_model = os.environ.get("EMBEDDING_MODEL")
    man_model = manifest.get("embedding_model")

    # mismatch guardrail: an explicit env model that disagrees with the KB's own
    # manifest means the query embedder would not match the indexed vectors.
    # HF model ids are case-insensitive in practice ("all-MiniLM-L6-v2" ==
    # "all-minilm-l6-v2"), so compare casefolded: a case-only difference must
    # not hard-fail the boot.
    if (env_model and man_model and env_model.casefold() != man_model.casefold()
            and not _truthy(os.environ.get("EMBEDDING_ALLOW_MISMATCH"))):
        raise RuntimeError(
            f"EMBEDDING_MODEL={env_model!r} disagrees with the KB manifest "
            f"({man_model!r}) at {kb_root}. The query embedder must match the "
            f"indexed vectors. Set EMBEDDING_ALLOW_MISMATCH=1 only if you mean to.")

    if env_model:
        model_id = env_model
    elif man_model:
        model_id = man_model
    else:
        # No KB self-declaration. Honor the config-json indirection, else default.
        cfg_model = None
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from config import SearchConfig          # search_config.json / env
            cfg_model = SearchConfig.EMBEDDING_MODEL
        except Exception:
            cfg_model = None
        model_id = cfg_model or _DEFAULT_MODEL
        if (kb_root / "vector_db").exists():
            print(f"[search_docs] WARNING: {kb_root} has a vector_db but its manifest does not "
                  f"declare embedding_model; assuming {model_id!r} (legacy regime). Phase-3 KBs "
                  f"must record embedding_model — rebuild via reembed.py if this is one.")

    # normalize + query_prefix: env override > manifest > model-id-derived default
    d_norm, d_prefix = _derive_regime(model_id)
    if os.environ.get("EMBEDDING_NORMALIZE") is not None:
        normalize = _truthy(os.environ.get("EMBEDDING_NORMALIZE"))
    elif "normalize" in manifest:
        normalize = bool(manifest.get("normalize"))
    else:
        normalize = d_norm
    if os.environ.get("EMBEDDING_QUERY_PREFIX") is not None:
        query_prefix = os.environ.get("EMBEDDING_QUERY_PREFIX")
    elif "query_prefix" in manifest:
        query_prefix = manifest.get("query_prefix") or ""
    else:
        query_prefix = d_prefix
    return {"model_id": model_id, "normalize": normalize, "query_prefix": query_prefix}


class _QueryEncoder:
    """Wraps a SentenceTransformer so QUERY embeddings get the model's regime
    (instruction prefix + L2-normalization) while leaving the underlying model
    otherwise untouched. retrieval_stack.py borrows ``TDDocSearch.model`` and calls
    ``.encode(query, …)``; search_docs.py's own ``search()`` does the same — so this
    single wrapper covers BOTH query paths. Passages are embedded at BUILD time by a
    raw model (kb_build), so they never receive the query prefix. For the shipped
    MiniLM / un-normalized regime (prefix='' , normalize=False) this is a
    pass-through → byte-identical to the pre-Phase-3 behavior."""

    def __init__(self, model, query_prefix: str = "", normalize: bool = False):
        self._model = model
        self._prefix = query_prefix or ""
        self._normalize = bool(normalize)

    def encode(self, text, **kw):
        if self._normalize:
            kw.setdefault("normalize_embeddings", True)   # never collide with a caller's kwarg
        if self._prefix:
            text = self._prefix + text if isinstance(text, str) else [self._prefix + t for t in text]
        return self._model.encode(text, **kw)

    def __getattr__(self, name):
        return getattr(self._model, name)   # delegate every non-overridden attribute


class TDDocSearch:
    """Semantic search for TouchDesigner documentation"""

    def __init__(self, vectordb_path: Optional[str] = None):
        # Default to the merged store next to this file so standalone use works
        # without configuration. Callers can override (e.g. mcp_server.py does).
        if vectordb_path is None:
            vectordb_path = str(Path(__file__).parent / "data" / "vector_db_merged")
        print("🔍 Loading TouchDesigner documentation search...")

        # Resolve the embedder + regime from the KB this adapter points at.
        kb_root = Path(vectordb_path).parent
        regime = _resolve_embedding(kb_root)
        self.embedding_model = regime["model_id"]
        self.embedding_normalize = regime["normalize"]
        self.embedding_query_prefix = regime["query_prefix"]
        print(f"  Embedder: {self.embedding_model} (normalize={self.embedding_normalize}, "
              f"query_prefix={self.embedding_query_prefix!r})")

        # Connect to Chroma FIRST, through the KF1 guard — refusing an absent/
        # empty store must happen before the (heavy) embedding model loads,
        # and a plain PersistentClient here would CREATE the store it fails
        # to find (the vector_db-kill root cause).
        _client, self.collection = open_chroma_or_refuse(
            Path(vectordb_path), "td_unified")

        # Load model, wrapped so QUERIES get the regime (prefix + normalize). The
        # wrapper is a pass-through for the shipped MiniLM/un-normalized control.
        self.model = _QueryEncoder(SentenceTransformer(self.embedding_model),
                                   query_prefix=self.embedding_query_prefix,
                                   normalize=self.embedding_normalize)

        # Exposed for the server's KB health gate: 0 documents means every
        # semantic query returns empty results, which must read as unhealthy.
        self.doc_count = self.collection.count()
        print(f"✓ Ready! Loaded {self.doc_count:,} documentation chunks\n")

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
