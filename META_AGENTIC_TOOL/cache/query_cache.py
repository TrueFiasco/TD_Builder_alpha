"""
Query Cache

SQLite-based caching for search queries to reduce API calls and improve performance.
"""

import sqlite3
import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any


class QueryCache:
    """
    Simple SQLite-based query cache with TTL support.

    Caches search results to:
    - Reduce API embedding costs
    - Improve response time for repeated queries
    - Track popular queries for optimization
    """

    def __init__(self, db_path: Optional[Path] = None, ttl_seconds: int = 86400):
        """
        Initialize query cache.

        Args:
            db_path: Path to SQLite database file
            ttl_seconds: Time-to-live for cached entries (default: 24 hours)
        """
        self.db_path = db_path or Path("kb_pipeline/cache/search_cache.db")
        self.ttl_seconds = ttl_seconds

        # Ensure cache directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create cache table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS query_cache (
                query_hash TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                n_results INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 0,
                last_accessed INTEGER NOT NULL
            )
        ''')

        # Create index on timestamp for cleanup
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON query_cache(created_at)
        ''')

        conn.commit()
        conn.close()

    def _get_query_hash(self, query: str, n_results: int) -> str:
        """Generate hash for query + parameters."""
        key = f"{query}::{n_results}"
        return hashlib.sha256(key.encode()).hexdigest()

    def get(self, query: str, n_results: int) -> Optional[Dict[str, Any]]:
        """
        Get cached result for query.

        Args:
            query: Search query
            n_results: Number of results requested

        Returns:
            Cached result dict or None if not found/expired
        """
        query_hash = self._get_query_hash(query, n_results)
        current_time = int(time.time())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT result_json, created_at, hit_count
            FROM query_cache
            WHERE query_hash = ?
        ''', (query_hash,))

        row = cursor.fetchone()

        if row:
            result_json, created_at, hit_count = row

            # Check if expired
            if current_time - created_at > self.ttl_seconds:
                # Delete expired entry
                cursor.execute('DELETE FROM query_cache WHERE query_hash = ?', (query_hash,))
                conn.commit()
                conn.close()
                return None

            # Update hit count and last accessed
            cursor.execute('''
                UPDATE query_cache
                SET hit_count = ?, last_accessed = ?
                WHERE query_hash = ?
            ''', (hit_count + 1, current_time, query_hash))

            conn.commit()
            conn.close()

            # Return cached result
            return json.loads(result_json)

        conn.close()
        return None

    def set(self, query: str, n_results: int, result: Dict[str, Any]):
        """
        Cache query result.

        Args:
            query: Search query
            n_results: Number of results
            result: Result dict to cache
        """
        query_hash = self._get_query_hash(query, n_results)
        current_time = int(time.time())
        result_json = json.dumps(result)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO query_cache
            (query_hash, query, n_results, result_json, created_at, hit_count, last_accessed)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        ''', (query_hash, query, n_results, result_json, current_time, current_time))

        conn.commit()
        conn.close()

    def clear(self):
        """Clear all cached entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM query_cache')
        conn.commit()
        conn.close()

    def cleanup_expired(self):
        """Remove expired cache entries."""
        current_time = int(time.time())
        cutoff_time = current_time - self.ttl_seconds

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM query_cache WHERE created_at < ?', (cutoff_time,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total entries
        cursor.execute('SELECT COUNT(*) FROM query_cache')
        total_entries = cursor.fetchone()[0]

        # Total hits
        cursor.execute('SELECT SUM(hit_count) FROM query_cache')
        total_hits = cursor.fetchone()[0] or 0

        # Top queries
        cursor.execute('''
            SELECT query, hit_count
            FROM query_cache
            ORDER BY hit_count DESC
            LIMIT 10
        ''')
        top_queries = [{'query': row[0], 'hits': row[1]} for row in cursor.fetchall()]

        conn.close()

        # Calculate hit rate (approximate)
        total_queries = total_entries + total_hits
        hit_rate = (total_hits / total_queries * 100) if total_queries > 0 else 0

        return {
            'total_entries': total_entries,
            'total_hits': total_hits,
            'hit_rate_percent': round(hit_rate, 2),
            'top_queries': top_queries
        }


# Example usage
if __name__ == '__main__':
    cache = QueryCache()

    # Test caching
    print("Testing query cache...")

    # Set a cache entry
    test_query = "What are POPs in TouchDesigner?"
    test_result = {
        'query': test_query,
        'semantic_results': [{'content': 'Test result'}],
        'relationships': {}
    }

    cache.set(test_query, 5, test_result)
    print(f"✓ Cached query: {test_query}")

    # Get from cache
    cached = cache.get(test_query, 5)
    if cached:
        print(f"✓ Retrieved from cache: {cached['query']}")

    # Get stats
    stats = cache.get_stats()
    print(f"\nCache stats:")
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Total hits: {stats['total_hits']}")
    print(f"  Hit rate: {stats['hit_rate_percent']}%")
