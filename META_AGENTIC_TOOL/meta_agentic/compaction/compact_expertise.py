"""
Compaction script for expertise JSONL -> YAML state.

This script:
1. Reads append-only event log (expertise_events.jsonl)
2. Materializes into expertise_state.yaml
3. Optionally refreshes legacy expertise/*.yaml files

Per INTEROP_AND_POLICY.md:
- Event log is the source of truth for all expertise updates
- YAML files are working-set views refreshed via compaction
- Both Claude and OpenAI agents can work with this system
"""

import json
import yaml
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field, asdict
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from concurrency.file_lock import FileLock


# Event schema version
SCHEMA_VERSION = "1.0"


@dataclass
class EventSchema:
    """
    Schema for expertise event log entries.

    Required fields per INTEROP_AND_POLICY.md:
    - id: Unique event ID
    - ts: ISO timestamp
    - agent_id: Which agent made this update
    - domain: Which domain (operators, patterns, params, problems, etc.)
    - inputs: What triggered this update
    - outputs: What was learned/changed
    - evidence: List of evidence pointers
    - metrics: Any quality metrics
    - status: success/failed/partial
    - notes: Human-readable notes
    - schema_version: Schema version for forward compat
    """
    id: str
    ts: str
    agent_id: str
    domain: str
    inputs: dict
    outputs: dict
    evidence: list  # [{source_path, chunk_id, excerpt_hash, td_version}, ...]
    metrics: dict
    status: str  # success, failed, partial
    notes: str
    schema_version: str = SCHEMA_VERSION

    # Optional fields
    td_version: Optional[str] = None
    confidence: Optional[float] = None
    problem_ids: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'EventSchema':
        # Handle missing optional fields
        d.setdefault('td_version', None)
        d.setdefault('confidence', None)
        d.setdefault('problem_ids', [])
        d.setdefault('schema_version', SCHEMA_VERSION)
        return cls(**d)

    def validate(self) -> tuple[bool, str]:
        """Validate event meets requirements."""
        # Required fields
        if not self.id:
            return False, "Missing event id"
        if not self.ts:
            return False, "Missing timestamp"
        if not self.agent_id:
            return False, "Missing agent_id"
        if not self.domain:
            return False, "Missing domain"

        # Evidence requirements for pattern claims
        if self.domain in ['patterns', 'recipes']:
            if len(self.evidence) < 3:
                return False, f"Pattern claims need >=3 evidence pointers, got {len(self.evidence)}"

        # Evidence must have required fields
        for ev in self.evidence:
            if 'source_path' not in ev:
                return False, "Evidence missing source_path"

        return True, "OK"


def generate_event_id() -> str:
    """Generate unique event ID."""
    import uuid
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    short_uuid = uuid.uuid4().hex[:8]
    return f"EVT-{timestamp}-{short_uuid}"


def append_event(
    event: EventSchema,
    events_path: Path = None
) -> tuple[bool, str]:
    """
    Append an event to the JSONL log.

    Args:
        event: Event to append
        events_path: Path to events file (default: history/expertise_events.jsonl)

    Returns:
        (success, message)
    """
    if events_path is None:
        events_path = Path(__file__).parent.parent / 'history' / 'expertise_events.jsonl'

    # Validate event
    valid, msg = event.validate()
    if not valid:
        return False, f"Event validation failed: {msg}"

    # Ensure directory exists
    events_path.parent.mkdir(parents=True, exist_ok=True)

    # Append with locking
    lock = FileLock(events_path)
    if not lock.acquire():
        return False, "Could not acquire lock on events file"

    try:
        with open(events_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event.to_dict()) + '\n')
        return True, f"Event {event.id} appended"
    except Exception as e:
        return False, f"Failed to append event: {e}"
    finally:
        lock.release()


def load_events(events_path: Path = None) -> list[EventSchema]:
    """Load all events from JSONL log."""
    if events_path is None:
        events_path = Path(__file__).parent.parent / 'history' / 'expertise_events.jsonl'

    if not events_path.exists():
        return []

    events = []
    with open(events_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    events.append(EventSchema.from_dict(data))
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"Warning: Skipping malformed event line: {e}")

    return events


def compact_events_to_state(
    events_path: Path = None,
    state_path: Path = None
) -> tuple[bool, str]:
    """
    Compact event log into materialized expertise_state.yaml.

    This is idempotent - can be run multiple times safely.

    Args:
        events_path: Path to events JSONL
        state_path: Path to output state YAML

    Returns:
        (success, message)
    """
    if events_path is None:
        events_path = Path(__file__).parent.parent / 'history' / 'expertise_events.jsonl'
    if state_path is None:
        state_path = Path(__file__).parent.parent / 'meta' / 'expertise_state.yaml'

    # Load all events
    events = load_events(events_path)

    if not events:
        return True, "No events to compact"

    # Initialize state structure
    state = {
        'schema_version': SCHEMA_VERSION,
        'last_compacted': datetime.now().isoformat(),
        'event_count': len(events),
        'checksum': None,  # Will compute after building

        # Per-domain sections (TD-specific)
        'operators': {},
        'patterns': {},
        'parameters': {},
        'problems': {},
        'recipes': {},
        'file_formats': {},
        'network_building': {},
        'td_glsl': {},

        # Creative orchestration domains
        'creative': {},
        'cg': {},
        'critique': {},
        'orchestration': {}
    }

    # Process events in order (chronological)
    for event in sorted(events, key=lambda e: e.ts):
        if event.status == 'failed':
            continue  # Skip failed events

        domain = event.domain
        outputs = event.outputs

        if domain not in state:
            state[domain] = {}

        # Merge outputs into state
        # Strategy: later events override earlier ones
        _deep_merge(state[domain], outputs, event)

    # Compute checksum of state
    state_json = json.dumps(state, sort_keys=True)
    state['checksum'] = hashlib.sha256(state_json.encode()).hexdigest()[:16]

    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Write state with locking
    lock = FileLock(state_path)
    if not lock.acquire():
        return False, "Could not acquire lock on state file"

    try:
        with open(state_path, 'w', encoding='utf-8') as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True, f"Compacted {len(events)} events to {state_path}"
    except Exception as e:
        return False, f"Failed to write state: {e}"
    finally:
        lock.release()


