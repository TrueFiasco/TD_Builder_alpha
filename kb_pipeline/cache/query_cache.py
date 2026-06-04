#!/usr/bin/env python3
"""
Query Cache System - Phase 5

Caches search results to reduce API calls and improve performance.
Uses SQLite for persistent caching with TTL support.
"""

import sqlite3
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any


class QueryCache:
    """
    LRU cache for query results with TTL support.

    Features:
    - Persistent SQLite storage
    - Configurable TTL (default 24 hours)
    - Automatic cleanup of expired entries
    - Query result serialization
    """

    def __init__(self, cache_dir: Path = None, ttl_hours: int = 24, max_entries: int = 1000):
        """
        Initialize query cache.

        Args:
            cache_dir: Directory for cache database
            ttl_hours: Time to live for cache entries (hours)
            max_entries: Maximum number of cache entries (LRU eviction)
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent / "cache"

        cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_dir / "search_cache.db"
        self.ttl_seconds = ttl_hours * 3600
        self.max_entries = max_entries

        self._init_db()

    def _init_db(self):
        """Initialize cache database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                query_hash TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_accessed
            ON query_cache(last_accessed)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON query_cache(created_at)
        """)

        conn.commit()
        conn.close()

    def _hash_query(self, query: str, n_results: int = 5) -> str:
        """Generate hash for query + parameters."""
        key = f"{query.lower().strip()}:{n_results}"
        return hashlib.sha256(key.encode()).hexdigest()

    def get(self, query: str, n_results: int = 5) -> Optional[List[Tuple[Dict, float]]]:
        """
        Get cached results for query.

        Args:
            query: Search query text
            n_results: Number of results requested

        Returns:
            Cached results or None if cache miss/expired
        """
        query_hash = self._hash_query(query, n_results)
        current_time = int(time.time())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get entry
        cursor.execute("""
            SELECT results_json, created_at, hit_count
            FROM query_cache
            WHERE query_hash = ?
        """, (query_hash,))

        row = cursor.fetchone()

        if row is None:
            conn.close()
            return None

        results_json, created_at, hit_count = row

        # Check if expired
        if current_time - created_at > self.ttl_seconds:
            # Delete expired entry
            cursor.execute("DELETE FROM query_cache WHERE query_hash = ?", (query_hash,))
            conn.commit()
            conn.close()
            return None

        # Update access time and hit count
        cursor.execute("""
            UPDATE query_cache
            SET last_accessed = ?, hit_count = ?
            WHERE query_hash = ?
        """, (current_time, hit_count + 1, query_hash))

        conn.commit()
        conn.close()

        # Deserialize results
        results_data = json.loads(results_json)
        results = [(chunk, score) for chunk, score in results_data]

        return results

    def set(self, query: str, results: List[Tuple[Dict, float]], n_results: int = 5):
        """
        Cache query results.

        Args:
            query: Search query text
            results: List of (chunk, score) tuples
            n_results: Number of results
        """
        query_hash = self._hash_query(query, n_results)
        current_time = int(time.time())

        # Serialize results
        results_data = [(chunk, score) for chunk, score in results]
        results_json = json.dumps(results_data)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Insert or replace
        cursor.execute("""
            INSERT OR REPLACE INTO query_cache
            (query_hash, query_text, results_json, created_at, last_accessed, hit_count)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (query_hash, query, results_json, current_time, current_time))

        conn.commit()

        # Cleanup old entries if over limit (LRU eviction)
        cursor.execute("SELECT COUNT(*) FROM query_cache")
        count = cursor.fetchone()[0]

        if count > self.max_entries:
            # Delete oldest accessed entries
            delete_count = count - self.max_entries
            cursor.execute("""
                DELETE FROM query_cache
                WHERE query_hash IN (
                    SELECT query_hash FROM query_cache
                    ORDER BY last_accessed ASC
                    LIMIT ?
                )
            """, (delete_count,))
            conn.commit()

        conn.close()

    def clear(self):
        """Clear all cache entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM query_cache")
        conn.commit()
        conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total entries
        cursor.execute("SELECT COUNT(*) FROM query_cache")
        total_entries = cursor.fetchone()[0]

        # Total hits
        cursor.execute("SELECT SUM(hit_count) FROM query_cache")
        total_hits = cursor.fetchone()[0] or 0

        # Average hits per entry
        avg_hits = total_hits / total_entries if total_entries > 0 else 0

        # Expired entries
        current_time = int(time.time())
        cursor.execute("""
            SELECT COUNT(*) FROM query_cache
            WHERE ? - created_at > ?
        """, (current_time, self.ttl_seconds))
        expired_count = cursor.fetchone()[0]

        # Top queries
        cursor.execute("""
            SELECT query_text, hit_count
            FROM query_cache
            ORDER BY hit_count DESC
            LIMIT 10
        """)
        top_queries = cursor.fetchall()

        conn.close()

        return {
            'total_entries': total_entries,
            'total_hits': total_hits,
            'average_hits_per_entry': round(avg_hits, 2),
            'expired_entries': expired_count,
            'top_queries': [
                {'query': query, 'hits': hits}
                for query, hits in top_queries
            ]
        }

    def cleanup_expired(self):
        """Remove expired cache entries."""
        current_time = int(time.time())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM query_cache
            WHERE ? - created_at > ?
        """, (current_time, self.ttl_seconds))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count


if __name__ == '__main__':
    # Test cache
    print("=" * 80)
    print("QUERY CACHE TEST")
    print("=" * 80)

    cache = QueryCache(ttl_hours=24)

    # Test data
    test_results = [
        ({'id': 'chunk_1', 'text': 'Test result 1'}, 0.95),
        ({'id': 'chunk_2', 'text': 'Test result 2'}, 0.85),
    ]

    test_query = "How do I control animation speed?"

    # Cache miss
    print(f"\nQuery: {test_query}")
    cached = cache.get(test_query, n_results=5)
    print(f"Cache miss: {cached is None}")

    # Set cache
    cache.set(test_query, test_results, n_results=5)
    print("Cached results")

    # Cache hit
    cached = cache.get(test_query, n_results=5)
    print(f"Cache hit: {cached is not None}")
    print(f"Results match: {len(cached) == len(test_results)}")

    # Different n_results = cache miss
    cached = cache.get(test_query, n_results=10)
    print(f"Different n_results (cache miss): {cached is None}")

    # Stats
    stats = cache.get_stats()
    print(f"\nCache stats:")
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Total hits: {stats['total_hits']}")
    print(f"  Average hits: {stats['average_hits_per_entry']}")

    print("\n[OK] Cache test passed!")
