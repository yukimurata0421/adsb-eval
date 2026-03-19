#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v in (None, ""):
        return default
    try:
        return int(v)
    except Exception:
        return default


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output or str(e)
    except Exception as e:
        return f"{e.__class__.__name__}: {e}"


def _tail(text: str, lines: int) -> str:
    if lines <= 0:
        return ""
    xs = text.splitlines()
    return "\n".join(xs[-lines:])


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: systemd_failure_notify.py <unit>", file=sys.stderr)
        return 2

    unit = sys.argv[1]
    url = (
        os.environ.get("ADSB_FAILURE_WEBHOOK_URL")
        or os.environ.get("DISCORD_WEBHOOK_URL")
        or ""
    ).strip()
    if not url:
        print("ADSB_FAILURE_WEBHOOK_URL (or DISCORD_WEBHOOK_URL) missing", file=sys.stderr)
        return 2

    lines = _env_int("LINES", 40)
    max_chars = _env_int("MAX_CHARS", 1800)
    cooldown = _env_int("NOTIFY_COOLDOWN_SECONDS", 3600)
    state_dir = os.environ.get("NOTIFY_STATE_DIR") or os.path.join(
        os.environ.get("ADSB_STATE_DIR", "/tmp/adsb-eval"),
        "notify",
    )
    os.makedirs(state_dir, exist_ok=True)

    stamp_name = f"notify_{unit}".replace("/", "_")
    stamp_path = os.path.join(state_dir, stamp_name + ".stamp")
    now = time.time()

    try:
        last_ts = os.path.getmtime(stamp_path)
    except FileNotFoundError:
        last_ts = 0.0
    except Exception:
        last_ts = 0.0

    if now - last_ts < cooldown:
        return 0

    host = _run(["hostname"]).strip()
    status = _tail(_run(["systemctl", "--no-pager", "--full", "status", unit]), lines)
    journal = _tail(_run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager"]), lines)

    msg = (
        ":rotating_light: systemd failure\n"
        f"host: {host}\n"
        f"unit: {unit}\n\n"
        f"status:\n```{status}```\n"
        f"journal:\n```{journal}```"
    )
    if len(msg) > max_chars:
        msg = msg[: max_chars - 20] + "\n...(truncated)..."

    payload = json.dumps({"content": msg}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "adsb-eval/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        _ = resp.read()

    with open(stamp_path, "w", encoding="utf-8") as f:
        f.write(str(int(now)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
