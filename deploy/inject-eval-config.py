"""Atomic HE_EVAL_* .env injection for the deploy pipeline (server side).

The workflow pipes ``KEY <base64>`` lines to this script over SSH. Each value
is decoded and merged into ``/opt/harness/shared/.env`` — existing keys are
replaced in place, missing keys are appended, so reruns are idempotent. The
whole file is rewritten through a temporary file plus ``os.replace`` (atomic,
no half-written state). Decode failures and values containing newlines warn
and skip instead of blocking the release; the target file keeps mode 0600.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile

TARGET = "/opt/harness/shared/.env"


def main() -> int:
    """Decode stdin entries and rewrite the env file atomically."""
    decoded: dict[str, str] = {}
    for line in sys.stdin.read().splitlines():
        key, _, encoded = line.strip().partition(" ")
        if not key or not encoded:
            continue
        try:
            value = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            print(f"::warning::{key} base64 解码失败，跳过该键（保持服务器现状）")
            continue
        if "\n" in value or "\r" in value:
            print(f"::warning::{key} 解码结果含换行，跳过该键（保持服务器现状）")
            continue
        decoded[key] = value
    if not decoded:
        print("::warning::无可用 HE_EVAL_* 配置，.env 保持不变")
        return 0
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    lines: list[str] = []
    if os.path.exists(TARGET):
        with open(TARGET, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    updated: list[str] = []
    seen: set[str] = set()
    for line in lines:
        name = line.split("=", 1)[0] if line and not line.startswith("#") else None
        if name in decoded:
            updated.append(f"{name}={decoded[name]}")
            seen.add(name)
        else:
            updated.append(line)
    for key, value in decoded.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(TARGET), prefix=".env.", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(updated).rstrip("\n") + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, TARGET)
    print(f"injected {len(decoded)} HE_EVAL_* entries into {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
