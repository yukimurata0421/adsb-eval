from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from .jsonx import json_dumps_strict


def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _try_parse_json_line(line: bytes) -> bool:
    line = line.strip()
    if not line:
        return True
    try:
        json.loads(line.decode("utf-8"))
        return True
    except Exception:
        return False


def repair_jsonl_tail(path: str, read_bytes: int = 64 * 1024) -> bool:
    """
    Repair truncated last line (power loss etc.).
    Strategy:
      - Read last read_bytes
      - Scan backwards for last line that parses as JSON
      - Truncate file to end of that line
    Returns:
      True if truncated (repaired), False otherwise.
    """
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    if size <= 0:
        return False

    rb = min(read_bytes, size)
    with open(path, "rb") as f:
        f.seek(size - rb)
        buf = f.read(rb)

    lines = buf.splitlines(True)  # keepends
    if not lines:
        return False

    good_end: Optional[int] = None
    offset_from_tail = 0
    for i in range(len(lines) - 1, -1, -1):
        offset_from_tail += len(lines[i])
        ln = lines[i].strip()
        if not ln:
            continue
        if _try_parse_json_line(lines[i]):
            good_end = size - (offset_from_tail - len(lines[i]))
            break

    if good_end is None or good_end == size:
        return False

    with open(path, "rb+") as f:
        f.truncate(good_end)
        f.flush()
        os.fsync(f.fileno())
    return True


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    """
    Crash-safe JSONL append:
      - Ensure directory
      - Repair tail (IMPORTANT: always before append)
      - Append + fsync
    """
    ensure_dir(path)
    repair_jsonl_tail(path)
    line = (json_dumps_strict(record) + "\n").encode("utf-8")
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
