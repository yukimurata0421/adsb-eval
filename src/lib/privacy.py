from __future__ import annotations

import os
from typing import Dict, Optional


def mask_path_basename(path: str, public_mode: bool) -> str:
    """Recommended: keep only basename (debuggable but not leaking full path)."""
    if not path:
        return ""
    return os.path.basename(path) if public_mode else path


def build_site_block(site_id: str, public_mode: bool, lat: Optional[float], lon: Optional[float]) -> Dict[str, object]:
    if public_mode:
        return {"id": site_id}
    d: Dict[str, object] = {"id": site_id}
    if lat is not None:
        d["lat"] = lat
    if lon is not None:
        d["lon"] = lon
    return d
