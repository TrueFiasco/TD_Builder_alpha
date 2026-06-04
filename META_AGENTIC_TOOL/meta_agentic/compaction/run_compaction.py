"""
Convenience CLI to compact expertise events -> state and optionally refresh legacy YAML.

Usage:
    python run_compaction.py [--no-refresh]
    # Override paths if needed:
    python run_compaction.py --events meta_agentic/history/expertise_events.jsonl --state meta_agentic/meta/expertise_state.yaml
"""
from pathlib import Path
import argparse
import sys

# Allow imports from sibling package
sys.path.insert(0, str(Path(__file__).parent.parent))

from compaction import compact_events_to_state, refresh_legacy_yaml  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact expertise event log to YAML state (and optionally refresh legacy YAML).")
    parser.add_argument("--no-refresh", action="store_true", help="Skip refreshing legacy expertise/*.yaml views.")
    parser.add_argument("--events", type=Path, help="Path to expertise_events.jsonl (optional override).")
    parser.add_argument("--state", type=Path, help="Path to expertise_state.yaml (optional override).")
    args = parser.parse_args()

    success, msg = compact_events_to_state(events_path=args.events, state_path=args.state)
    print(f"[compact] {msg}")
    if not success:
        return 1

    if args.no_refresh:
        return 0

    refresh_success, refresh_msg = refresh_legacy_yaml(state_path=args.state)
    print(f"[refresh] {refresh_msg}")
    return 0 if refresh_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
