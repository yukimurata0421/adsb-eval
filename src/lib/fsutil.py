#!/usr/bin/env python3
"""
lib/fsutil.py

Filesystem utilities used across adsb-eval.

Design goals:
- Small, dependency-free helpers
- Safe defaults (mkdir -p behavior)
- Provide compatibility functions expected by other lib modules:
  - ensure_dir_for_file(path)
  - get_file_age_sec(path)
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional, Union


PathLike = Union[str, os.PathLike]


def ensure_dir(path: PathLike) -> None:
    """
    Ensure a directory exists.
    - If 'path' is "", no-op.
    """
    p = str(path)
    if not p:
        return
    Path(p).mkdir(parents=True, exist_ok=True)


def ensure_dir_for_file(path: PathLike) -> None:
    """
    Ensure parent directory exists for a file path.
    Example:
      ensure_dir_for_file("/a/b/c.jsonl") -> mkdir -p /a/b
    """
    p = str(path)
    parent = os.path.dirname(p)
    if parent:
        Path(parent).mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: PathLike, text: str, *, encoding: str = "utf-8") -> None:
    """
    Atomic write (write temp file then replace).
    """
    p = Path(str(path))
    ensure_dir_for_file(p)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(str(tmp), str(p))


def safe_read_text(path: PathLike, *, encoding: str = "utf-8") -> Optional[str]:
    """
    Read text; return None on any failure.
    """
    try:
        return Path(str(path)).read_text(encoding=encoding)
    except Exception:
        return None


def get_file_age_sec(path: PathLike) -> Optional[int]:
    """
    Return file age seconds from mtime.
    - None if missing/unreadable
    """
    try:
        st = os.stat(str(path))
    except Exception:
        return None
    return max(0, int(time.time() - st.st_mtime))


def file_exists(path: PathLike) -> bool:
    try:
        return Path(str(path)).exists()
    except Exception:
        return False
