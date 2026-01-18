#!/usr/bin/env python3
# src/adsb_dist_logger.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from lib.env import env_float_opt, env_str
from lib.fsutil import ensure_dir_for_file
from lib.geo import haversine_km
from lib.jsonl import append_jsonl
from lib.lockutil import acquire_lock, release_lock
from lib.timeutil import unix_now


# ----------------------------
# Config
# ----------------------------
AIRCRAFT_JSON = env_str("READSB_AIRCRAFT_JSON", "/run/readsb/aircraft.json")

LOG_DIR = env_str("ADSB_LOG_DIR", "data/logs")
STATE_DIR = env_str("ADSB_STATE_DIR", "data/state")

OUT_JSONL = os.path.join(LOG_DIR, env_str("ADSB_DIST_JSONL", "dist_1m.jsonl"))
ERR_JSONL = os.path.join(LOG_DIR, env_str("ADSB_DIST_ERR_JSONL", "dist_1m_errors.jsonl"))
LOCK_PATH = os.path.join(STATE_DIR, os.getenv("ADSB_DIST_LOCK", "adsb_dist_logger.lock"))

SITE_ID = env_str("ADSB_SITE_ID", "unknown")
SITE_LAT = env_float_opt("ADSB_SITE_LAT", None)
SITE_LON = env_float_opt("ADSB_SITE_LON", None)

CONFIG_ID = env_str("ADSB_CONFIG_ID", "unknown")
GAIN_DB = env_float_opt("ADSB_GAIN_DB", None)

MAX_SEEN_POS_S = float(env_str("ADSB_MAX_SEEN_POS_S", "30"))
MIN_SAMPLES_FOR_STATS = int(env_str("ADSB_MIN_SAMPLES_FOR_STATS", "5"))

BUCKET_EDGES_KM: List[float] = [
    0, 5, 10, 20, 30, 50, 80, 120, 160, 200, 250, 300, 400
]


# ----------------------------
# Helpers
# ----------------------------
def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _bucket_index(d_km: float) -> int:
    for i in range(len(BUCKET_EDGES_KM) - 1):
        if BUCKET_EDGES_KM[i] <= d_km < BUCKET_EDGES_KM[i + 1]:
            return i
    return len(BUCKET_EDGES_KM) - 1


def _percentile(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    xs2 = sorted(xs)
    if q <= 0:
        return xs2[0]
    if q >= 100:
        return xs2[-1]
    k = (len(xs2) - 1) * (q / 100.0)
    f = int(k)
    c = min(f + 1, len(xs2) - 1)
    if f == c:
        return xs2[f]
    return xs2[f] * (c - k) + xs2[c] * (k - f)


def _append_error(where: str, err: Exception, ts: float) -> None:
    ensure_dir_for_file(ERR_JSONL)
    append_jsonl(
        ERR_JSONL,
        {
            "ts": ts,
            "src": "dist_1m_error",
            "where": where,
            "error": repr(err),
        },
    )


def _quality_eval(n_used: int) -> Dict[str, Any]:
    """
    A案：quality.ok を「正常/異常」ではなく「評価可能か」に寄せる。
    - eval_ok: 評価可能（サンプル数が足りる）なら True
    - state:   "ok" or "insufficient_samples"
    - reason:  人間向け短文

    互換維持のため、quality.ok も当面は残す（= eval_ok と同義）。
    """
    eval_ok = (n_used >= MIN_SAMPLES_FOR_STATS)
    if eval_ok:
        return {
            "eval_ok": True,
            "state": "ok",
            "reason": None,
            "ok": True,  # backward-compat: same as eval_ok
        }
    return {
        "eval_ok": False,
        "state": "insufficient_samples",
        "reason": f"insufficient_samples(n_used={n_used})",
        "ok": False,  # backward-compat: same as eval_ok
    }


# ----------------------------
# Main
# ----------------------------
def main() -> int:
    ts = float(unix_now())

    # 座標が無いなら距離計算できない → 落とさず errors.jsonl に書いて終了
    if SITE_LAT is None or SITE_LON is None:
        ensure_dir_for_file(ERR_JSONL)
        append_jsonl(
            ERR_JSONL,
            {
                "ts": ts,
                "src": "dist_1m_error",
                "where": "config",
                "error": "ADSB_SITE_LAT/LON not set (cannot compute distance)",
            },
        )
        return 0

    ensure_dir_for_file(OUT_JSONL)
    ensure_dir_for_file(ERR_JSONL)
    ensure_dir_for_file(LOCK_PATH)

    fd: Optional[int] = None
    try:
        fd = acquire_lock(LOCK_PATH)
        if fd is None:
            # 既に実行中 → 静かに終了
            return 0

        data = _read_json(AIRCRAFT_JSON)
        aircraft = data.get("aircraft", [])
        if not isinstance(aircraft, list):
            aircraft = []

        dists: List[float] = []
        n_total = 0
        n_with_pos = 0

        for a in aircraft:
            n_total += 1

            lat = a.get("lat")
            lon = a.get("lon")
            if lat is None or lon is None:
                continue

            seen_pos = a.get("seen_pos")
            if isinstance(seen_pos, (int, float)) and float(seen_pos) > MAX_SEEN_POS_S:
                continue

            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except Exception:
                continue

            n_with_pos += 1
            d_km = float(haversine_km(float(SITE_LAT), float(SITE_LON), lat_f, lon_f))
            dists.append(d_km)

        n_used = len(dists)
        pos_rate = (n_with_pos / n_total) if n_total > 0 else None

        bucket_counts = [0] * len(BUCKET_EDGES_KM)
        for d in dists:
            bucket_counts[_bucket_index(d)] += 1

        rec: Dict[str, Any] = {
            "ts": ts,
            "src": "dist_1m",
            "site": {"id": SITE_ID, "lat": SITE_LAT, "lon": SITE_LON},
            "setup": {"config_id": CONFIG_ID, "gain_db": GAIN_DB},
            "filters": {
                "max_seen_pos_s": MAX_SEEN_POS_S,
                "min_samples_for_stats": MIN_SAMPLES_FOR_STATS,
            },
            "counts": {
                "n_total": n_total,
                "n_with_pos": n_with_pos,
                "pos_rate": pos_rate,
                "n_used": n_used,
            },
            "dist_km": {
                "avg": (sum(dists) / n_used) if n_used > 0 else None,
                "p50": _percentile(dists, 50),
                "p90": _percentile(dists, 90),
                "p95": _percentile(dists, 95),
                "max": max(dists) if n_used > 0 else None,
            },
            "buckets": {"edges_km": BUCKET_EDGES_KM, "counts": bucket_counts},
            "quality": _quality_eval(n_used),
        }

        append_jsonl(OUT_JSONL, rec)
        return 0

    except Exception as e:
        try:
            _append_error("main", e, ts)
        except Exception:
            pass
        raise
    finally:
        release_lock(fd)


if __name__ == "__main__":
    raise SystemExit(main())
