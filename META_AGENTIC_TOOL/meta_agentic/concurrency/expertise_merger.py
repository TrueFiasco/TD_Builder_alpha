"""
Safely merge concurrent updates to expertise files.

This module handles the complete workflow of:
1. Validating updates before applying
2. Acquiring file locks
3. Resolving conflicts
4. Applying updates atomically
5. Creating snapshots for rollback
"""

import yaml
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

from .file_lock import FileLock
from .conflict_resolver import ConflictResolver, ConflictDetector


def load_yaml(file_path: Path) -> dict:
    """Load YAML file, returning empty dict if doesn't exist."""
    if not file_path.exists():
        return {}
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def save_yaml(file_path: Path, data: dict):
    """Save dict to YAML file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


class ExpertiseMerger:
    """
    Safely merge concurrent updates to expertise files.
    """

    def __init__(self, expertise_dir: Path = None):
        """
        Initialize merger.

        Args:
            expertise_dir: Base directory for expertise files
        """
        if expertise_dir is None:
            expertise_dir = Path(__file__).parent.parent / 'expertise'
        self.expertise_dir = Path(expertise_dir)
        self.history_dir = Path(__file__).parent.parent / 'history' / 'snapshots'

        self.conflict_resolver = ConflictResolver()
        self.conflict_detector = ConflictDetector()

    def apply_update(
        self,
        file_name: str,
        update: dict,
        validate_func: callable = None
    ) -> tuple[bool, str]:
        """
        Apply an update to an expertise file with locking and conflict resolution.

        Args:
            file_name: Name of expertise file (e.g., 'td_operators.yaml')
            update: Update to apply, containing:
                - path: Dot-separated path to update location (e.g., 'operators.CHOP.analyze')
                - content: New content to set
                - validation: Validation metadata
            validate_func: Optional function to validate update before applying

        Returns:
            Tuple of (success: bool, message: str)
        """
        file_path = self.expertise_dir / file_name

        # Validate update structure
        if 'path' not in update and 'content' not in update:
            return False, "Update must have 'path' and/or 'content'"

        # Optional external validation
        if validate_func:
            is_valid, reason = validate_func(update)
            if not is_valid:
                return False, f"Validation failed: {reason}"

        # Acquire lock
        lock = FileLock(file_path)
        if not lock.acquire():
            return False, f"Could not acquire lock for {file_name}"

        try:
            # Load current expertise
            current = load_yaml(file_path)

            # Navigate to update path
            path = update.get('path', '')
            path_parts = path.split('.') if path else []

            # Get existing value at path
            existing = self._get_at_path(current, path_parts)

            # Check for conflicts
            if existing is not None:
                if self.conflict_detector.has_conflict(existing, update.get('content')):
                    # Resolve conflict
                    existing_with_meta = {
                        'content': existing,
                        'validation': {'timestamp': current.get('last_updated', '')}
                    }
                    resolved = self.conflict_resolver.resolve(existing_with_meta, update)
                    update = resolved

            # Create snapshot before modifying
            self._create_snapshot(file_path, current)

            # Apply update
            self._set_at_path(current, path_parts, update.get('content'))

            # Update metadata
            current['last_updated'] = datetime.now().isoformat()
            current['update_count'] = current.get('update_count', 0) + 1

            # Save
            save_yaml(file_path, current)

            return True, "Update applied successfully"

        except Exception as e:
            return False, f"Error applying update: {str(e)}"

        finally:
            lock.release()

    def append_to_list(
        self,
        file_name: str,
        path: str,
        item: Any
    ) -> tuple[bool, str]:
        """
        Append an item to a list in an expertise file.

        Args:
            file_name: Name of expertise file
            path: Dot-separated path to list
            item: Item to append

        Returns:
            Tuple of (success: bool, message: str)
        """
        file_path = self.expertise_dir / file_name

        lock = FileLock(file_path)
        if not lock.acquire():
            return False, f"Could not acquire lock for {file_name}"

        try:
            current = load_yaml(file_path)
            path_parts = path.split('.') if path else []

            # Get existing list
            existing = self._get_at_path(current, path_parts)

            if existing is None:
                existing = []
            elif not isinstance(existing, list):
                return False, f"Path {path} is not a list"

            # Check for duplicates (simple equality check)
            if item not in existing:
                existing.append(item)
                self._set_at_path(current, path_parts, existing)

                current['last_updated'] = datetime.now().isoformat()
                current['update_count'] = current.get('update_count', 0) + 1

                save_yaml(file_path, current)
                return True, "Item appended"
            else:
                return True, "Item already exists (no change)"

        except Exception as e:
            return False, f"Error appending: {str(e)}"

        finally:
            lock.release()

    def increment_counter(
        self,
        file_name: str,
        path: str,
        amount: int = 1
    ) -> tuple[bool, str]:
        """
        Increment a counter in an expertise file.

        Args:
            file_name: Name of expertise file
            path: Dot-separated path to counter
            amount: Amount to increment by (default 1)

        Returns:
            Tuple of (success: bool, message: str)
        """
        file_path = self.expertise_dir / file_name

        lock = FileLock(file_path)
        if not lock.acquire():
            return False, f"Could not acquire lock for {file_name}"

        try:
            current = load_yaml(file_path)
            path_parts = path.split('.') if path else []

            existing = self._get_at_path(current, path_parts) or 0
            self._set_at_path(current, path_parts, existing + amount)

            current['last_updated'] = datetime.now().isoformat()
            current['update_count'] = current.get('update_count', 0) + 1

            save_yaml(file_path, current)
            return True, f"Counter incremented to {existing + amount}"

        except Exception as e:
            return False, f"Error incrementing: {str(e)}"

        finally:
            lock.release()

    def _get_at_path(self, data: dict, path_parts: list) -> Any:
        """Get value at nested path."""
        current = data
        for part in path_parts:
            if not part:
                continue
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _set_at_path(self, data: dict, path_parts: list, value: Any):
        """Set value at nested path, creating intermediate dicts as needed."""
        if not path_parts or not path_parts[0]:
            # Root level update
            if isinstance(value, dict):
                data.update(value)
            return

        current = data
        for part in path_parts[:-1]:
            if not part:
                continue
            if part not in current:
                current[part] = {}
            current = current[part]

        if path_parts[-1]:
            current[path_parts[-1]] = value

    def _create_snapshot(self, file_path: Path, data: dict):
        """Create a timestamped snapshot of the expertise file."""
        self.history_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshot_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        snapshot_path = self.history_dir / snapshot_name

        save_yaml(snapshot_path, data)

        # Keep only last 20 snapshots per file
        self._cleanup_old_snapshots(file_path.stem, keep=20)

    def _cleanup_old_snapshots(self, file_stem: str, keep: int = 20):
        """Remove old snapshots, keeping only the most recent ones."""
        pattern = f"{file_stem}_*.yaml"
        snapshots = sorted(self.history_dir.glob(pattern), reverse=True)

        for old_snapshot in snapshots[keep:]:
            old_snapshot.unlink()


class ExpertiseRollback:
    """
    Rollback expertise files to previous versions.
    """

    def __init__(self, expertise_dir: Path = None):
        if expertise_dir is None:
            expertise_dir = Path(__file__).parent.parent / 'expertise'
        self.expertise_dir = Path(expertise_dir)
        self.history_dir = Path(__file__).parent.parent / 'history' / 'snapshots'

    def list_snapshots(self, file_name: str) -> list[dict]:
        """List available snapshots for a file."""
        file_stem = Path(file_name).stem
        pattern = f"{file_stem}_*.yaml"
        snapshots = sorted(self.history_dir.glob(pattern), reverse=True)

        return [
            {
                'path': str(s),
                'timestamp': s.stem.split('_')[-2] + '_' + s.stem.split('_')[-1],
                'size': s.stat().st_size
            }
            for s in snapshots
        ]

    def rollback_to(self, file_name: str, snapshot_path: str) -> tuple[bool, str]:
        """
        Rollback an expertise file to a specific snapshot.

        Args:
            file_name: Name of expertise file to rollback
            snapshot_path: Path to snapshot file

        Returns:
            Tuple of (success: bool, message: str)
        """
        file_path = self.expertise_dir / file_name
        snapshot = Path(snapshot_path)

        if not snapshot.exists():
            return False, f"Snapshot not found: {snapshot_path}"

        lock = FileLock(file_path)
        if not lock.acquire():
            return False, f"Could not acquire lock for {file_name}"

        try:
            # Create backup of current before rollback
            current = load_yaml(file_path)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"{file_path.stem}_pre_rollback_{timestamp}{file_path.suffix}"
            backup_path = self.history_dir / backup_name
            save_yaml(backup_path, current)

            # Copy snapshot to expertise file
            shutil.copy2(snapshot, file_path)

            return True, f"Rolled back {file_name} to {snapshot.name}"

        except Exception as e:
            return False, f"Rollback failed: {str(e)}"

        finally:
            lock.release()
