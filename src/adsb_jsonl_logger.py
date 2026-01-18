#!/usr/bin/env python3
# adsb_jsonl_logger.py (publish-hardened)

from __future__ import annotations

import json
import time
from typing import Any, Dict

from lib.env import env_flag, env_str
from lib.jsonl import append_jsonl, repair_jsonl_tail


def build_meta() -> Dict[str, Any]:
    # schema_ver is a string env; keep int-like but safe
    try:
        schema_ver = int(env_str("ADSB_SCHEMA_VER", "1"))
    except Exception:
        schema_ver = 1

    return {
        "site_id": env_str("ADSB_SITE_ID", "unknown"),
        "antenna_id": env_str("ADSB_ANTENNA_ID", "unknown"),
        "dongle": env_str("ADSB_DONGLE", "unknown"),
        "lna": env_str("ADSB_LNA", "unknown"),
        "schema_ver": schema_ver,
    }


def main() -> int:
    public_mode = env_flag("ADSB_PUBLIC_MODE", "1")

    readsb_stats = env_str("READSB_STATS_JSON", "/run/readsb/stats.json")

    base_dir = env_str("ADSB_BASE_DIR", "/home/yuki/publish/adsb-eval")
    log_dir = env_str("ADSB_LOG_DIR", f"{base_dir}/data/logs")
    out_path = env_str("ADSB_STATS_JSONL", f"{log_dir}/stats_history.jsonl")

    ts = time.time()
    meta = build_meta()

    repair_jsonl_tail(out_path)

    try:
        with open(readsb_stats, "r", encoding="utf-8") as f:
            stats = json.load(f)
        if not isinstance(stats, dict):
            raise ValueError("readsb stats.json is not an object")
    except Exception as e:
        append_jsonl(out_path, {"ts": ts, "src": "readsb_stats", "meta": meta, "error": str(e)})
        return 1

    rec: Dict[str, Any] = {
        "ts": ts,
        "src": "readsb_stats",
        "meta": meta,
        "stats": stats,
    }

    # minimal public sanitization
    if public_mode and isinstance(rec.get("stats"), dict):
        s = rec["stats"]
        for k in ("lat", "lon", "site", "receiverLat", "receiverLon"):
            if k in s:
                s.pop(k, None)

    append_jsonl(out_path, rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
