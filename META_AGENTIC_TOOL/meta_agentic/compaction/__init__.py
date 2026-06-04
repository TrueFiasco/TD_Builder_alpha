# Compaction module for meta-agentic expertise system
# Converts JSONL event log to YAML state files

from .compact_expertise import (
    compact_events_to_state,
    refresh_legacy_yaml,
    append_event,
    EventSchema
)

__all__ = [
    'compact_events_to_state',
    'refresh_legacy_yaml',
    'append_event',
    'EventSchema'
]
