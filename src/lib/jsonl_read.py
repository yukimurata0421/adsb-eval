from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def safe_load_json_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    try:
        v = json.loads(line)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def tail_jsonl(path: str, max_lines: int) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []

    lines: List[str] = []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                lines.append(line)
        lines = lines[-max_lines:]
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for ln in lines:
        obj = safe_load_json_line(ln)
        if obj is not None:
            out.append(obj)
    return out


def read_last_record(path: str, max_lines: int = 300) -> Optional[Dict[str, Any]]:
    records = tail_jsonl(path, max_lines=max_lines)
    if not records:
        return None
    # last parsed record
    return records[-1]
