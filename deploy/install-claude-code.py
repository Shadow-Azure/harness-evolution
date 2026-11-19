#!/usr/bin/env python3
"""Install and configure Claude Code on the production server.

Runs as the ``deploy`` user over SSH. The runner uploads an official
``claude-code`` deb; this script extracts it into a versioned prefix, verifies
the binary, atomically switches ``~/.local/bin/claude``, and writes the model
configuration under ``~/.claude``.

Secret values arrive as ``KEY <base64>`` lines on stdin so they never appear in
SSH command lines. ``CLAUDE_CODE_MODEL`` and ``CLAUDE_CODE_API_KEY`` are
required; ``CLAUDE_CODE_BASE_URL`` is optional. The key is stored in a 0600
file and exposed to Claude Code through ``apiKeyHelper``; it never enters
``settings.json`` or a subprocess environment.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED_KEYS = ("CLAUDE_CODE_MODEL", "CLAUDE_CODE_API_KEY")
MINIMAX_AUTO_COMPACT = "524288"
MINIMAX_EFFORT = "max"
DEFAULT_PREFIX = "/opt/harness/shared/claude-code"


def decode_entries(lines: list[str]) -> dict[str, str]:
    """Decode ``KEY <base64>`` lines into a mapping.

    Raises:
        ValueError: for a malformed line, invalid base64, or a value with a
            newline; secrets must be injected whole or not at all.
    """
    decoded: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        key, separator, encoded = line.partition(" ")
        if not separator or not key or not encoded:
            raise ValueError("stdin entries must be KEY <base64>")
        try:
            value = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError(f"{key}: base64 decode failed") from error
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key}: decoded value contains a newline")
        decoded[key] = value
    return decoded


def normalize_version(version: str) -> str:
    """Return the upstream version without a leading ``v`` or Debian revision."""
    value = version.strip()
    if value.startswith("v"):
        value = value[1:]
    return re.sub(r"-\d+$", "", value)


def cli_version(output: str) -> str | None:
    """Extract ``2.1.311`` from ``2.1.311 (Claude Code)``."""
    match = re.search(r"(\d+\.\d+\.\d+)", output)
    return match.group(1) if match else None


def validate_base_url(value: str | None) -> str | None:
    """Validate an optional Anthropic-compatible endpoint.

    Raises:
        ValueError: for a non-http(s) URL, embedded credentials, or whitespace.
    """
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if any(character.isspace() or ord(character) < 0x20 for character in url):
        raise ValueError("CLAUDE_CODE_BASE_URL must not contain whitespace or control characters")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("CLAUDE_CODE_BASE_URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("CLAUDE_CODE_BASE_URL must not embed credentials")
    return url


def build_settings(model: str, base_url: str | None, home: Path) -> dict[str, object]:
    """Build the user ``settings.json`` payload.

    For a custom gateway, the Claude model aliases resolve to the configured
    model so background requests do not fall back to a model the gateway does
    not serve. MiniMax additionally receives its documented 1M-window and
    effort defaults.
    """
    settings: dict[str, object] = {
        "model": model,
        "apiKeyHelper": str((home / ".claude" / "api-key.sh").resolve()),
        "env": {"DISABLE_AUTOUPDATER": "1"},
    }
    if base_url:
        env = settings["env"]
        assert isinstance(env, dict)
        env["ANTHROPIC_BASE_URL"] = base_url
        for alias in (
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        ):
            env[alias] = model
        if "minimax" in base_url.lower() or model.lower().startswith("minimax-"):
            env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = MINIMAX_AUTO_COMPACT
            env["CLAUDE_CODE_EFFORT_LEVEL"] = MINIMAX_EFFORT
    return settings


def write_atomic(path: Path, content: str, mode: int) -> None:
    """Write ``content`` to ``path`` through a same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def install_from_deb(deb: Path, version: str, prefix: Path, home: Path) -> Path:
    """Extract a deb into ``prefix/version`` and return its ``claude`` binary."""
    prefix.mkdir(parents=True, exist_ok=True)
    target = prefix / version
    binary = target / "usr/bin/claude"
    if binary.exists():
        existing = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HOME": str(home)},
        )
        if existing.returncode == 0:
            return binary
        shutil.rmtree(target, ignore_errors=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=str(prefix)))
    try:
        subprocess.run(
            ["dpkg-deb", "-x", str(deb), str(staging)],
            check=True,
            timeout=300,
        )
        candidate = staging / "usr/bin/claude"
        if not candidate.exists():
            raise RuntimeError("deb does not contain usr/bin/claude")
        check = subprocess.run(
            [str(candidate), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HOME": str(home)},
        )
        if check.returncode != 0:
            raise RuntimeError(f"unpacked claude failed --version: {check.stderr.strip()}")
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return binary


def switch_launcher(binary: Path, home: Path) -> Path:
    """Atomically point ``~/.local/bin/claude`` at ``binary``."""
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "claude"
    temporary = bin_dir / f".claude.{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    os.symlink(str(binary), str(temporary))
    os.replace(temporary, launcher)
    return launcher


def version_sort_key(path: Path) -> tuple[int, ...]:
    """Sort version directory names numerically (e.g. 2.1.311-1)."""
    return tuple(int(part) for part in re.split(r"[.\-]", path.name) if part.isdigit())


def clean_versions(prefix: Path, keep: int) -> None:
    """Remove old version directories, keeping the newest ``keep`` versions."""
    if keep < 1 or not prefix.exists():
        return
    versions = [
        entry
        for entry in prefix.iterdir()
        if entry.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+-\d+", entry.name)
    ]
    versions.sort(key=version_sort_key, reverse=True)
    for old in versions[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def configure(entries: dict[str, str], home: Path) -> Path:
    """Write settings, the API-key file, and the apiKeyHelper script."""
    model = entries.get("CLAUDE_CODE_MODEL", "").strip()
    api_key = entries.get("CLAUDE_CODE_API_KEY", "")
    if not model or not api_key:
        raise ValueError("CLAUDE_CODE_MODEL and CLAUDE_CODE_API_KEY are required")
    base_url = validate_base_url(entries.get("CLAUDE_CODE_BASE_URL"))

    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(claude_dir, 0o700)

    settings = build_settings(model, base_url, home)
    write_atomic(claude_dir / "settings.json", json.dumps(settings, indent=2, ensure_ascii=False) + "\n", 0o600)
    write_atomic(claude_dir / "api-key", api_key, 0o600)

    helper = claude_dir / "api-key.sh"
    write_atomic(
        helper,
        "#!/bin/sh\n" + f"cat {shlex.quote(str(claude_dir / 'api-key'))}\n",
        0o700,
    )
    return claude_dir / "settings.json"


def read_current_version(home: Path) -> str | None:
    """Return the active launcher version, or ``None`` when it is absent/broken."""
    launcher = home / ".local" / "bin" / "claude"
    if not launcher.exists():
        return None
    check = subprocess.run(
        [str(launcher), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "HOME": str(home)},
    )
    return cli_version(check.stdout) if check.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    """Install/configure Claude Code from the uploaded deb and stdin secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deb", help="uploaded claude-code .deb; omit to configure only")
    parser.add_argument("--version", help="target apt version, e.g. 2.1.311-1")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--home", default=os.environ.get("HOME", ""))
    parser.add_argument("--keep", type=int, default=2)
    args = parser.parse_args(argv)

    try:
        home = Path(args.home).expanduser()
        if not home.is_dir():
            raise ValueError(f"HOME is not a directory: {home}")
        entries = decode_entries(sys.stdin.read().splitlines())
        target = normalize_version(args.version) if args.version else read_current_version(home)
        if not target:
            raise ValueError("no active claude and no --version/--deb supplied")

        if args.deb:
            binary = install_from_deb(Path(args.deb), args.version or target, Path(args.prefix), home)
            candidate = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "HOME": str(home)},
            )
            installed = cli_version(candidate.stdout) if candidate.returncode == 0 else None
            if installed != target:
                raise RuntimeError(f"installed version {installed!r} does not match target {target!r}")
        else:
            current = read_current_version(home)
            if current != target:
                raise RuntimeError(f"active version {current!r} does not match target {target!r}")

        configure(entries, home)
        launcher = switch_launcher(binary if args.deb else (home / ".local" / "bin" / "claude").resolve(), home)
        check = subprocess.run(
            [str(launcher), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HOME": str(home)},
        )
        if check.returncode != 0:
            raise RuntimeError(f"launcher verification failed: {check.stderr.strip()}")
        clean_versions(Path(args.prefix), args.keep)
        print(f"claude-code: {check.stdout.strip()}")
        print(f"settings: {home / '.claude' / 'settings.json'}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"::error::Claude Code setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
