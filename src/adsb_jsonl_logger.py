#!/usr/bin/env python3
# adsb_jsonl_logger.py (publish-hardened)
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, Optional


def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")


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
    JSONL末尾が壊れていたら、最後の正常行までtruncateして修復する。
    - 電源断/強制終了で「最後の1行だけ途中」になったケースを想定
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


def append_jsonl(path: str, record: Dict[str, Any], fsync: bool = True) -> None:
    ensure_dir(path)
    # strict JSON
    line = (json_dumps_strict(record) + "\n").encode("utf-8")

    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
        if fsync:
            os.fsync(fd)
    finally:
        os.close(fd)


def build_meta() -> Dict[str, Any]:
    return {
        "site_id": env_str("ADSB_SITE_ID", "unknown"),
        "antenna_id": env_str("ADSB_ANTENNA_ID", "unknown"),
        "dongle": env_str("ADSB_DONGLE", "unknown"),
        "lna": env_str("ADSB_LNA", "unknown"),
        "schema_ver": int(env_str("ADSB_SCHEMA_VER", "1")),
    }


def main() -> int:
    public_mode = env_flag("ADSB_PUBLIC_MODE", "1")

    # 入力：readsb stats の場所（環境で差し替え）
    readsb_stats = env_str("READSB_STATS_JSON", "/run/readsb/stats.json")

    # 出力：日別JSONL（例）
    base_dir = env_str("ADSB_BASE_DIR", "/home/yuki/publish/adsb-eval")
    log_dir = env_str("ADSB_LOG_DIR", os.path.join(base_dir, "data", "logs"))
    out_path = env_str("ADSB_STATS_JSONL", os.path.join(log_dir, "stats_history.jsonl"))

    ts = time.time()
    meta = build_meta()

    # 末尾修復（安全側）
    repair_jsonl_tail(out_path)

    try:
        with open(readsb_stats, "r", encoding="utf-8") as f:
            stats = json.load(f)
        if not isinstance(stats, dict):
            raise ValueError("readsb stats.json is not an object")
    except Exception as e:
        # エラーもJSONLに残す（公開でも壊れない形）
        append_jsonl(out_path, {"ts": ts, "src": "readsb_stats", "meta": meta, "error": str(e)})
        return 1

    rec: Dict[str, Any] = {
        "ts": ts,
        "src": "readsb_stats",
        "meta": meta,
        "stats": stats,
    }

    # public_mode: 座標やパスっぽいものが混入しても落とす（最低限）
    # stats.jsonの構造は環境差があるので、ここは「よくあるキー」を落とすだけに留める
    if public_mode and isinstance(rec.get("stats"), dict):
        s = rec["stats"]
        # 例：site/lat/lon系のキーがあれば除去
        for k in ("lat", "lon", "site", "receiverLat", "receiverLon"):
            if k in s:
                s.pop(k, None)

    append_jsonl(out_path, rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
