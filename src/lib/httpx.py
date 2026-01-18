from __future__ import annotations

from typing import Any, Dict, Optional

import requests


def fetch_json(session: requests.Session, url: str, *, timeout_s: int = 5) -> Optional[Dict[str, Any]]:
    """
    - returns dict only
    - non-200 -> None
    - any exception -> None
    """
    try:
        r = session.get(url, timeout=timeout_s)
        if r.status_code != 200:
            return None
        j = r.json()
        return j if isinstance(j, dict) else None
    except Exception:
        return None
