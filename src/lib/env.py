from __future__ import annotations

import os
import sys
from typing import Optional, Callable, TypeVar

T = TypeVar("T")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def _get_env(
    name: str,
    cast: Callable[[str], T],
    default: Optional[T],
    *,
    allow_none: bool,
) -> Optional[T]:
    v = os.environ.get(name)

    if v in (None, ""):
        return None if allow_none else default

    try:
        return cast(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return None if allow_none else default


def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_int(name: str, default: str) -> int:
    return int(
        _get_env(
            name,
            int,
            int(default),
            allow_none=False,
        )
    )


def env_float(name: str, default: str) -> float:
    return float(
        _get_env(
            name,
            float,
            float(default),
            allow_none=False,
        )
    )


def env_int_opt(name: str) -> Optional[int]:
    return _get_env(
        name,
        int,
        None,
        allow_none=True,
    )


def env_float_opt(name: str) -> Optional[float]:
    return _get_env(
        name,
        float,
        None,
        allow_none=True,
    )


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")
