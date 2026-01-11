#!/usr/bin/env python3
# adsb_performance_logger.py (fixed + km unified + strict json + public mode)
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# -----------------------
# env helpers
# -----------------------
def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v in (None, ""):
        return default
    try:
        return int(v)
    except Exception:
        return default


def env_float(name: str, default: Optional[float]) -> Optional[float]:
    v = os.environ.get(name)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except Exception:
        return default


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")


# -----------------------
# strict json
# -----------------------
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


# -----------------------
# file helpers
# -----------------------
def ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


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
    JSONLの末尾が壊れていたら最後の正常行までtruncateして修復する。
    """
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
        ln = lines[i].strip()
        offset_from_tail += len(lines[i])
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


# -----------------------
# math
# -----------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def percentile_sorted(vals_sorted: List[float], p: float) -> Optional[float]:
    n = len(vals_sorted)
    if n == 0:
        return None
    if n == 1:
        return vals_sorted[0]
    if p <= 0:
        return vals_sorted[0]
    if p >= 100:
        return vals_sorted[-1]
    r = (p / 100.0) * (n - 1)
    lo, hi = int(math.floor(r)), int(math.ceil(r))
    if lo == hi:
        return vals_sorted[lo]
    return vals_sorted[lo] * (1 - (r - lo)) + vals_sorted[hi] * (r - lo)


# -----------------------
# http
# -----------------------
def fetch_json(session: requests.Session, url: str, timeout_s: int = 5) -> Optional[Dict[str, Any]]:
    try:
        r = session.get(url, timeout=timeout_s)
        if r.status_code != 200:
            return None
        j = r.json()
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def build_meta() -> Dict[str, Any]:
    return {
        "site_id": env_str("ADSB_SITE_ID", "unknown"),
        "antenna_id": env_str("ADSB_ANTENNA_ID", "unknown"),
        "dongle": env_str("ADSB_DONGLE", "unknown"),
        "lna": env_str("ADSB_LNA", "unknown"),
        "schema_ver": env_int("ADSB_SCHEMA_VER", 1),
    }


def main() -> int:
    public_mode = env_flag("ADSB_PUBLIC_MODE", "1")

    script_dir = Path(__file__).resolve().parent
    base_dir = Path(env_str("ADSB_BASE_DIR", str(script_dir.parent))).resolve()
    log_dir = Path(env_str("ADSB_LOG_DIR", str(base_dir / "data" / "logs"))).resolve()

    aircraft_url = env_str("ADSB_AIRCRAFT_URL", "http://localhost/tar1090/data/aircraft.json")
    stats_url = env_str("ADSB_STATS_URL", "http://localhost/tar1090/data/stats.json")

    # 位置は「設定された場合のみ距離統計を出す」
    site_lat = env_float("ADSB_SITE_LAT", None)
    site_lon = env_float("ADSB_SITE_LON", None)

    out_dist = env_str("ADSB_PERF_DIST_JSONL", str(log_dir / "adsb_perf_dist.jsonl"))
    out_stats = env_str("ADSB_PERF_STATS_JSONL", str(log_dir / "adsb_perf_stats.jsonl"))

    ts = time.time()
    meta = build_meta()

    s = requests.Session()
    s.headers.update({"User-Agent": "adsb-eval/1.0"})

    # 1) aircraft.json -> 距離統計（kmを他と統一）
    aircraft = fetch_json(s, aircraft_url, timeout_s=5)
    if aircraft and isinstance(aircraft.get("aircraft"), list) and site_lat is not None and site_lon is not None:
        distances: List[float] = []
        for a in aircraft.get("aircraft", []):
            if not isinstance(a, dict):
                continue
            lat = a.get("lat")
            lon = a.get("lon")
            if lat is None or lon is None:
                continue
            try:
                d = haversine_km(float(site_lat), float(site_lon), float(lat), float(lon))
                if math.isfinite(d) and d >= 0:
                    distances.append(d)
            except Exception:
                continue

        if distances:
            distances.sort()
            rec: Dict[str, Any] = {
                "ts": ts,
                "src": "adsb_perf_dist",
                "meta": meta,
                "n_used": len(distances),
                "km": {
                    "n": len(distances),
                    "avg": round(sum(distances) / len(distances), 3),
                    "p50": round(percentile_sorted(distances, 50) or 0.0, 3),
                    "p90": round(percentile_sorted(distances, 90) or 0.0, 3),
                    "p95": round(percentile_sorted(distances, 95) or 0.0, 3),
                    "max": round(distances[-1], 3),
                },
            }
            if not public_mode:
                rec["site"] = {"lat": site_lat, "lon": site_lon}
            append_jsonl(out_dist, rec)

    # 2) stats.json -> total をJSONL化（比較用）
    stats = fetch_json(s, stats_url, timeout_s=5)
    if stats and isinstance(stats.get("total"), dict):
        rec2: Dict[str, Any] = dict(stats["total"])
        rec2["ts"] = ts
        rec2["src"] = "adsb_perf_stats"
        rec2["meta"] = meta
        append_jsonl(out_stats, rec2)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[adsb_performance_logger] unexpected error: {e}", file=sys.stderr)
        raise SystemExit(1)
