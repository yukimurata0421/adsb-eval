from __future__ import annotations

import json
import math
from typing import Any


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
