from __future__ import annotations

import os
from typing import Optional

from .fsutil import ensure_dir_for_file

try:
    import fcntl
except Exception:
    fcntl = None  # type: ignore


def acquire_lock(lock_path: str) -> Optional[int]:
    """Return fd on success, None if already locked. If fcntl missing, return -1 (no-op lock)."""
    if fcntl is None:
        return -1
    ensure_dir_for_file(lock_path)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except Exception:
        os.close(fd)
        return None


def release_lock(fd: Optional[int]) -> None:
    if fd in (None, -1):
        return
    try:
        os.close(fd)
    except Exception:
        pass
