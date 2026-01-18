from __future__ import annotations

import os
import sys
from typing import Optional


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def env_int(name: str, default: str) -> int:
    v = os.environ.get(name)
    if v is None:
        return int(default)
    try:
        return int(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return int(default)


def env_float(name: str, default: str) -> float:
    """
    互換維持：
    - default は str 前提（従来通り）
    - env未設定なら float(default)
    - env不正なら warnして float(default)
    """
    v = os.environ.get(name)
    if v is None:
        return float(default)
    try:
        return float(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default}")
        return float(default)


def env_float_opt(name: str, default: Optional[str] = None) -> Optional[float]:
    """
    None許容の Optional float getter（追加・互換非破壊）

    - env未設定/空文字:
        default が None -> None を返す
        default が str -> float(default) を返す
    - envが不正:
        warnして default にフォールバック（defaultがNoneならNone）
    - envが正常:
        float(env) を返す
    """
    v = os.environ.get(name)

    # 未設定 or 空文字は「未指定」として扱う
    if v is None or v.strip() == "":
        if default is None:
            return None
        return float(default)

    try:
        return float(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default!r}")
        if default is None:
            return None
        return float(default)


def env_flag(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default)
    v = (v or "").strip().lower()
    return v in ("1", "true", "yes", "on")

def env_float_opt(name: str, default: Optional[str] = None) -> Optional[float]:
    """
    None許容の Optional float getter（追加・互換非破壊）

    - env未設定/空文字:
        default が None -> None を返す
        default が str -> float(default) を返す
    - envが不正:
        warnして default にフォールバック（defaultがNoneならNone）
    - envが正常:
        float(env) を返す
    """
    v = os.environ.get(name)

    if v is None or v.strip() == "":
        if default is None:
            return None
        return float(default)

    try:
        return float(v)
    except Exception:
        warn(f"{name} invalid ({v!r}), fallback={default!r}")
        if default is None:
            return None
        return float(default)
