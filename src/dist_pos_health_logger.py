#!/usr/bin/env python3
# dist_pos_health_logger.py (fixed: always mask paths in PUBLIC_MODE, strict JSON)
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, List


def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def sanitize_for_json(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, list):
        return [sanitize_for_json(x) for x in obj]
    if isinstance(obj, tuple):
        return [sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    return str(obj)


def json_dumps_strict(obj: Any) -> str:
    clean = sanitize_for_json(obj)
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


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
    p = Path(path)
    if not p.exists():
        return False

    size = p.stat().st_size
    if size <= 0:
        return False

    rb = min(read_bytes, size)
    with open(path, "rb") as f:
        f.seek(size - rb)
        buf = f.read(rb)

    lines = buf.splitlines(True)
    if not lines:
        return False

    good_end = None
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


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    ensure_dir(path)
    repair_jsonl_tail(path)
    line = json_dumps_strict(obj) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def read_last_record(jsonl_path: str, max_lines: int = 300) -> Optional[Dict[str, Any]]:
    p = Path(jsonl_path)
    if not p.exists():
        return None

    lines: List[str] = []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for ln in f:
                lines.append(ln)
        lines = lines[-max_lines:]
    except Exception:
        return None

    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def get_float(obj: Dict[str, Any], key: str) -> Optional[float]:
    try:
        v = obj.get(key)
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def main() -> None:
    PUBLIC_MODE = env_flag("ADSB_PUBLIC_MODE", "1")
    MASK_PATHS = env_flag("ADSB_HEALTH_MASK_PATHS", "0") or PUBLIC_MODE

    script_dir = Path(__file__).resolve().parent
    base_dir = Path(env_str("ADSB_BASE_DIR", str(script_dir.parent))).resolve()
    log_dir = Path(env_str("ADSB_LOG_DIR", str(base_dir / "data" / "logs"))).resolve()

    in_dist = env_str("ADSB_DIST_JSONL", str(log_dir / "dist_1m.jsonl"))
    out_health = env_str("ADSB_POS_HEALTH_JSONL", str(log_dir / "dist_pos_health_1m.jsonl"))

    ts = time.time()
    latest = read_last_record(in_dist)

    if not latest:
        append_jsonl(out_health, {"ts": ts, "src": "dist_pos_health", "status": "no_input"})
        return

    n_total = get_float(latest, "n_total")
    n_with_pos = get_float(latest, "n_with_pos")

    pos_rate: Optional[float] = None
    if n_total is not None and n_total > 0 and n_with_pos is not None:
        pos_rate = n_with_pos / n_total

    km = latest.get("km") if isinstance(latest.get("km"), dict) else {}

    health: Dict[str, Any] = {
        "ts": ts,
        "src": "dist_pos_health",
        "status": "ok",
        "input": {
            "dist_jsonl": "masked" if MASK_PATHS else in_dist,
        },
        "latest": {
            "n_total": int(n_total) if n_total is not None else None,
            "n_with_pos": int(n_with_pos) if n_with_pos is not None else None,
            "pos_rate": pos_rate,
            "km": {
                "avg": km.get("avg"),
                "p50": km.get("p50"),
                "p90": km.get("p90"),
                "p95": km.get("p95"),
                "max": km.get("max"),
                "n": km.get("n"),
            },
        },
    }

    append_jsonl(out_health, health)


if __name__ == "__main__":
    main()
