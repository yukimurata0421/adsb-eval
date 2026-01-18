#!/usr/bin/env python3
# make_summary.py (lib unified + schema-aware + A-policy: eval_ok)

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.env import env_flag, env_int, env_str
from lib.jsonl_read import tail_jsonl
from lib.jsonx import json_dumps_strict


def atomic_write_text(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(p))


def _pick_float(d: Dict[str, Any], path: List[str]) -> Optional[float]:
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


def _pick_bool(d: Dict[str, Any], path: List[str]) -> Optional[bool]:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    if isinstance(cur, bool):
        return cur
    if isinstance(cur, (int, float)):
        return bool(cur)
    if isinstance(cur, str):
        s = cur.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return None


def _pick_str(d: Dict[str, Any], path: List[str]) -> Optional[str]:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur if isinstance(cur, str) else None


def _mean(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / len(vals)


def summarize_dist_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    now_ts = time.time()
    if not records:
        return {"ts": now_ts, "status": "no_records"}

    latest = records[-1]

    # --- latest core fields (schema-aware) ---
    n_used_latest = _pick_float(latest, ["counts", "n_used"])
    n_total_latest = _pick_float(latest, ["counts", "n_total"])
    n_with_latest = _pick_float(latest, ["counts", "n_with_pos"])
    pos_rate_latest = _pick_float(latest, ["counts", "pos_rate"])

    # Some records may not have pos_rate computed; derive if possible
    if pos_rate_latest is None and n_total_latest is not None and n_with_latest is not None and n_total_latest > 0:
        pos_rate_latest = n_with_latest / n_total_latest

    eval_ok_latest = _pick_bool(latest, ["quality", "eval_ok"])
    # backward compat: if eval_ok missing, fallback to quality.ok
    if eval_ok_latest is None:
        eval_ok_latest = _pick_bool(latest, ["quality", "ok"])

    eval_state_latest = _pick_str(latest, ["quality", "state"])
    eval_reason_latest = _pick_str(latest, ["quality", "reason"])
    min_samples_for_stats = _pick_float(latest, ["filters", "min_samples_for_stats"])

    # --- rolling (all vs eval_ok only) ---
    dist_keys = {
        "km_avg": ["dist_km", "avg"],
        "km_p50": ["dist_km", "p50"],
        "km_p90": ["dist_km", "p90"],
        "km_p95": ["dist_km", "p95"],
        "km_max": ["dist_km", "max"],
    }
    count_keys = {
        "n_used": ["counts", "n_used"],
        "n_total": ["counts", "n_total"],
        "n_with_pos": ["counts", "n_with_pos"],
        "pos_rate": ["counts", "pos_rate"],
    }

    rolling_all: Dict[str, Any] = {"n": len(records)}
    rolling_eval: Dict[str, Any] = {"n": 0}

    # Build eval_ok mask per record
    eval_mask: List[bool] = []
    for r in records:
        b = _pick_bool(r, ["quality", "eval_ok"])
        if b is None:
            b = _pick_bool(r, ["quality", "ok"])
        eval_mask.append(bool(b))

    # counts (all)
    for outk, pth in count_keys.items():
        vals: List[float] = []
        for r in records:
            v = _pick_float(r, pth)
            if v is not None:
                vals.append(v)
        m = _mean(vals)
        if m is not None:
            rolling_all[outk] = m

    # dist (all)
    for outk, pth in dist_keys.items():
        vals_all: List[float] = []
        vals_eval: List[float] = []
        for r, ok in zip(records, eval_mask):
            v = _pick_float(r, pth)
            if v is None:
                continue
            vals_all.append(v)
            if ok:
                vals_eval.append(v)

        m_all = _mean(vals_all)
        if m_all is not None:
            rolling_all[outk] = m_all

        m_eval = _mean(vals_eval)
        if m_eval is not None:
            rolling_eval[outk] = m_eval

    rolling_eval["n"] = sum(1 for ok in eval_mask if ok)

    # --- summary payload ---
    out: Dict[str, Any] = {
        "ts": now_ts,
        "status": "ok",
        "latest": latest,
        "latest_eval": {
            "eval_ok": eval_ok_latest,
            "state": eval_state_latest,
            "reason": eval_reason_latest,
            "min_samples_for_stats": min_samples_for_stats,
            "n_used": n_used_latest,
        },
        "pos_rate_latest": pos_rate_latest,
        "rolling_all": rolling_all,
        "rolling_eval": rolling_eval,
    }

    return out


def main() -> None:
    public_mode = env_flag("ADSB_PUBLIC_MODE", "1")

    script_dir = Path(__file__).resolve().parent
    base_dir = Path(env_str("ADSB_BASE_DIR", str(script_dir.parent))).resolve()
    log_dir = Path(env_str("ADSB_LOG_DIR", str(base_dir / "data" / "logs"))).resolve()

    src_jsonl = env_str("ADSB_DIST_JSONL", str(log_dir / "dist_1m.jsonl"))
    out_json = env_str("ADSB_SUMMARY_JSON", str(log_dir / "summary.json"))

    max_lines = env_int("ADSB_SUMMARY_LINES", "120")

    records = tail_jsonl(src_jsonl, max_lines)
    summary = summarize_dist_records(records)

    # source block (path leaks are common)
    summary["source"] = {"lines": max_lines}
    if env_str("ADSB_SUMMARY_MASK_PATHS", "0") == "1" or public_mode:
        summary["source"]["dist_jsonl"] = "masked"
    else:
        summary["source"]["dist_jsonl"] = src_jsonl

    # PUBLIC_MODE: hide site block if present in latest (mask lat/lon)
    if public_mode and isinstance(summary.get("latest"), dict):
        latest = summary["latest"]
        if isinstance(latest.get("site"), dict):
            sid = latest["site"].get("id")
            latest["site"] = {"id": sid} if sid is not None else {"id": "unknown"}

    atomic_write_text(out_json, json_dumps_strict(summary) + "\n")


if __name__ == "__main__":
    main()
