"""
Enhanced search module for MCP server.
Provides backward-compatible adapter with improved embeddings and caching.
Also exposes a module-level lazy singleton (`get_search_adapter()`) so the
inactive MCP server and the strategy runner share one adapter instance,
one ChromaDB connection, and one embedding model load.
"""

from .unified_search import UnifiedSearchAdapter

__all__ = ['UnifiedSearchAdapter', 'get_search_adapter']

# Module-level lazy singleton. Initialised on first call so import is cheap.
_adapter = None


def get_search_adapter():
    """Return a process-wide UnifiedSearchAdapter pointing at the merged store.

    Lazy: the adapter (and its ChromaDB client + embedding model) only loads
    on first call, then is cached for the life of the process. Callers that
    only need the singleton in a few code paths pay nothing at import time.

    Path resolution: vector_db_merged sits next to this module's parent
    (META_AGENTIC_TOOL/data/vector_db_merged). If that store is missing the
    underlying UnifiedSearchAdapter raises; callers should catch and fall
    back to a degraded mode rather than crashing.
    """
    global _adapter
    if _adapter is None:
        from pathlib import Path
        base = Path(__file__).parent.parent
        _adapter = UnifiedSearchAdapter(
            graph_path=str(base / "data" / "td_knowledge_graph_enhanced.gpickle"),
            vectordb_path=str(base / "data" / "vector_db_merged"),
            use_legacy=False,
        )
    return _adapter
