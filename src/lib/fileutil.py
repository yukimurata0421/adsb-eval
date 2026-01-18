from __future__ import annotations

import os
import time
from typing import Optional


def ensure_dir_for_file(path: str) -> None:
    """
    Ensure parent directory exists for a file path.
    Used by lockutil/jsonl writers.
    """
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def get_file_age_sec(path: str) -> Optional[int]:
    """
    Return file age seconds from mtime. None if missing/unreadable.
    """
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        return None
    return max(0, int(time.time() - mtime))

