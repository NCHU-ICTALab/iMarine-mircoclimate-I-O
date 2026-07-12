from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def atomic_write_json(
    path: str | Path,
    payload: dict[str, Any],
    *,
    retries: int = 20,
    retry_delay_seconds: float = 0.05,
) -> None:
    """Write JSON via a unique temp file and atomic replace.

    Windows can reject replace operations when concurrent requests compete for
    the same path, so each writer gets its own temp file and transient replace
    failures are retried briefly.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target_key = str(target.resolve(strict=False))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if _existing_content_matches(target, serialized):
        return
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp_path = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)

        with _path_lock(target_key):
            attempts = max(1, retries + 1)
            for attempt in range(1, attempts + 1):
                try:
                    os.replace(temp_path, target)
                    replaced = True
                    return
                except (PermissionError, FileExistsError, OSError):
                    if attempt >= attempts:
                        raise
                    time.sleep(min(retry_delay_seconds * attempt, 0.5))
    finally:
        if not replaced and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _path_lock(target_key: str) -> threading.Lock:
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(target_key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[target_key] = lock
        return lock


def _existing_content_matches(target: Path, serialized: str) -> bool:
    if not target.exists():
        return False
    try:
        return target.read_text(encoding="utf-8") == serialized
    except OSError:
        return False
