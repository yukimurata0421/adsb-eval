#!/usr/bin/env python3
# make_summary.py (public-hardened)
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


def env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v in (None, ""):
        return default
    try:
        return int(v)
    except Exception:
        return default


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


def json_dumps_strict(obj: Any, *, indent: int | None = None) -> str:
    clean = sanitize_for_json(obj)
    return json.dumps(
        clean,
        ensure_ascii=False,
        sort_keys=False,
        indent=indent,
        separators=(",", ":") if indent is None else None,
        allow_nan=False,
    )


def atomic_write_text(path: str, text: str) -> None:
    ensure_dir(path)
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(p))


def safe_load_json_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    try:
        v = json.loads(line)
        if isinstance(v, dict):
            return v
        return None
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


def summarize_dist_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    now = time.time()
    if not records:
        return {"ts": now, "status": "no_records"}

    latest = records[-1]

    def pick_float(d: Dict[str, Any], path: List[str]) -> Optional[float]:
        cur: Any = d
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        try:
            v = float(cur)
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        except Exception:
            return None

    keys = {
        "km_avg": ["km", "avg"],
        "km_p50": ["km", "p50"],
        "km_p90": ["km", "p90"],
        "km_p95": ["km", "p95"],
        "km_max": ["km", "max"],
        "n_used": ["n_used"],
        "n_total": ["n_total"],
        "n_with_pos": ["n_with_pos"],
    }

    roll: Dict[str, Any] = {"n": len(records)}
    for outk, pth in keys.items():
        vals: List[float] = []
        for r in records:
            v = pick_float(r, pth)
            if v is not None:
                vals.append(v)
        if vals:
            roll[outk] = sum(vals) / len(vals)

    n_with = pick_float(latest, ["n_with_pos"])
    n_total = pick_float(latest, ["n_total"])
    pos_rate = None
    if n_with is not None and n_total is not None and n_total > 0:
        pos_rate = n_with / n_total

    return {"ts": now, "status": "ok", "latest": latest, "rolling": roll, "pos_rate_latest": pos_rate}


def main() -> None:
    PUBLIC_MODE = env_flag("ADSB_PUBLIC_MODE", "1")

    script_dir = Path(__file__).resolve().parent
    base_dir = Path(env_str("ADSB_BASE_DIR", str(script_dir.parent))).resolve()
    log_dir = Path(env_str("ADSB_LOG_DIR", str(base_dir / "data" / "logs"))).resolve()

    src_jsonl = env_str("ADSB_DIST_JSONL", str(log_dir / "dist_1m.jsonl"))
    out_json = env_str("ADSB_SUMMARY_JSON", str(log_dir / "summary.json"))

    max_lines = env_int("ADSB_SUMMARY_LINES", 60)

    records = tail_jsonl(src_jsonl, max_lines)
    summary = summarize_dist_records(records)

    # source block (path leaks are common)
    summary["source"] = {"lines": max_lines}
    if env_str("ADSB_SUMMARY_MASK_PATHS", "0") == "1" or PUBLIC_MODE:
        summary["source"]["dist_jsonl"] = "masked"
    else:
        summary["source"]["dist_jsonl"] = src_jsonl

    # PUBLIC_MODE: hide site block if present in latest
    if PUBLIC_MODE and isinstance(summary.get("latest"), dict):
        latest = summary["latest"]
        if isinstance(latest.get("site"), dict):
            # keep id only if exists
            sid = latest["site"].get("id")
            latest["site"] = {"id": sid} if sid is not None else {"id": "unknown"}

    atomic_write_text(out_json, json_dumps_strict(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
