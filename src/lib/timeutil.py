from __future__ import annotations

from datetime import datetime, timezone

import time


def utc_iso_z(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def unix_now() -> float:
    """
    Unix epoch seconds (float).
    既存libとの互換を壊さないためのエイリアス関数。
    """
    return time.time()