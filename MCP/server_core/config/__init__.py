"""
Configuration management for MCP search system.
Loads settings from search_config.json and environment variables.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Load JSON configuration
config_path = Path(__file__).parent / "search_config.json"
if config_path.exists():
    with open(config_path, 'r') as f:
        _CONFIG = json.load(f)
else:
    _CONFIG = {}


class SearchConfig:
    """Configuration for search and embedding system."""

    # Embedding Provider
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", _CONFIG.get("embedding_provider", "local"))
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", _CONFIG.get("embedding_model", "all-MiniLM-L6-v2"))

    # API Keys
    VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")

    # Paths
    VECTOR_DB_PATH = Path(
        os.getenv("UNIFIED_VECTORDB_PATH", _CONFIG.get("vector_db_path", "C:/TD_Projects/kb_pipeline/vector_db"))
    )
    GRAPH_DATA_PATH = Path(
        os.getenv("GRAPH_DATA_PATH", _CONFIG.get("graph_path", "C:/TD_Projects/kb_pipeline/graph/td_knowledge_graph_merged.gpickle"))
    )

    # Fallback options
    FALLBACK_TO_LOCAL = os.getenv("FALLBACK_TO_LOCAL", str(_CONFIG.get("fallback_to_local", True))).lower() == "true"

    # Performance settings
    MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_API_CALLS", _CONFIG.get("performance", {}).get("max_concurrent_api_calls", 5)))
    QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT_MS", _CONFIG.get("performance", {}).get("query_timeout_ms", 5000)))
    PARALLEL_QUERIES = _CONFIG.get("performance", {}).get("parallel_queries", True)

    # Cache settings
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", str(_CONFIG.get("cache_enabled", True))).lower() == "true"
    CACHE_TTL = int(os.getenv("CACHE_TTL_HOURS", _CONFIG.get("cache_ttl_hours", 24))) * 3600
    CACHE_PATH = Path(__file__).parent.parent / "cache" / "search_cache.db"

    # Search settings
    DEFAULT_N_RESULTS = _CONFIG.get("search", {}).get("default_n_results", 5)
    VECTOR_SEARCH_MULTIPLIER = _CONFIG.get("search", {}).get("vector_search_multiplier", 4)
    RERANK_ENABLED = _CONFIG.get("search", {}).get("rerank_enabled", False)
    QUERY_EXPANSION_ENABLED = _CONFIG.get("search", {}).get("query_expansion_enabled", True)

    # Metadata settings
    SEMANTIC_TAGS_ENABLED = _CONFIG.get("metadata", {}).get("semantic_tags_enabled", True)
    POPULARITY_TRACKING_ENABLED = _CONFIG.get("metadata", {}).get("popularity_tracking_enabled", True)

    @classmethod
    def validate(cls) -> tuple[bool, Optional[str]]:
        """
        Validate configuration settings.
        Returns (is_valid, error_message).
        """
        # Check if embedding provider is valid
        if cls.EMBEDDING_PROVIDER not in ["voyage", "openai", "cohere", "local"]:
            return False, f"Invalid embedding provider: {cls.EMBEDDING_PROVIDER}"

        # Check API keys for non-local providers
        if cls.EMBEDDING_PROVIDER == "voyage" and not cls.VOYAGE_API_KEY:
            if not cls.FALLBACK_TO_LOCAL:
                return False, "VOYAGE_API_KEY not set and fallback disabled"
        elif cls.EMBEDDING_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            if not cls.FALLBACK_TO_LOCAL:
                return False, "OPENAI_API_KEY not set and fallback disabled"
        elif cls.EMBEDDING_PROVIDER == "cohere" and not cls.COHERE_API_KEY:
            if not cls.FALLBACK_TO_LOCAL:
                return False, "COHERE_API_KEY not set and fallback disabled"

        return True, None

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """Get a summary of current configuration."""
        return {
            "embedding_provider": cls.EMBEDDING_PROVIDER,
            "embedding_model": cls.EMBEDDING_MODEL,
            "vector_db_path": str(cls.VECTOR_DB_PATH),
            "graph_path": str(cls.GRAPH_DATA_PATH),
            "fallback_to_local": cls.FALLBACK_TO_LOCAL,
            "cache_enabled": cls.CACHE_ENABLED,
            "parallel_queries": cls.PARALLEL_QUERIES,
        }


# Validate configuration on import
is_valid, error = SearchConfig.validate()
if not is_valid:
    print(f"Warning: Configuration validation failed: {error}")
    if SearchConfig.FALLBACK_TO_LOCAL:
        print("Will fall back to local embeddings (all-MiniLM-L6-v2)")
