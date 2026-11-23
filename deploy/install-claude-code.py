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
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED_KEYS = ("CLAUDE_CODE_MODEL", "CLAUDE_CODE_API_KEY")
MINIMAX_AUTO_COMPACT = "524288"
MINIMAX_EFFORT = "max"
DEFAULT_PREFIX = "/opt/harness/shared/claude-code"
SHARED_CONFIG_DIR = "config"
"""Subdirectory holding the service-readable settings."""
SHARED_SETTINGS_MODE = 0o644
"""Settings are readable by the service account and contain no credentials."""


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
        ValueError: for a non-https URL (except loopback), embedded credentials,
            or whitespace.
    """
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if any(character.isspace() or ord(character) < 0x20 for character in url):
        raise ValueError(
            "CLAUDE_CODE_BASE_URL must not contain whitespace or control characters"
        )
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("CLAUDE_CODE_BASE_URL must be an absolute https URL")
    if parsed.scheme == "http" and (parsed.hostname or "") not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError(
            "CLAUDE_CODE_BASE_URL must use https (http is allowed only for loopback)"
        )
    if parsed.username or parsed.password:
        raise ValueError("CLAUDE_CODE_BASE_URL must not embed credentials")
    return url


def _gateway_env(model: str, base_url: str | None) -> dict[str, str]:
    """Build the shared model/gateway environment for one settings payload.

    For a custom gateway, the Claude model aliases resolve to the configured
    model so background requests do not fall back to a model the gateway does
    not serve. MiniMax additionally receives its documented 512K auto-compact
    window and effort defaults.
    """
    env = {"DISABLE_AUTOUPDATER": "1"}
    if base_url:
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
    return env


def build_settings(model: str, base_url: str | None, home: Path) -> dict[str, object]:
    """Build the deploy user's ``settings.json`` payload.

    The key remains in a 0600 ``api-key`` file behind ``apiKeyHelper`` for the
    deploy user's own CLI; the service uses the shared settings below instead.
    """
    return {
        "model": model,
        "apiKeyHelper": str((home / ".claude" / "api-key.sh").resolve()),
        "env": _gateway_env(model, base_url),
    }


def build_shared_settings(model: str, base_url: str | None) -> dict[str, object]:
    """Build the service-readable settings payload without any credential.

    The service account authenticates through ``ANTHROPIC_API_KEY`` in the
    0600 deployment environment, so this file can stay 0644 and contain only
    the model, endpoint, aliases, and MiniMax tuning.
    """
    return {"model": model, "env": _gateway_env(model, base_url)}


def write_atomic(
    path: Path, content: str, mode: int, *, parent_mode: int = 0o700
) -> None:
    """Write ``content`` to ``path`` through a same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=parent_mode)
    os.chmod(path.parent, parent_mode)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent), text=True
    )
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
            raise RuntimeError(
                f"unpacked claude failed --version: {check.stderr.strip()}"
            )
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


def clean_versions(prefix: Path, keep: int, protected: Path | None = None) -> None:
    """Remove old version directories, keeping the newest ``keep`` and ``protected``."""
    if keep < 1 or not prefix.exists():
        return
    versions = [
        entry
        for entry in prefix.iterdir()
        if entry.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+-\d+", entry.name)
    ]
    versions.sort(key=version_sort_key, reverse=True)
    kept: list[Path] = []
    if protected is not None and protected in versions:
        kept.append(protected)
    for version in versions:
        if version in kept:
            continue
        if len(kept) >= keep:
            break
        kept.append(version)
    for old in versions:
        if old not in kept:
            shutil.rmtree(old, ignore_errors=True)


def configure(entries: dict[str, str], home: Path) -> Path:
    """Write settings, the API-key file, the apiKeyHelper, and onboarding state."""
    model = entries.get("CLAUDE_CODE_MODEL", "").strip()
    api_key = entries.get("CLAUDE_CODE_API_KEY", "")
    if not model or not api_key:
        raise ValueError("CLAUDE_CODE_MODEL and CLAUDE_CODE_API_KEY are required")
    base_url = validate_base_url(entries.get("CLAUDE_CODE_BASE_URL"))
    if model.lower().startswith("minimax-") and not base_url:
        raise ValueError("MiniMax models require CLAUDE_CODE_BASE_URL")

    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(claude_dir, 0o700)

    onboarding_path = home / ".claude.json"
    onboarding: dict[str, object] = {}
    if onboarding_path.exists():
        try:
            loaded = json.loads(onboarding_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                "~/.claude.json is not valid JSON; fix or remove it first"
            ) from error
        if not isinstance(loaded, dict):
            raise ValueError("~/.claude.json must contain a JSON object")
        onboarding = loaded
    onboarding["hasCompletedOnboarding"] = True

    settings = build_settings(model, base_url, home)
    write_atomic(
        claude_dir / "settings.json",
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        0o600,
    )
    write_atomic(claude_dir / "api-key", api_key, 0o600)

    helper = claude_dir / "api-key.sh"
    write_atomic(
        helper,
        "#!/bin/sh\n" + f"cat {shlex.quote(str(claude_dir / 'api-key'))}\n",
        0o700,
    )
    write_atomic(
        onboarding_path,
        json.dumps(onboarding, indent=2, ensure_ascii=False) + "\n",
        0o600,
    )
    return claude_dir / "settings.json"


