#!/usr/bin/env python3
"""
readsb_dist_signal_stats_logger.py (public-hardened)

Distance-bucketed RSSI stats from readsb aircraft.json.

Features:
- RSSI distribution by distance buckets (avg/min/max/p50/p90/p95)
- Append-only JSONL output with crash safety (tail repair + fsync)
- PUBLIC_MODE: hide coordinates and file paths (basename only)
- Non-blocking: returns 0 for systemd timer compatibility

Env:
- ADSB_SITE_LAT / ADSB_SITE_LON: receiver coordinates (required)
- ADSB_SITE_ID: site identifier (default: unknown)
- ADSB_CONFIG_ID: config identifier tag (optional, recommended)
- ADSB_PUBLIC_MODE: hide coordinates/paths in output (default: 1)
- READSB_AIRCRAFT_JSON: aircraft.json path (default: /run/readsb/aircraft.json)
- ADSB_LOG_DIR: output directory (default: $ADSB_MONITOR_DIR/data/logs)
- ADSB_DIST_SIGNAL_JSONL: output JSONL path (default: $ADSB_LOG_DIR/dist_signal_stats_1m.jsonl)
- ADSB_SCHEMA_VER: schema version (default: 1)
- ADSB_MAX_SEEN_POS_SEC: exclude stale positions (seconds); unset/empty to disable
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# =====================
# Env helpers
# =====================
def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def env_float_opt(name: str, default: Optional[float] = None) -> Optional[float]:
    v = os.environ.get(name)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), ignored")
        return default


def env_float(name: str, default: str) -> float:
    v = os.environ.get(name)
    if v in (None, ""):
        return float(default)
    try:
        return float(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return float(default)


def env_int(name: str, default: str) -> int:
    v = os.environ.get(name)
    if v in (None, ""):
        return int(default)
    try:
        return int(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return int(default)


# =====================
# Config
# =====================
PUBLIC_MODE = env_flag("ADSB_PUBLIC_MODE", "1")

RECEIVER_LAT = env_float("ADSB_SITE_LAT", "0.0")
RECEIVER_LON = env_float("ADSB_SITE_LON", "0.0")

SITE_ID = env_str("ADSB_SITE_ID", "unknown")
CONFIG_ID = env_str("ADSB_CONFIG_ID", "")

AIRCRAFT_JSON = env_str("READSB_AIRCRAFT_JSON", "/run/readsb/aircraft.json")

BASE_DIR = env_str("ADSB_MONITOR_DIR", "/home/yuki/projects/adsb_monitor")
LOG_DIR = env_str("ADSB_LOG_DIR", os.path.join(BASE_DIR, "data", "logs"))
LOG_FILE = env_str("ADSB_DIST_SIGNAL_JSONL", os.path.join(LOG_DIR, "dist_signal_stats_1m.jsonl"))

SCHEMA_VER = env_int("ADSB_SCHEMA_VER", "1")

# Distance bucket edges (km): 0-25, 25-50, ..., 250-300, 300+ overflow
BUCKET_EDGES = [0, 25, 50, 75, 100, 125, 150, 175, 200, 225, 250, 300]

# seen_pos = seconds ago (larger => older). if unset, do not filter.
MAX_SEEN_POS_SEC = env_float_opt("ADSB_MAX_SEEN_POS_SEC", None)


# =====================
# Strict JSON
# =====================
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


# =====================
# File helpers (JSONL hardened)
# =====================
def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def utc_iso_z(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _try_parse_json_line_keepend(line: bytes) -> bool:
    ln = line.strip()
    if not ln:
        return True
    try:
        json.loads(ln.decode("utf-8"))
        return True
    except Exception:
        return False


def repair_jsonl_tail(path: str, read_bytes: int = 64 * 1024) -> bool:
    """Repair truncated last line by truncating to end of last valid JSON line."""
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    if size <= 0:
        return False

    rb = min(read_bytes, size)
    start = size - rb
    with open(path, "rb") as f:
        f.seek(start)
        buf = f.read(rb)

    lines = buf.splitlines(True)  # keepends=True
    if not lines:
        return False

    last_good_i: Optional[int] = None
    for i in range(len(lines) - 1, -1, -1):
        if _try_parse_json_line_keepend(lines[i]):
            if lines[i].strip():
                last_good_i = i
                break
            continue

    if last_good_i is None:
        return False

    good_end = start + sum(len(x) for x in lines[: last_good_i + 1])
    if good_end >= size:
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


def mask_path_basename(path: str) -> str:
    """Public: basename only. Internal: full path."""
    if not path:
        return ""
    return os.path.basename(path) if PUBLIC_MODE else path


def build_site_block() -> Dict[str, Any]:
    if PUBLIC_MODE:
        return {"id": SITE_ID}
    return {"id": SITE_ID, "lat": RECEIVER_LAT, "lon": RECEIVER_LON}


# =====================
# Math
# =====================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * (math.sin(dlon / 2) ** 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def bucket_label(i: int) -> str:
    if i < len(BUCKET_EDGES) - 1:
        return f"{BUCKET_EDGES[i]}-{BUCKET_EDGES[i+1]}km"
    return f"{BUCKET_EDGES[-1]}+km"


def bucket_index(dist_km: float) -> int:
    idx = bisect_right(BUCKET_EDGES, dist_km) - 1
    if idx < 0:
        return 0
    if idx >= len(BUCKET_EDGES) - 1:
        return len(BUCKET_EDGES) - 1
    return idx


def percentile_nearest_rank(sorted_vals: List[float], p: float) -> Optional[float]:
    n = len(sorted_vals)
    if n == 0:
        return None
    if p <= 0:
        return sorted_vals[0]
    if p >= 1:
        return sorted_vals[-1]
    k = int(math.ceil(p * n)) - 1
    k = max(0, min(n - 1, k))
    return sorted_vals[k]


def summarize_signals(signals: List[float]) -> Dict[str, Any]:
    n = len(signals)
    if n == 0:
        return {"n_samples": 0, "avg": None, "min": None, "max": None, "p50": None, "p90": None, "p95": None}
    vals = sorted(signals)
    s = sum(vals)
    avg = s / n
    return {
        "n_samples": n,
        "avg": round(avg, 2),
        "min": vals[0],
        "max": vals[-1],
        "p50": percentile_nearest_rank(vals, 0.50),
        "p90": percentile_nearest_rank(vals, 0.90),
        "p95": percentile_nearest_rank(vals, 0.95),
    }


# =====================
# Core
# =====================
def safe_load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_stats() -> Optional[Dict[str, Any]]:
    # Validate coordinates
    if RECEIVER_LAT == 0.0 and RECEIVER_LON == 0.0:
        warn("ADSB_SITE_LAT/LON not set, skipping")
        return None

    data = safe_load_json(AIRCRAFT_JSON)
    if not data:
        return None

    now = time.time()
    aircrafts = data.get("aircraft", [])
    if not isinstance(aircrafts, list):
        return None

    buckets: List[List[float]] = [[] for _ in range(len(BUCKET_EDGES))]

    n_aircraft_total = len(aircrafts)
    n_with_pos = 0
    n_used = 0
    n_overflow = 0
    n_missing_rssi = 0
    n_skipped_stale_pos = 0

    for ac in aircrafts:
        if not isinstance(ac, dict):
            continue

        lat = ac.get("lat")
        lon = ac.get("lon")
        rssi = ac.get("rssi")

        if lat is None or lon is None:
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        n_with_pos += 1

        if MAX_SEEN_POS_SEC is not None:
            seen_pos = ac.get("seen_pos")
            if isinstance(seen_pos, (int, float)) and float(seen_pos) > float(MAX_SEEN_POS_SEC):
                n_skipped_stale_pos += 1
                continue

        if rssi is None or not isinstance(rssi, (int, float)):
            n_missing_rssi += 1
            continue

        dist_km = haversine_km(RECEIVER_LAT, RECEIVER_LON, float(lat), float(lon))
        idx = bucket_index(dist_km)

        if idx == len(BUCKET_EDGES) - 1 and dist_km >= BUCKET_EDGES[-1]:
            n_overflow += 1

        buckets[idx].append(float(rssi))
        n_used += 1

    output_buckets: Dict[str, Any] = {}
    for i in range(len(BUCKET_EDGES)):
        output_buckets[bucket_label(i)] = summarize_signals(buckets[i])

    return {
        "ts": now,
        "ts_iso_utc": utc_iso_z(now),
        "src": "dist_signal_stats",
        "producer": "readsb",
        "schema_ver": SCHEMA_VER,
        "config_id": CONFIG_ID or None,
        "site": build_site_block(),
        "inputs": {
            "aircraft_json": mask_path_basename(AIRCRAFT_JSON),
            "bucket_edges_km": BUCKET_EDGES,
            "max_seen_pos_sec": MAX_SEEN_POS_SEC,
        },
        "counts": {
            "aircraft_total": n_aircraft_total,
            "aircraft_with_pos": n_with_pos,
            "aircraft_used_in_stats": n_used,
            "aircraft_overflow_ge_last_edge": n_overflow,
            "aircraft_missing_rssi": n_missing_rssi,
            "aircraft_skipped_stale_pos": n_skipped_stale_pos,
        },
        "buckets": output_buckets,
    }


def main() -> int:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    result = get_stats()
    if result is None:
        return 0

    try:
        append_jsonl(LOG_FILE, result)
    except Exception as e:
        warn(f"Failed to write JSONL: {e}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
