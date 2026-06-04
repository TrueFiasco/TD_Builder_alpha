"""
Conflict resolution for concurrent expertise file updates.

When multiple agents try to update the same expertise simultaneously,
this module determines which update wins or how to merge them.

Resolution strategies:
1. Higher confidence wins
2. More examples wins
3. Try merge if compatible
4. More recent wins (fallback)
"""

from datetime import datetime
from typing import Optional, Any
import copy


class ConflictResolver:
    """
    Resolve conflicts when multiple agents update the same expertise.
    """

    # Minimum confidence difference to prefer one over another
    CONFIDENCE_THRESHOLD = 0.1

    # Minimum example count difference to prefer one over another
    EXAMPLE_COUNT_THRESHOLD = 2

    def resolve(self, existing: dict, incoming: dict) -> dict:
        """
        Resolve conflict between existing and incoming updates.

        Args:
            existing: The current value in expertise file (with validation metadata)
            incoming: The new value being proposed (with validation metadata)

        Returns:
            The winning version or merged version
        """
        # Extract validation metadata
        existing_validation = existing.get('validation', {})
        incoming_validation = incoming.get('validation', {})

        existing_confidence = existing_validation.get('confidence', 0)
        incoming_confidence = incoming_validation.get('confidence', 0)

        # Strategy 1: Higher confidence wins (if significant difference)
        confidence_diff = abs(incoming_confidence - existing_confidence)
        if confidence_diff > self.CONFIDENCE_THRESHOLD:
            winner = incoming if incoming_confidence > existing_confidence else existing
            return self._annotate_winner(winner, 'confidence')

        # Strategy 2: More examples wins (if significant difference)
        existing_count = existing_validation.get('example_count', 0)
        incoming_count = incoming_validation.get('example_count', 0)

        count_diff = abs(incoming_count - existing_count)
        if count_diff > self.EXAMPLE_COUNT_THRESHOLD:
            winner = incoming if incoming_count > existing_count else existing
            return self._annotate_winner(winner, 'example_count')

        # Strategy 3: Try to merge if compatible
        merged = self._try_merge(existing, incoming)
        if merged:
            return self._annotate_winner(merged, 'merged')

        # Strategy 4: More recent wins (fallback)
        existing_time = existing_validation.get('timestamp', '')
        incoming_time = incoming_validation.get('timestamp', '')

        winner = incoming if incoming_time > existing_time else existing
        return self._annotate_winner(winner, 'recency')

    def _try_merge(self, a: dict, b: dict) -> Optional[dict]:
        """
        Try to merge two compatible updates.

        Only merges if:
        - Both have 'content' of same type
        - Content can be meaningfully combined
        """
        a_content = a.get('content')
        b_content = b.get('content')

        # Can only merge if types match
        if type(a_content) != type(b_content):
            return None

        if isinstance(a_content, dict):
            return self._merge_dicts(a, b)

        if isinstance(a_content, list):
            return self._merge_lists(a, b)

        # Can't merge scalar values
        return None

    def _merge_dicts(self, a: dict, b: dict) -> Optional[dict]:
        """Merge two dict-content updates."""
        a_content = a.get('content', {})
        b_content = b.get('content', {})
        a_validation = a.get('validation', {})
        b_validation = b.get('validation', {})

        # Check for conflicting keys with different values
        for key in set(a_content.keys()) & set(b_content.keys()):
            if a_content[key] != b_content[key]:
                # Conflict on a key - can't merge without choosing
                # Use confidence to pick the value
                if a_validation.get('confidence', 0) >= b_validation.get('confidence', 0):
                    # Keep a's value for this key
                    pass
                else:
                    a_content = {**a_content, key: b_content[key]}

        # Merge all keys
        merged_content = {**a_content, **b_content}

        # Combine validation metadata
        merged_validation = {
            'source': f"merged:{a_validation.get('source', 'unknown')}+{b_validation.get('source', 'unknown')}",
            'confidence': (a_validation.get('confidence', 0) + b_validation.get('confidence', 0)) / 2,
            'example_count': a_validation.get('example_count', 0) + b_validation.get('example_count', 0),
            'timestamp': datetime.now().isoformat(),
            'merge_note': 'Auto-merged from concurrent updates'
        }

        return {
            'content': merged_content,
            'validation': merged_validation
        }

    def _merge_lists(self, a: dict, b: dict) -> Optional[dict]:
        """Merge two list-content updates."""
        a_content = a.get('content', [])
        b_content = b.get('content', [])
        a_validation = a.get('validation', {})
        b_validation = b.get('validation', {})

        # Combine lists, avoiding duplicates
        merged_content = list(a_content)
        for item in b_content:
            if item not in merged_content:
                merged_content.append(item)

        merged_validation = {
            'source': f"merged:{a_validation.get('source', 'unknown')}+{b_validation.get('source', 'unknown')}",
            'confidence': (a_validation.get('confidence', 0) + b_validation.get('confidence', 0)) / 2,
            'example_count': a_validation.get('example_count', 0) + b_validation.get('example_count', 0),
            'timestamp': datetime.now().isoformat(),
            'merge_note': 'Auto-merged from concurrent updates'
        }

        return {
            'content': merged_content,
            'validation': merged_validation
        }

    def _annotate_winner(self, winner: dict, resolution_method: str) -> dict:
        """Annotate the winning update with how it was chosen."""
        result = copy.deepcopy(winner)
        if 'validation' not in result:
            result['validation'] = {}
        result['validation']['resolution_method'] = resolution_method
        result['validation']['resolved_at'] = datetime.now().isoformat()
        return result


class ConflictDetector:
    """
    Detect conflicts between expertise versions.
    """

    def has_conflict(self, existing: Any, incoming: Any) -> bool:
        """
        Check if there's a conflict between existing and incoming content.

        A conflict exists when:
        - Types differ
        - Same keys have different values (for dicts)
        - Semantic meaning differs (requires validation)
        """
        if type(existing) != type(incoming):
            return True

        if isinstance(existing, dict):
            # Conflict if same keys with different values
            for key in set(existing.keys()) & set(incoming.keys()):
                if existing[key] != incoming[key]:
                    return True

        if isinstance(existing, list):
            # Lists don't conflict - they can be merged
            return False

        # Scalar values conflict if different
        return existing != incoming

    def describe_conflict(self, existing: Any, incoming: Any) -> str:
        """Describe the nature of the conflict."""
        if type(existing) != type(incoming):
            return f"Type mismatch: {type(existing).__name__} vs {type(incoming).__name__}"

        if isinstance(existing, dict):
            conflicts = []
            for key in set(existing.keys()) & set(incoming.keys()):
                if existing[key] != incoming[key]:
                    conflicts.append(f"Key '{key}': {existing[key]} vs {incoming[key]}")
            return f"Dict value conflicts: {', '.join(conflicts)}"

        return f"Value conflict: {existing} vs {incoming}"
