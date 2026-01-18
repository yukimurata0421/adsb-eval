#!/usr/bin/env python3
# dist_pos_health_logger.py (lib unified + strict JSONL + public mode)

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from lib.env import env_flag, env_str
from lib.jsonl import append_jsonl
from lib.jsonl_read import read_last_record
from lib.privacy import mask_path_basename


def get_float(obj: Dict[str, Any], key: str) -> Optional[float]:
    try:
        v = obj.get(key)
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def main() -> None:
    public_mode = env_flag("ADSB_PUBLIC_MODE", "1")
    mask_paths = env_flag("ADSB_HEALTH_MASK_PATHS", "0") or public_mode

    script_dir = Path(__file__).resolve().parent
    base_dir = Path(env_str("ADSB_BASE_DIR", str(script_dir.parent))).resolve()
    log_dir = Path(env_str("ADSB_LOG_DIR", str(base_dir / "data" / "logs"))).resolve()

    in_dist = env_str("ADSB_DIST_JSONL", str(log_dir / "dist_1m.jsonl"))
    out_health = env_str("ADSB_POS_HEALTH_JSONL", str(log_dir / "dist_pos_health_1m.jsonl"))

    ts = time.time()
    latest = read_last_record(in_dist, max_lines=300)

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
            "dist_jsonl": "masked" if mask_paths else in_dist,
            # better default: basename masking for public debug
            "dist_jsonl_name": mask_path_basename(in_dist, public_mode),
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
