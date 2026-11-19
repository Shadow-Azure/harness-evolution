"""Atomic ``.env`` injection for the deploy pipeline (server side).

The workflow pipes ``KEY <base64>`` lines to this script over SSH. Each value
is decoded and merged into ``/opt/harness/shared/.env`` — existing keys are
replaced in place, missing keys are appended, so reruns are idempotent. The
whole file is rewritten through a temporary file plus ``os.replace`` (atomic,
no half-written state). A ``--backup`` path snapshots the pre-injection file
so ``release.sh`` can restore it when a deploy fails.

Decode failures, invalid key names, and values containing newlines warn and
skip instead of blocking the release; the target file keeps mode 0600.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import shutil
import sys
import tempfile

TARGET = "/opt/harness/shared/.env"
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def decode_entries(stdin: str) -> dict[str, str]:
    """Decode ``KEY value`` lines, warning and skipping unusable entries."""
    decoded: dict[str, str] = {}
    for line in stdin.splitlines():
        key, _, encoded = line.strip().partition(" ")
        if not key or not encoded:
            continue
        if not _ENV_NAME.fullmatch(key):
            print(f"::warning::{key} 不是合法的环境变量名，跳过该键（保持服务器现状）")
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
    return decoded


def backup_target(path: str | None) -> None:
    """Copy the current env file to ``path`` before the rewrite."""
    if not path:
        return
    if not os.path.exists(TARGET):
        print(f"::warning::{TARGET} 尚不存在，跳过备份 {path}")
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    shutil.copy2(TARGET, path)
    os.chmod(path, 0o600)
    print(f"backed up {TARGET} to {path}")


def rewrite_env(decoded: dict[str, str]) -> None:
    """Merge ``decoded`` into the env file and replace it atomically."""
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


def main(argv: list[str] | None = None) -> int:
    """Decode stdin entries, back up the env file, and rewrite it atomically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", help="预注入 .env 备份路径")
    args = parser.parse_args(argv)
    decoded = decode_entries(sys.stdin.read())
    if not decoded:
        print("::warning::无可用配置，.env 保持不变")
        return 0
    try:
        backup_target(args.backup)
        rewrite_env(decoded)
    except OSError as exc:
        print(f"::error::写入 {TARGET} 失败：{exc}", file=sys.stderr)
        return 2
    print(f"injected {len(decoded)} config entries into {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
