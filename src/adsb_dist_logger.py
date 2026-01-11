#!/usr/bin/env python3
"""
adsb_dist_logger.py (public-hardened)

- Read readsb aircraft.json snapshot
- Compute distance distribution vs site (lat/lon)
- Append summary to JSONL (1 record per run)
- Append-only / crash-safe / single-instance
- Adds:
  - setup metadata (antenna / LNA / gain / dongle)
  - quality rank (based on n_used)
- Public hardening:
  - strict JSON (NaN/Inf -> null, allow_nan=False)
  - PUBLIC_MODE hides site lat/lon
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ===== Linux lock =====
try:
    import fcntl
except Exception:
    fcntl = None  # type: ignore


# =====================
# Utility / env helpers
# =====================
def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_float(name: str, default: str) -> float:
    v = os.environ.get(name)
    if v is None:
        return float(default)
    try:
        return float(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return float(default)


def env_int(name: str, default: str) -> int:
    v = os.environ.get(name)
    if v is None:
        return int(default)
    try:
        return int(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return int(default)


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def get_file_age_sec(path: str) -> Optional[int]:
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        return None
    return max(0, int(time.time() - mtime))


# =====================
# Strict JSON sanitize
# =====================
def sanitize_for_json(obj: Any) -> Any:
    # NaN/Inf -> None, recursively
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
    # fallback
    return str(obj)


def json_dumps_strict(obj: Any) -> str:
    clean = sanitize_for_json(obj)
    return json.dumps(
        clean,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


# =====================
# Config
# =====================
PUBLIC_MODE = env_flag("ADSB_PUBLIC_MODE", "1")  # publish default: safe

AIRCRAFT_JSON_PATH = env_str("READSB_AIRCRAFT_JSON", "/run/readsb/aircraft.json")
AIRCRAFT_STALE_SEC = env_int("ADSB_AIRCRAFT_STALE_SEC", "120")

BASE_DIR = env_str("ADSB_MONITOR_DIR", "/home/yuki/projects/adsb_monitor")
LOG_DIR = env_str("ADSB_LOG_DIR", os.path.join(BASE_DIR, "data", "logs"))

OUT_JSONL_PATH = env_str("ADSB_DIST_JSONL", os.path.join(LOG_DIR, "dist_1m.jsonl"))
ERR_JSONL_PATH = env_str("ADSB_DIST_ERR_JSONL", os.path.join(LOG_DIR, "dist_1m_errors.jsonl"))

LOCK_PATH = env_str("ADSB_DIST_LOCK", "/run/lock/adsb_dist_logger.lock")

# Site (used for distance calc; may be hidden in output)
SITE_LAT = env_float("ADSB_SITE_LAT", "36.120054940988986")
SITE_LON = env_float("ADSB_SITE_LON", "140.23229972540037")

MAX_SEEN_POS_S = env_float("ADSB_MAX_SEEN_POS_S", "30")
MIN_SAMPLES_FOR_STATS = env_int("ADSB_MIN_SAMPLES_FOR_STATS", "5")

SRC_NAME = env_str("ADSB_DIST_SRC", "dist_1m")

# ---- setup metadata (comparison axis) ----
SITE_ID = env_str("ADSB_SITE_ID", "unknown")
ANTENNA_ID = env_str("ADSB_ANTENNA_ID", "unknown")
LNA_NAME = env_str("ADSB_LNA", "unknown")
DONGLE_NAME = env_str("ADSB_DONGLE", "unknown")
# NOTE: default "nan" was risky for strict JSON; keep as float but will become null after sanitize
GAIN_DB = env_float("ADSB_GAIN_DB", "nan")
SCHEMA_VER = env_int("ADSB_SCHEMA_VER", "3")


# =====================
# Lock helpers
# =====================
def acquire_lock(path: str) -> Optional[int]:
    if fcntl is None:
        return -1
    ensure_dir(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
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


# =====================
# JSONL helpers
# =====================
def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    ensure_dir(path)
    line = json_dumps_strict(record) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


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
    Repair truncated last line (power loss etc.). Strictly validate JSON lines.
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


# =====================
# Math
# =====================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def percentile(vals_sorted: List[float], p: float) -> Optional[float]:
    n = len(vals_sorted)
    if n == 0:
        return None
    if n == 1:
        return vals_sorted[0]
    r = (p / 100.0) * (n - 1)
    lo, hi = int(math.floor(r)), int(math.ceil(r))
    if lo == hi:
        return vals_sorted[lo]
    return vals_sorted[lo] * (1 - (r - lo)) + vals_sorted[hi] * (r - lo)


def quality_rank(n: int) -> str:
    if n >= 20:
        return "A"
    if n >= 10:
        return "B"
    if n >= 5:
        return "C"
    return "D"


# =====================
# Core
# =====================
def load_snapshot(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_distances(
    snap: Dict[str, Any],
    lat0: float,
    lon0: float,
    max_seen: float,
) -> Tuple[List[float], Dict[str, int]]:
    aircraft = snap.get("aircraft", [])
    distances: List[float] = []

    meta = {
        "n_total": 0,
        "n_with_pos": 0,
        "n_seen_pos_ok": 0,
        "n_fresh": 0,
        "n_used": 0,
    }

    if not isinstance(aircraft, list):
        return distances, meta

    meta["n_total"] = len(aircraft)

    for a in aircraft:
        if not isinstance(a, dict):
            continue

        lat, lon = a.get("lat"), a.get("lon")
        if lat is None or lon is None:
            continue
        try:
            latf, lonf = float(lat), float(lon)
        except Exception:
            continue
        if not (-90 <= latf <= 90 and -180 <= lonf <= 180):
            continue

        meta["n_with_pos"] += 1

        seen_pos = a.get("seen_pos")
        try:
            sp = float(seen_pos)
        except Exception:
            continue

        meta["n_seen_pos_ok"] += 1
        if 0.0 <= sp <= max_seen:
            meta["n_fresh"] += 1
            d = haversine_km(lat0, lon0, latf, lonf)
            if math.isfinite(d) and d >= 0:
                distances.append(d)

    meta["n_used"] = len(distances)
    return distances, meta


def build_site_block() -> Dict[str, Any]:
    if PUBLIC_MODE:
        return {"id": SITE_ID}
    return {"id": SITE_ID, "lat": SITE_LAT, "lon": SITE_LON}


def build_ok_record(ts: float, meta: Dict[str, int], dists: List[float]) -> Dict[str, Any]:
    n = meta["n_used"]
    rec: Dict[str, Any] = {
        "ts": ts,
        "src": SRC_NAME,
        "site": build_site_block(),
        "filters": {"max_seen_pos_s": MAX_SEEN_POS_S, "min_samples_for_stats": MIN_SAMPLES_FOR_STATS},
        "setup": {
            "schema_ver": SCHEMA_VER,
            "antenna_id": ANTENNA_ID,
            "lna": LNA_NAME,
            "gain_db": GAIN_DB,
            "dongle": DONGLE_NAME,
        },
        "quality": {"rank": quality_rank(n), "n_used": n},
        **meta,
    }

    if n < MIN_SAMPLES_FOR_STATS:
        rec["km"] = {"n": n}
        return rec

    s = sorted(dists)
    rec["km"] = {
        "n": n,
        "avg": round(sum(s) / n, 3),
        "p50": round(percentile(s, 50) or 0.0, 3),
        "p75": round(percentile(s, 75) or 0.0, 3),
        "p90": round(percentile(s, 90) or 0.0, 3),
        "p95": round(percentile(s, 95) or 0.0, 3),
        "max": round(s[-1], 3),
    }
    return rec


def build_error_record(ts: float, msg: str) -> Dict[str, Any]:
    return {
        "ts": ts,
        "src": SRC_NAME,
        "site": build_site_block(),
        "error": msg,
    }


def main() -> int:
    ts = time.time()

    lock_fd = acquire_lock(LOCK_PATH)
    if lock_fd is None:
        return 0

    try:
        repair_jsonl_tail(OUT_JSONL_PATH)
        repair_jsonl_tail(ERR_JSONL_PATH)

        try:
            age = get_file_age_sec(AIRCRAFT_JSON_PATH)
            if age is None:
                append_jsonl(ERR_JSONL_PATH, build_error_record(ts, "aircraft.json missing"))
                return 1
            if age > AIRCRAFT_STALE_SEC:
                append_jsonl(ERR_JSONL_PATH, build_error_record(ts, f"aircraft.json stale: age={age}s"))
                return 1
            snap = load_snapshot(AIRCRAFT_JSON_PATH)
        except Exception as e:
            append_jsonl(ERR_JSONL_PATH, build_error_record(ts, f"aircraft.json load failed: {e}"))
            return 1

        try:
            dists, meta = extract_distances(snap, SITE_LAT, SITE_LON, MAX_SEEN_POS_S)
            rec = build_ok_record(ts, meta, dists)
            append_jsonl(OUT_JSONL_PATH, rec)
            return 0
        except Exception as e:
            append_jsonl(ERR_JSONL_PATH, build_error_record(ts, f"compute failed: {e}"))
            return 1

    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
