#!/usr/bin/env python3
# adsb_performance_logger.py (lib unified + strict json + public mode)

from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from lib.env import env_flag, env_float_opt, env_int, env_str
from lib.geo import haversine_km
from lib.httpx import fetch_json
from lib.jsonl import append_jsonl
from lib.privacy import build_site_block


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


def build_meta() -> Dict[str, Any]:
    return {
        "site_id": env_str("ADSB_SITE_ID", "unknown"),
        "antenna_id": env_str("ADSB_ANTENNA_ID", "unknown"),
        "dongle": env_str("ADSB_DONGLE", "unknown"),
        "lna": env_str("ADSB_LNA", "unknown"),
        "schema_ver": env_int("ADSB_SCHEMA_VER", "1"),
    }


def main() -> int:
    public_mode = env_flag("ADSB_PUBLIC_MODE", "1")

    script_dir = Path(__file__).resolve().parent
    base_dir = Path(env_str("ADSB_BASE_DIR", str(script_dir.parent))).resolve()
    log_dir = Path(env_str("ADSB_LOG_DIR", str(base_dir / "data" / "logs"))).resolve()

    aircraft_url = env_str("ADSB_AIRCRAFT_URL", "http://localhost/tar1090/data/aircraft.json")
    stats_url = env_str("ADSB_STATS_URL", "http://localhost/tar1090/data/stats.json")

    # If coordinates are set -> output distance stats. If not -> skip distance part.
    site_lat = env_float_opt("ADSB_SITE_LAT")
    site_lon = env_float_opt("ADSB_SITE_LON")

    out_dist = env_str("ADSB_PERF_DIST_JSONL", str(log_dir / "adsb_perf_dist.jsonl"))
    out_stats = env_str("ADSB_PERF_STATS_JSONL", str(log_dir / "adsb_perf_stats.jsonl"))

    ts = time.time()
    meta = build_meta()
    site_id = env_str("ADSB_SITE_ID", "unknown")

    s = requests.Session()
    s.headers.update({"User-Agent": "adsb-eval/1.0"})

    # 1) aircraft.json -> distance stats (km unified)
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
            # site block: in public mode keep id only (consistent with other scripts)
            rec["site"] = build_site_block(site_id, public_mode, site_lat, site_lon)
            append_jsonl(out_dist, rec)

    # 2) stats.json -> total as JSONL (for comparisons)
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
