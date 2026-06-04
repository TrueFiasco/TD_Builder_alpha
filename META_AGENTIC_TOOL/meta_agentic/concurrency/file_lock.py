"""
Cross-process file locking for expertise files.

Works across:
- Claude Code instances
- Claude API agents
- OpenAI agents
- Any process that respects .lock files

Usage:
    with FileLock('expertise/td_operators.yaml') as lock:
        expertise = load_yaml('expertise/td_operators.yaml')
        # ... modify expertise ...
        save_yaml('expertise/td_operators.yaml', expertise)
"""

import os
import time
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


class FileLock:
    """
    Cross-process file locking using lock files.

    This is designed to work across different LLM runtimes that may not
    share memory but can all read/write to the filesystem.
    """

    LOCK_TIMEOUT = 30  # seconds before lock considered stale
    RETRY_DELAY = 0.5  # seconds between acquisition attempts
    MAX_RETRIES = 60   # 30 seconds total wait time

    def __init__(self, file_path: str | Path):
        """
        Initialize lock for a specific file.

        Args:
            file_path: Path to the file to lock (not the lock file itself)
        """
        self.file_path = Path(file_path)
        self.lock_path = self.file_path.with_suffix(self.file_path.suffix + '.lock')
        self.lock_holder: Optional[str] = None
        self._locked = False

    def acquire(self, holder_id: str = None) -> bool:
        """
        Acquire lock for file.

        Args:
            holder_id: Unique ID for lock holder (auto-generated if None)

        Returns:
            True if lock acquired, False otherwise
        """
        if holder_id is None:
            holder_id = self._generate_holder_id()

        for attempt in range(self.MAX_RETRIES):
            # Check for existing lock
            if self.lock_path.exists():
                lock_info = self._read_lock()

                if lock_info:
                    lock_time = datetime.fromisoformat(lock_info['timestamp'])
                    age = datetime.now() - lock_time

                    if age > timedelta(seconds=self.LOCK_TIMEOUT):
                        # Stale lock - remove it
                        try:
                            self.lock_path.unlink()
                        except FileNotFoundError:
                            pass  # Already removed by another process
                    else:
                        # Valid lock held by someone else - wait
                        time.sleep(self.RETRY_DELAY)
                        continue
                else:
                    # Corrupted lock file - remove it
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass

            # Try to acquire lock
            try:
                lock_info = {
                    'holder_id': holder_id,
                    'timestamp': datetime.now().isoformat(),
                    'file': str(self.file_path),
                    'pid': os.getpid()
                }

                # Create lock file - use 'x' mode for atomic creation
                # This will fail if file already exists
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, json.dumps(lock_info).encode())
                finally:
                    os.close(fd)

                self.lock_holder = holder_id
                self._locked = True
                return True

            except FileExistsError:
                # Someone else created the lock first
                time.sleep(self.RETRY_DELAY)
                continue
            except OSError as e:
                # Other filesystem error
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
                    continue
                raise

        return False

    def release(self) -> bool:
        """
        Release the lock.

        Returns:
            True if lock was released, False if we didn't hold it
        """
        if not self._locked:
            return False

        if self.lock_path.exists():
            lock_info = self._read_lock()

            # Only release if we hold the lock
            if lock_info and lock_info.get('holder_id') == self.lock_holder:
                try:
                    self.lock_path.unlink()
                    self.lock_holder = None
                    self._locked = False
                    return True
                except FileNotFoundError:
                    # Already removed
                    self._locked = False
                    return True

        self._locked = False
        return False

    def is_locked(self) -> bool:
        """Check if the file is currently locked (by anyone)."""
        if not self.lock_path.exists():
            return False

        lock_info = self._read_lock()
        if not lock_info:
            return False

        # Check if lock is stale
        try:
            lock_time = datetime.fromisoformat(lock_info['timestamp'])
            age = datetime.now() - lock_time
            return age <= timedelta(seconds=self.LOCK_TIMEOUT)
        except (KeyError, ValueError):
            return False

    def _read_lock(self) -> Optional[dict]:
        """Read lock file info."""
        try:
            with open(self.lock_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, IOError):
            return None

    def _generate_holder_id(self) -> str:
        """Generate unique holder ID."""
        return f"{os.getpid()}-{uuid.uuid4().hex[:8]}-{int(time.time())}"

    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise TimeoutError(
                f"Could not acquire lock for {self.file_path} "
                f"after {self.MAX_RETRIES * self.RETRY_DELAY} seconds"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False  # Don't suppress exceptions


class ReadWriteLock:
    """
    Read-write lock for expertise files.

    Allows multiple readers OR a single writer.
    Useful for scenarios where reads are frequent but writes are rare.
    """

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.write_lock = FileLock(file_path)
        self.reader_count_path = self.file_path.with_suffix(self.file_path.suffix + '.readers')

    def acquire_read(self) -> bool:
        """Acquire read lock (multiple readers allowed)."""
        # For simplicity, this implementation just checks write lock isn't held
        # A full implementation would track reader count
        if self.write_lock.is_locked():
            return False
        return True

    def release_read(self):
        """Release read lock."""
        pass  # No-op for simple implementation

    def acquire_write(self) -> bool:
        """Acquire write lock (exclusive)."""
        return self.write_lock.acquire()

    def release_write(self):
        """Release write lock."""
        self.write_lock.release()