def _deep_merge(target: dict, source: dict, event: EventSchema):
    """
    Deep merge source into target, with event metadata.
    Later events override earlier ones.
    """
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value, event)
        else:
            # Store value with metadata
            if isinstance(value, dict):
                value['_last_updated'] = event.ts
                value['_updated_by'] = event.agent_id
                if event.confidence:
                    value['_confidence'] = event.confidence
            target[key] = value


def refresh_legacy_yaml(
    state_path: Path = None,
    expertise_dir: Path = None
) -> tuple[bool, str]:
    """
    Refresh legacy expertise/*.yaml files from expertise_state.yaml.

    This keeps the working-set YAML files in sync with compacted state.

    Args:
        state_path: Path to expertise_state.yaml
        expertise_dir: Path to expertise/ directory

    Returns:
        (success, message)
    """
    if state_path is None:
        state_path = Path(__file__).parent.parent / 'meta' / 'expertise_state.yaml'
    if expertise_dir is None:
        expertise_dir = Path(__file__).parent.parent / 'expertise'

    if not state_path.exists():
        return False, "No expertise_state.yaml to refresh from"

    # Load state
    with open(state_path, 'r', encoding='utf-8') as f:
        state = yaml.safe_load(f)

    if not state:
        return False, "Empty state file"

    # Map state sections to legacy files
    file_mapping = {
        # TD-specific files
        'operators': 'td_operators.yaml',
        'patterns': 'td_network_patterns.yaml',
        'parameters': 'td_parameters.yaml',
        'problems': 'td_problems.yaml',
        'file_formats': 'td_file_formats.yaml',
        'network_building': 'td_network_building.yaml',
        'td_glsl': 'td_glsl.yaml',

        # Creative orchestration files
        'creative': 'creative_vision.yaml',
        'cg': 'cg_concepts.yaml',
        'critique': 'critique_patterns.yaml'
        # Note: 'orchestration' domain logs workflow state, not expertise
    }

    refreshed = []
    for section, filename in file_mapping.items():
        if section not in state or not state[section]:
            continue

        file_path = expertise_dir / filename
        lock = FileLock(file_path)

        if not lock.acquire():
            print(f"Warning: Could not lock {filename}, skipping")
            continue

        try:
            # Load existing file to preserve structure
            existing = {}
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing = yaml.safe_load(f) or {}

            # Merge state into existing (state takes precedence for content,
            # but preserve existing schema structure)
            merged = _merge_into_legacy(existing, state[section], section)

            # Update metadata
            merged['last_updated'] = datetime.now().isoformat()
            merged['update_count'] = merged.get('update_count', 0) + 1
            merged['refreshed_from_state'] = state_path.name
            merged['state_checksum'] = state.get('checksum', 'unknown')

            # Write
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(merged, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            refreshed.append(filename)
        except Exception as e:
            print(f"Warning: Failed to refresh {filename}: {e}")
        finally:
            lock.release()

    return True, f"Refreshed {len(refreshed)} files: {', '.join(refreshed)}"


def _merge_into_legacy(existing: dict, state_section: dict, section_name: str) -> dict:
    """
    Merge compacted state section into legacy file structure.
    Preserves existing schema structure while updating content.
    """
    result = existing.copy()

    # Section-specific merge logic
    if section_name == 'operators':
        if 'operators' not in result:
            result['operators'] = {}
        for family, ops in state_section.items():
            if family.startswith('_'):
                continue
            if family not in result['operators']:
                result['operators'][family] = {}
            for op_type, op_data in ops.items():
                if op_type.startswith('_'):
                    continue
                result['operators'][family][op_type] = op_data

    elif section_name == 'patterns':
        if 'workflows' not in result:
            result['workflows'] = {}
        for pattern_name, pattern_data in state_section.items():
            if pattern_name.startswith('_'):
                continue
            result['workflows'][pattern_name] = pattern_data

    elif section_name == 'problems':
        if 'problems' not in result:
            result['problems'] = {}
        for prob_id, prob_data in state_section.items():
            if prob_id.startswith('_'):
                continue
            result['problems'][prob_id] = prob_data

    else:
        # Generic merge for other sections
        for key, value in state_section.items():
            if key.startswith('_'):
                continue
            result[key] = value

    return result


def run_compaction():
    """Run compaction as script."""
    print("Starting expertise compaction...")

    # Compact events to state
    success, msg = compact_events_to_state()
    print(f"Compact: {msg}")

    if not success:
        print("Compaction failed, not refreshing YAML files")
        return 1

    # Refresh legacy YAML files
    success, msg = refresh_legacy_yaml()
    print(f"Refresh: {msg}")

    return 0 if success else 1


if __name__ == '__main__':
    import sys
    sys.exit(run_compaction())
