"""
Query Tracker - Logs operator queries with test type context.

This module tracks which operators are queried during different test types
to inform Sweet 16 evolution.

Test Types:
- basic_build: Simple instruction-based builds
- creative_workflow: Full creative → CG → TD Designer pipeline
- claude_desktop: Interactions from Claude Desktop MCP
- manual_test: Manual testing/debugging

Usage:
    from meta_agentic.history.query_tracker import QueryTracker

    tracker = QueryTracker(test_type="creative_workflow")
    tracker.log_query("choptoTOP", "TOP", source="td_designer")
    tracker.log_query("analyze", "CHOP", source="claude_desktop")

    # View stats
    stats = tracker.get_stats()
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional
from dataclasses import dataclass, asdict
import threading

# File paths
HISTORY_DIR = Path(__file__).parent
QUERY_LOG_PATH = HISTORY_DIR / "operator_queries.jsonl"
STATS_CACHE_PATH = HISTORY_DIR / "query_stats.json"

# Test types
TestType = Literal[
    "basic_build",      # Simple instruction builds
    "creative_workflow", # Full creative pipeline
    "claude_desktop",    # Claude Desktop MCP interactions
    "manual_test",       # Manual testing
    "a_b_test_full",     # A/B test with full expertise
    "a_b_test_compact"   # A/B test with compact expertise
]


@dataclass
class QueryEvent:
    """Single operator query event."""
    timestamp: str
    operator: str
    family: str
    test_type: TestType
    source: str  # Which expert/tool made the query
    in_sweet_16: bool
    session_id: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class QueryTracker:
    """
    Tracks operator queries for Sweet 16 evolution.

    Thread-safe for concurrent access.
    """

    # Sweet 16 operators (from td_operators_v2.yaml)
    SWEET_16 = {
        'CHOP': {'noise', 'math', 'null', 'constant', 'analyze', 'filter', 'select', 'merge',
                 'count', 'speed', 'logic', 'limit', 'lag', 'trigger', 'expression', 'audiodevicein'},
        'TOP': {'noise', 'level', 'composite', 'blur', 'transform', 'null', 'ramp', 'constant',
                'feedback', 'render', 'moviefilein', 'text', 'resolution', 'crop', 'flip', 'over'},
        'SOP': {'grid', 'sphere', 'box', 'line', 'circle', 'transform', 'merge', 'null',
                'copy', 'sort', 'delete', 'facet', 'skin', 'sweep', 'carve', 'convert'},
        'DAT': {'text', 'table', 'select', 'null', 'execute', 'evaluate', 'script', 'info',
                'error', 'webclient', 'udp', 'osc', 'chopto', 'sopto', 'constant', 'perform'},
        'COMP': {'base', 'container', 'geometry', 'camera', 'light', 'animation', 'geo', 'replicator'},
        'MAT': {'constant', 'pbr', 'phong', 'wireframe'},
        'POP': {'forcepop', 'field', 'feedback', 'render', 'particlegpu', 'instancepop', 'copypop', 'choptopop'}
    }

    def __init__(self, test_type: TestType = "manual_test", session_id: str = None):
        self.test_type = test_type
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._lock = threading.Lock()

    def is_sweet_16(self, operator: str, family: str) -> bool:
        """Check if operator is in Sweet 16."""
        family_ops = self.SWEET_16.get(family.upper(), set())
        return operator.lower() in family_ops

    def log_query(
        self,
        operator: str,
        family: str,
        source: str = "unknown",
        notes: str = None
    ) -> QueryEvent:
        """
        Log an operator query.

        Args:
            operator: Operator name (e.g., "choptoTOP", "analyze")
            family: Operator family (CHOP, TOP, SOP, DAT, COMP, MAT, POP)
            source: What made the query (e.g., "td_designer", "claude_desktop")
            notes: Optional notes

        Returns:
            The created QueryEvent
        """
        event = QueryEvent(
            timestamp=datetime.now().isoformat(),
            operator=operator.lower(),
            family=family.upper(),
            test_type=self.test_type,
            source=source,
            in_sweet_16=self.is_sweet_16(operator, family),
            session_id=self.session_id,
            notes=notes
        )

        # Append to log file
        with self._lock:
            QUERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(QUERY_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event.to_dict()) + '\n')

        return event

    @staticmethod
    def load_all_queries() -> list[QueryEvent]:
        """Load all query events from log."""
        if not QUERY_LOG_PATH.exists():
            return []

        events = []
        with open(QUERY_LOG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        events.append(QueryEvent(**data))
                    except (json.JSONDecodeError, TypeError):
                        pass
        return events

    @staticmethod
    def get_stats(test_type: Optional[TestType] = None) -> dict:
        """
        Get query statistics.

        Args:
            test_type: Filter by test type (None = all)

        Returns:
            {
                "total_queries": N,
                "by_test_type": {"basic_build": N, ...},
                "by_family": {"CHOP": N, ...},
                "sweet_16_hits": N,
                "non_sweet_16_queries": [
                    {"operator": "choptoTOP", "family": "TOP", "count": N, "candidate": True/False}
                ],
                "candidate_promotions": [...]  # Operators with >90% frequency
            }
        """
        events = QueryTracker.load_all_queries()

        if test_type:
            events = [e for e in events if e.test_type == test_type]

        if not events:
            return {"total_queries": 0, "by_test_type": {}, "by_family": {},
                    "sweet_16_hits": 0, "non_sweet_16_queries": [], "candidate_promotions": []}

        # Count by test type
        by_test_type = {}
        for e in events:
            by_test_type[e.test_type] = by_test_type.get(e.test_type, 0) + 1

        # Count by family
        by_family = {}
        for e in events:
            by_family[e.family] = by_family.get(e.family, 0) + 1

        # Count Sweet 16 hits
        sweet_16_hits = sum(1 for e in events if e.in_sweet_16)

        # Count non-Sweet-16 queries
        non_sweet_16 = {}
        for e in events:
            if not e.in_sweet_16:
                key = (e.operator, e.family)
                non_sweet_16[key] = non_sweet_16.get(key, 0) + 1

        non_sweet_16_list = [
            {"operator": op, "family": fam, "count": count,
             "candidate": count / len(events) > 0.1}  # >10% frequency = candidate
            for (op, fam), count in sorted(non_sweet_16.items(), key=lambda x: -x[1])
        ]

        # Identify promotion candidates (>90% of max query count)
        if non_sweet_16_list:
            max_count = non_sweet_16_list[0]["count"]
            threshold = max_count * 0.9
            candidates = [op for op in non_sweet_16_list if op["count"] >= threshold]
        else:
            candidates = []

        return {
            "total_queries": len(events),
            "by_test_type": by_test_type,
            "by_family": by_family,
            "sweet_16_hits": sweet_16_hits,
            "sweet_16_hit_rate": sweet_16_hits / len(events) if events else 0,
            "non_sweet_16_queries": non_sweet_16_list[:20],  # Top 20
            "candidate_promotions": candidates
        }


def view_stats(test_type: Optional[str] = None):
    """Print stats to console."""
    stats = QueryTracker.get_stats(test_type)

    print("=" * 60)
    print("OPERATOR QUERY STATISTICS")
    print("=" * 60)
    print(f"Total queries: {stats['total_queries']}")
    print(f"Sweet 16 hit rate: {stats['sweet_16_hit_rate']:.1%}")
    print()

    print("By Test Type:")
    for tt, count in sorted(stats['by_test_type'].items()):
        print(f"  {tt}: {count}")
    print()

    print("By Family:")
    for fam, count in sorted(stats['by_family'].items()):
        print(f"  {fam}: {count}")
    print()

    if stats['non_sweet_16_queries']:
        print("Non-Sweet-16 Queries (candidates for promotion):")
        for op in stats['non_sweet_16_queries'][:10]:
            marker = " *CANDIDATE*" if op['candidate'] else ""
            print(f"  {op['family']}:{op['operator']}: {op['count']}{marker}")
    print()

    if stats['candidate_promotions']:
        print("PROMOTION CANDIDATES (>90% threshold):")
        for op in stats['candidate_promotions']:
            print(f"  → {op['family']}:{op['operator']} ({op['count']} queries)")


# Global tracker instance (for convenience)
_global_tracker: Optional[QueryTracker] = None


def get_tracker(test_type: TestType = "manual_test") -> QueryTracker:
    """Get or create global tracker."""
    global _global_tracker
    if _global_tracker is None or _global_tracker.test_type != test_type:
        _global_tracker = QueryTracker(test_type=test_type)
    return _global_tracker


def log_query(operator: str, family: str, source: str = "unknown", test_type: TestType = "manual_test"):
    """Convenience function to log a query."""
    tracker = get_tracker(test_type)
    return tracker.log_query(operator, family, source)


if __name__ == "__main__":
    import sys
    test_type = sys.argv[1] if len(sys.argv) > 1 else None
    view_stats(test_type)