def shared_settings_path(prefix: Path) -> Path:
    """Return the service-readable settings path under the install prefix."""
    return prefix / SHARED_CONFIG_DIR / "settings.json"


def configure_shared(entries: dict[str, str], prefix: Path) -> Path:
    """Write the 0644 service settings next to the versioned CLI.

    The settings contain no API key or ``apiKeyHelper``: the service reads the
    key from ``ANTHROPIC_API_KEY`` in its 0600 environment file. The directory
    is 0755 so the unprivileged service account can traverse it.
    """
    model = entries.get("CLAUDE_CODE_MODEL", "").strip()
    api_key = entries.get("CLAUDE_CODE_API_KEY", "")
    if not model or not api_key:
        raise ValueError("CLAUDE_CODE_MODEL and CLAUDE_CODE_API_KEY are required")
    base_url = validate_base_url(entries.get("CLAUDE_CODE_BASE_URL"))
    if model.lower().startswith("minimax-") and not base_url:
        raise ValueError("MiniMax models require CLAUDE_CODE_BASE_URL")
    path = shared_settings_path(prefix)
    payload = build_shared_settings(model, base_url)
    write_atomic(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        SHARED_SETTINGS_MODE,
        parent_mode=0o755,
    )
    return path


def switch_current(binary: Path, prefix: Path) -> Path:
    """Atomically point ``prefix/current`` at the binary's version directory."""
    version_dir = binary.parents[2]
    if not version_dir.is_dir() or version_dir.parent != prefix:
        raise ValueError(f"binary is not inside a version directory: {binary}")
    current = prefix / "current"
    temporary = prefix / f".current.{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    os.symlink(version_dir.name, temporary)
    os.replace(temporary, current)
    return current


def _other_access(path: Path, mask: int) -> bool:
    """Return whether an unprivileged non-owner can traverse/read ``path``."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    return bool(mode & mask)


def preflight_shared_access(binary: Path, settings: Path, prefix: Path) -> None:
    """Fail before switching ``current`` when the service cannot use the assets.

    The installer runs as ``deploy`` and cannot impersonate ``harness`` without
    root, so this checks the portable subset: the binary has the other-execute
    bit, the settings have the other-read bit, and the prefix/config directories
    are other-traversable. A failure aborts before the symlink switches.
    """
    errors: list[str] = []
    if not binary.is_file():
        errors.append(f"binary is missing: {binary}")
    elif not _other_access(binary, 0o001):
        errors.append(f"binary is not executable by the service user: {binary}")
    if not settings.is_file():
        errors.append(f"shared settings are missing: {settings}")
    elif not _other_access(settings, 0o004):
        errors.append(
            f"shared settings are not readable by the service user: {settings}"
        )
    for directory in (prefix, settings.parent):
        if not _other_access(directory, 0o001):
            errors.append(
                f"directory is not traversable by the service user: {directory}"
            )
    if errors:
        raise RuntimeError("; ".join(errors))


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
    parser.add_argument(
        "--deb", help="uploaded claude-code .deb; omit to configure only"
    )
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
        target = (
            normalize_version(args.version)
            if args.version
            else read_current_version(home)
        )
        if not target:
            raise ValueError("no active claude and no --version/--deb supplied")

        if args.deb:
            binary = install_from_deb(
                Path(args.deb), args.version or target, Path(args.prefix), home
            )
            candidate = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "HOME": str(home)},
            )
            installed = (
                cli_version(candidate.stdout) if candidate.returncode == 0 else None
            )
            if installed != target:
                raise RuntimeError(
                    f"installed version {installed!r} does not match target {target!r}"
                )
        else:
            current = read_current_version(home)
            if current != target:
                raise RuntimeError(
                    f"active version {current!r} does not match target {target!r}"
                )

        active_binary = (
            binary if args.deb else (home / ".local" / "bin" / "claude").resolve()
        )
        prefix = Path(args.prefix)
        configure(entries, home)
        shared = configure_shared(entries, prefix)
        # The preflight runs before ``current`` switches, so a broken shared
        # asset never becomes the path the service resolves at startup.
        preflight_shared_access(active_binary, shared, prefix)
        current = switch_current(active_binary, prefix)
        launcher = switch_launcher(active_binary, home)
        stable_binary = current / "usr/bin/claude"
        check = subprocess.run(
            [str(stable_binary), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HOME": str(home)},
        )
        if check.returncode != 0:
            raise RuntimeError(f"launcher verification failed: {check.stderr.strip()}")
        clean_versions(prefix, args.keep, protected=active_binary.parents[2])
        after_cleanup = subprocess.run(
            [str(stable_binary), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "HOME": str(home)},
        )
        if after_cleanup.returncode != 0:
            raise RuntimeError(
                f"launcher verification after cleanup failed: {after_cleanup.stderr.strip()}"
            )
        if args.deb:
            Path(args.deb).unlink(missing_ok=True)
        print(f"claude-code: {check.stdout.strip()}")
        print(f"settings: {home / '.claude' / 'settings.json'}")
        print(f"shared-settings: {shared}")
        print(f"stable-binary: {stable_binary}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"::error::Claude Code setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
