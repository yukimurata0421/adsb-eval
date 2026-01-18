#!/usr/bin/env python3
"""
airspy_adsb_decoder_metrics_logger.py (public-hardened)

Extract decoder metrics from airspy_adsb stats.json or stdout log file.

Metrics:
- peak_signal_dbfs
- signal_dbfs
- noise_floor_dbfs
- messages_per_sec

Features:
- Prefers stats.json (-S output) when available
- Fallback: stdout log parsing with inode+offset state
- Append-only JSONL with crash safety (tail repair + fsync)
- PUBLIC_MODE: paths -> basename only in public output
- State file keeps full path (internal only)

Env:
- ADSB_AIRSPY_STATS_JSON (default: /run/airspy_adsb/stats.json)
- ADSB_AIRSPY_LOGFILE (default: "")
- ADSB_MONITOR_DIR (default: /home/yuki/projects/adsb_monitor)
- ADSB_LOG_DIR (default: $ADSB_MONITOR_DIR/data/logs)
- ADSB_STATE_DIR (default: $ADSB_MONITOR_DIR/data/state)
- ADSB_STATS_FILENAME (default: adsb_airspy_decoder_metrics_1m.jsonl)
- ADSB_PUBLIC_MODE (default: 1)
- ADSB_SCHEMA_VER (default: 1)
- ADSB_CONFIG_ID (optional)
- ADSB_MAX_READ_BYTES (default: 262144)
- ADSB_MERGE_WINDOW_LINES (default: 400)
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# =====================
# Env helpers
# =====================
def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_int(name: str, default: str) -> int:
    v = os.environ.get(name)
    if v in (None, ""):
        return int(default)
    try:
        return int(v)
    except Exception:
        return int(default)


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")


# =====================
# Config
# =====================
PUBLIC_MODE = env_flag("ADSB_PUBLIC_MODE", "1")

BASE_DIR = env_str("ADSB_MONITOR_DIR", "/home/yuki/projects/adsb_monitor")
LOG_DIR = env_str("ADSB_LOG_DIR", os.path.join(BASE_DIR, "data", "logs"))
STATE_DIR = env_str("ADSB_STATE_DIR", os.path.join(BASE_DIR, "data", "state"))

FILENAME_STATS = env_str("ADSB_STATS_FILENAME", "adsb_airspy_decoder_metrics_1m.jsonl")

AIRSPY_STATS_JSON = env_str("ADSB_AIRSPY_STATS_JSON", "/run/airspy_adsb/stats.json").strip()
AIRSPY_LOGFILE = env_str("ADSB_AIRSPY_LOGFILE", "").strip()

SCHEMA_VER = env_int("ADSB_SCHEMA_VER", "1")
CONFIG_ID = env_str("ADSB_CONFIG_ID", "")

MAX_READ_BYTES = env_int("ADSB_MAX_READ_BYTES", "262144")
MERGE_WINDOW_LINES = env_int("ADSB_MERGE_WINDOW_LINES", "400")


# =====================
# Regex patterns
# =====================
RE_PEAK = re.compile(r"\bPeak\b\s*[:=]?\s*([-]?\d+(?:\.\d+)?)", re.IGNORECASE)
RE_RSSI = re.compile(r"\bRSSI\b\s*[:=]?\s*([-]?\d+(?:\.\d+)?)", re.IGNORECASE)
RE_SIGNAL = re.compile(r"\bSignal\b\s*[:=]?\s*([-]?\d+(?:\.\d+)?)", re.IGNORECASE)
RE_NOISE = re.compile(r"\bNoise(?:\s*Floor)?\b\s*[:=]?\s*([-]?\d+(?:\.\d+)?)", re.IGNORECASE)

RE_MSG_RATE_1 = re.compile(
    r"\bMessages?\b\s*(?:/|\s+per\s+)?\s*(?:sec|s)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
RE_MSG_RATE_2 = re.compile(r"\b(?:msg|msgs)\s*/\s*s\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
RE_MSG_RATE_3 = re.compile(r"\bMsgs?\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b.*\b/s\b", re.IGNORECASE)


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

    lines = buf.splitlines(True)
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


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    ensure_dir(path)
    repair_jsonl_tail(path)
    line = json_dumps_strict(record) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def mask_path_basename(path: str) -> str:
    if not path:
        return ""
    return os.path.basename(path) if PUBLIC_MODE else path


def state_path() -> str:
    ensure_dir(os.path.join(STATE_DIR, "dummy"))
    return os.path.join(STATE_DIR, "airspy_adsb_log_offset.json")


def load_state() -> Dict[str, Any]:
    p = state_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    ensure_dir(path)
    tmp = path + ".tmp"
    payload = json_dumps_strict(data)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _to_float(m: Optional[re.Match]) -> Optional[float]:
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


# =====================
# Stats.json reader
# =====================
def read_stats_json(path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"{e.__class__.__name__}: {e}"


def extract_metrics_from_stats(stats: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rssi = stats.get("rssi") if isinstance(stats.get("rssi"), dict) else {}
    noise = stats.get("noise") if isinstance(stats.get("noise"), dict) else {}
    df_counts = stats.get("df_counts") if isinstance(stats.get("df_counts"), list) else []

    rssi_max = rssi.get("max")
    rssi_med = rssi.get("median")
    noise_med = noise.get("median")

    total_msgs = None
    if df_counts:
        try:
            total_msgs = float(sum(float(x) for x in df_counts))
        except Exception:
            total_msgs = None

    # interval hint if exists; else assume 60s
    interval_s = None
    for k in ("interval_s", "interval", "period_s", "period"):
        v = stats.get(k)
        if isinstance(v, (int, float)) and float(v) > 0:
            interval_s = float(v)
            break
    if interval_s is None:
        interval_s = 60.0

    msgps = None if total_msgs is None else (total_msgs / interval_s)

    metrics = {
        "peak_signal_dbfs": rssi_max,
        "signal_dbfs": rssi_med,
        "noise_floor_dbfs": noise_med,
        "messages_per_sec": msgps,
    }
    diag = {
        "stats_keys": list(stats.keys()),
        "interval_s_used": interval_s,
        "df_counts_sum": total_msgs,
        "df_counts_len": len(df_counts),
        "rssi": rssi,
        "noise": noise,
    }
    return metrics, diag


# =====================
# Log reader (offset + inode)
# =====================
def read_new_bytes(logfile: str, prev_inode: Optional[int], prev_offset: int) -> Tuple[bytes, Dict[str, Any]]:
    info: Dict[str, Any] = {"rotated": False, "truncated": False}

    st = os.stat(logfile)
    inode = st.st_ino
    size = st.st_size

    if prev_inode is not None and inode != prev_inode:
        info["rotated"] = True
        prev_offset = 0

    if prev_offset > size:
        info["truncated"] = True
        prev_offset = 0

    to_read = min(MAX_READ_BYTES, max(0, size - prev_offset))

    with open(logfile, "rb") as f:
        f.seek(prev_offset)
        data = f.read(to_read)
        new_offset = prev_offset + len(data)

    info.update({"inode": inode, "size": size, "read_bytes": len(data), "new_offset": new_offset})
    return data, info


def extract_metrics_from_lines(lines: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    peak = sig = noise = msgps = None
    matches: List[Dict[str, Any]] = []
    candidates: List[str] = []

    def pick_msgps(s: str) -> Optional[float]:
        m = RE_MSG_RATE_2.search(s) or RE_MSG_RATE_1.search(s) or RE_MSG_RATE_3.search(s)
        return _to_float(m)

    for line in reversed(lines):
        if any(tok in line for tok in ("Peak", "RSSI", "Noise", "Signal", "msg/s", "msgs/s", "Messages")):
            if len(candidates) < 30:
                candidates.append(line[:300])

        if peak is None:
            v = _to_float(RE_PEAK.search(line))
            if v is not None:
                peak = v
                matches.append({"k": "peak_signal_dbfs", "v": v, "line": line[:300]})

        if sig is None:
            v = _to_float(RE_RSSI.search(line) or RE_SIGNAL.search(line))
            if v is not None:
                sig = v
                matches.append({"k": "signal_dbfs", "v": v, "line": line[:300]})

        if noise is None:
            v = _to_float(RE_NOISE.search(line))
            if v is not None:
                noise = v
                matches.append({"k": "noise_floor_dbfs", "v": v, "line": line[:300]})

        if msgps is None:
            v = pick_msgps(line)
            if v is not None:
                msgps = v
                matches.append({"k": "messages_per_sec", "v": v, "line": line[:300]})

        if peak is not None and sig is not None and noise is not None and msgps is not None:
            break

    metrics = {
        "peak_signal_dbfs": peak,
        "signal_dbfs": sig,
        "noise_floor_dbfs": noise,
        "messages_per_sec": msgps,
    }
    diag = {"matches": matches, "candidates": list(reversed(candidates))}
    return metrics, diag


# =====================
# Main
# =====================
def main() -> int:
    ts = time.time()
    out_path = os.path.join(LOG_DIR, FILENAME_STATS)

    # Prefer stats.json
    if AIRSPY_STATS_JSON:
        stats, err = read_stats_json(AIRSPY_STATS_JSON)
        if isinstance(stats, dict):
            metrics, diag = extract_metrics_from_stats(stats)
            got_any = any(v is not None for v in metrics.values())
            got_all = all(v is not None for v in metrics.values())

            record: Dict[str, Any] = {
                "ts": ts,
                "ts_iso_utc": utc_iso_z(ts),
                "src": "decoder_metrics",
                "producer": "airspy_adsb",
                "schema_ver": SCHEMA_VER,
                "config_id": CONFIG_ID or None,
                "stats_json": mask_path_basename(AIRSPY_STATS_JSON),
                **metrics,
                "status": {"mode": "stats_json", "got_any": got_any, "got_all": got_all},
                "diag": diag,
            }
            append_jsonl(out_path, record)

            if got_any:
                print(
                    f"OK(stats, partial={not got_all}): "
                    f"Peak={record['peak_signal_dbfs']} "
                    f"Signal={record['signal_dbfs']} "
                    f"Noise={record['noise_floor_dbfs']} "
                    f"Msg/s={record['messages_per_sec']}"
                )
            else:
                print("NO METRICS FOUND in stats.json (recorded diagnostics).")
            return 0

        if err:
            record = {
                "ts": ts,
                "ts_iso_utc": utc_iso_z(ts),
                "src": "decoder_metrics",
                "producer": "airspy_adsb",
                "schema_ver": SCHEMA_VER,
                "config_id": CONFIG_ID or None,
                "stats_json": mask_path_basename(AIRSPY_STATS_JSON),
                "status": {"mode": "stats_json", "error": True},
                "error": err,
            }
            append_jsonl(out_path, record)
            print("ERROR: cannot read stats.json (recorded).")
            # continue to logfile fallback if configured

    # Fallback: logfile
    if not AIRSPY_LOGFILE:
        record = {
            "ts": ts,
            "ts_iso_utc": utc_iso_z(ts),
            "src": "decoder_metrics",
            "producer": "airspy_adsb",
            "schema_ver": SCHEMA_VER,
            "config_id": CONFIG_ID or None,
            "status": {"mode": "logfile", "error": True},
            "error": "ADSB_AIRSPY_LOGFILE is not set",
        }
        append_jsonl(out_path, record)
        print("ERROR: ADSB_AIRSPY_LOGFILE is not set (recorded).")
        return 0

    st = load_state()
    prev_inode = st.get("inode")
    prev_offset = st.get("offset", 0)
    if not isinstance(prev_inode, int):
        prev_inode = None
    if not isinstance(prev_offset, int):
        prev_offset = 0

    try:
        data, info = read_new_bytes(AIRSPY_LOGFILE, prev_inode, prev_offset)
    except Exception as e:
        record = {
            "ts": ts,
            "ts_iso_utc": utc_iso_z(ts),
            "src": "decoder_metrics",
            "producer": "airspy_adsb",
            "schema_ver": SCHEMA_VER,
            "config_id": CONFIG_ID or None,
            "logfile": mask_path_basename(AIRSPY_LOGFILE),
            "status": {"mode": "logfile", "error": True},
            "error": f"{e.__class__.__name__}: {e}",
        }
        append_jsonl(out_path, record)
        print("ERROR: cannot read logfile (recorded).")
        return 0

    text = data.decode("utf-8", errors="replace")
    new_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    scan_lines = new_lines[-MERGE_WINDOW_LINES:] if len(new_lines) > MERGE_WINDOW_LINES else new_lines

    metrics, diag = extract_metrics_from_lines(scan_lines)
    got_any = any(v is not None for v in metrics.values())
    got_all = all(v is not None for v in metrics.values())

    record = {
        "ts": ts,
        "ts_iso_utc": utc_iso_z(ts),
        "src": "decoder_metrics",
        "producer": "airspy_adsb",
        "schema_ver": SCHEMA_VER,
        "config_id": CONFIG_ID or None,
        "logfile": mask_path_basename(AIRSPY_LOGFILE),
        "read": {
            "inode_prev": prev_inode,
            "offset_prev": prev_offset,
            **info,
            "new_lines": len(new_lines),
            "scanned_lines": len(scan_lines),
        },
        **metrics,
        "status": {"mode": "logfile", "got_any": got_any, "got_all": got_all},
        "diag": diag,
    }

    append_jsonl(out_path, record)

    # Persist state (internal only; keep full path)
    try:
        atomic_write_json(state_path(), {
            "ts": ts,
            "ts_iso_utc": utc_iso_z(ts),
            "logfile": AIRSPY_LOGFILE,
            "inode": info.get("inode"),
            "offset": info.get("new_offset"),
        })
    except Exception as e:
        sys.stderr.write(f"[airspy_adsb_decoder_metrics] write_state failed: {e.__class__.__name__}: {e}\n")

    if got_any:
        print(
            f"OK(partial={not got_all}): "
            f"Peak={record['peak_signal_dbfs']} "
            f"Signal={record['signal_dbfs']} "
            f"Noise={record['noise_floor_dbfs']} "
            f"Msg/s={record['messages_per_sec']}"
        )
    else:
        print("NO METRICS FOUND (recorded diagnostics).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
