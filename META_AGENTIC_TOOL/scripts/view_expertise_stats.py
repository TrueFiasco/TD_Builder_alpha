"""
View Expertise Stats - Dashboard for Sweet 16 and Query Frequencies

Usage:
    python scripts/view_expertise_stats.py              # All stats
    python scripts/view_expertise_stats.py sweet16      # Just Sweet 16
    python scripts/view_expertise_stats.py queries      # Just query stats
    python scripts/view_expertise_stats.py events       # Recent expertise events
    python scripts/view_expertise_stats.py --test-type creative_workflow
"""

import sys
import json
import yaml
from pathlib import Path
from datetime import datetime

# Paths
META_AGENTIC_DIR = Path(__file__).parent.parent / "meta_agentic"
EXPERTISE_DIR = META_AGENTIC_DIR / "expertise"
HISTORY_DIR = META_AGENTIC_DIR / "history"


def print_header(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def view_sweet_16():
    """Display current Sweet 16 operators."""
    print_header("SWEET 16 OPERATORS (Compact Mode)")

    v2_path = EXPERTISE_DIR / "td_operators_v2.yaml"
    if not v2_path.exists():
        print("ERROR: td_operators_v2.yaml not found")
        return

    with open(v2_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    sweet_16 = data.get('sweet_16', {})
    index = data.get('operator_index', {})

    print(f"File: {v2_path.name}")
    print(f"Last updated: {data.get('last_updated', 'unknown')}")
    print()

    total_sweet = 0
    total_index = 0

    for family in ['CHOP', 'TOP', 'SOP', 'DAT', 'COMP', 'MAT', 'POP']:
        family_sweet = sweet_16.get(family, {})
        family_index = index.get(family, [])

        sweet_count = len(family_sweet)
        index_count = len(family_index) if isinstance(family_index, list) else 0

        total_sweet += sweet_count
        total_index += index_count

        print(f"\n{family} ({sweet_count} Sweet 16 / {index_count} total):")
        print("-" * 50)

        if family_sweet:
            ops = list(family_sweet.keys())
            # Print in rows of 4
            for i in range(0, len(ops), 4):
                row = ops[i:i+4]
                print("  " + ", ".join(row))

    print()
    print(f"TOTALS: {total_sweet} Sweet 16 operators / {total_index} indexed operators")
    print(f"Token reduction: ~87% (from ~60K to ~6K tokens)")


def view_query_stats(test_type: str = None):
    """Display query frequency statistics."""
    print_header("QUERY FREQUENCY STATISTICS")

    query_log = HISTORY_DIR / "operator_queries.jsonl"

    if not query_log.exists():
        print("No query log found yet.")
        print(f"Expected at: {query_log}")
        print()
        print("Queries will be logged when:")
        print("  - Claude Desktop uses td_assistant tool")
        print("  - Experts query non-Sweet-16 operators")
        print("  - Manual testing with QueryTracker")
        return

    # Load events
    events = []
    with open(query_log, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if test_type:
        events = [e for e in events if e.get('test_type') == test_type]

    if not events:
        print(f"No queries found" + (f" for test_type={test_type}" if test_type else ""))
        return

    print(f"Total queries: {len(events)}")

    # By test type
    by_test_type = {}
    for e in events:
        tt = e.get('test_type', 'unknown')
        by_test_type[tt] = by_test_type.get(tt, 0) + 1

    print("\nBy Test Type:")
    for tt, count in sorted(by_test_type.items(), key=lambda x: -x[1]):
        pct = count / len(events) * 100
        print(f"  {tt}: {count} ({pct:.1f}%)")

    # Sweet 16 hit rate
    sweet_hits = sum(1 for e in events if e.get('in_sweet_16'))
    print(f"\nSweet 16 hit rate: {sweet_hits}/{len(events)} ({sweet_hits/len(events)*100:.1f}%)")

    # Top non-Sweet-16 queries
    non_sweet = {}
    for e in events:
        if not e.get('in_sweet_16'):
            key = f"{e.get('family', '?')}:{e.get('operator', '?')}"
            non_sweet[key] = non_sweet.get(key, 0) + 1

    if non_sweet:
        print("\nTop Non-Sweet-16 Queries (candidates for promotion):")
        for op, count in sorted(non_sweet.items(), key=lambda x: -x[1])[:15]:
            pct = count / len(events) * 100
            marker = " *CANDIDATE*" if pct > 10 else ""
            print(f"  {op}: {count} ({pct:.1f}%){marker}")


def view_expertise_events():
    """Display recent expertise events from JSONL log."""
    print_header("RECENT EXPERTISE EVENTS")

    events_log = HISTORY_DIR / "expertise_events.jsonl"

    if not events_log.exists():
        print(f"No events log found at: {events_log}")
        return

    events = []
    with open(events_log, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not events:
        print("No events found")
        return

    print(f"Total events: {len(events)}")
    print()

    # Show last 10 events
    print("Last 10 events:")
    print("-" * 70)

    for event in events[-10:]:
        ts = event.get('ts', 'unknown')[:19]
        agent = event.get('agent_id', 'unknown')
        domain = event.get('domain', 'unknown')
        status = event.get('status', 'unknown')
        notes = event.get('notes', '')[:50]

        print(f"  [{ts}] {agent} | {domain} | {status}")
        if notes:
            print(f"    {notes}...")

    # By domain summary
    print()
    print("Events by Domain:")
    by_domain = {}
    for e in events:
        d = e.get('domain', 'unknown')
        by_domain[d] = by_domain.get(d, 0) + 1

    for domain, count in sorted(by_domain.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count}")

    # By agent summary
    print()
    print("Events by Agent:")
    by_agent = {}
    for e in events:
        a = e.get('agent_id', 'unknown')
        by_agent[a] = by_agent.get(a, 0) + 1

    for agent, count in sorted(by_agent.items(), key=lambda x: -x[1]):
        print(f"  {agent}: {count}")


def view_all():
    """Display all stats."""
    view_sweet_16()
    view_query_stats()
    view_expertise_events()


def main():
    args = sys.argv[1:]

    test_type = None
    for i, arg in enumerate(args):
        if arg == "--test-type" and i + 1 < len(args):
            test_type = args[i + 1]
            args = args[:i] + args[i+2:]
            break

    if not args:
        view_all()
    elif args[0] == "sweet16":
        view_sweet_16()
    elif args[0] == "queries":
        view_query_stats(test_type)
    elif args[0] == "events":
        view_expertise_events()
    else:
        print(f"Unknown command: {args[0]}")
        print("Usage: python view_expertise_stats.py [sweet16|queries|events] [--test-type TYPE]")


if __name__ == "__main__":
    main()
