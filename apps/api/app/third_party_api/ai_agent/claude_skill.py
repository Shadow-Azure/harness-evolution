"""Non-interactive Claude Code invocation in a case-scoped filesystem."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from app.third_party_api.ai_agent.claude_cli import ClaudeCliCancelled, ClaudeCliRunner
from app.third_party_api.attribution.transcript import read_transcript
from app.utils.redaction import sanitize_value

if TYPE_CHECKING:
    from app.third_party_api.ai_agent.contracts import SkillRunRequest

_PROVIDER_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_MODEL",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
    "CLAUDE_CODE_EFFORT_LEVEL",
)


def _provider_environment(settings: Path) -> dict[str, str]:
    configured = json.loads(settings.read_text()).get("env", {}) if settings.is_file() else {}
    return {
        key: value
        for key in _PROVIDER_ENV
        if isinstance(value := os.environ.get(key, configured.get(key)), str) and value
    }


def _environment(directory: Path, provider_env: dict[str, str]) -> dict[str, str]:
    home = directory / "home"
    temp = directory / "tmp"
    home.mkdir()
    temp.mkdir()
    # Only project the provider settings needed by this worker. Personal hooks,
    # MCP configuration, API database settings and other login secrets stay outside.
    env = {
        "HOME": str(home),
        "TMPDIR": str(temp),
        "CLAUDE_CODE_TMPDIR": str(temp),
        "PATH": os.defpath + ":/usr/local/bin",
        "LANG": "en_US.UTF-8",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
    }
    env.update(provider_env)
    return env


def _sandbox(directory: Path, executable: str) -> list[str]:
    if sys.platform == "darwin":
        # Read-only system runtime. The only writable subtree is this attempt.
        profile = """(version 1)(allow default)
(deny file-read* file-write*)
(allow file-read-metadata)
(allow file-read* (literal "/") (subpath "/System") (subpath "/usr") (subpath "/bin")
 (subpath "/private/var/run") (subpath "/private/var/db/timezone") (subpath "/Library/Frameworks")
 (subpath "/Library/Developer") (subpath "/Library/Preferences/SystemConfiguration")
 (subpath "/sbin") (subpath "/private/etc")
 (subpath "/opt/homebrew") (subpath "/dev"))
(allow file-read* file-write* (subpath (param "WORK")) (literal "/dev/null"))
(allow file-read* (literal (param "CLAUDE")))
(deny process-info* (target others))
"""
        return [
            "/usr/bin/sandbox-exec",
            "-D",
            f"WORK={directory}",
            "-D",
            f"CLAUDE={Path(executable).resolve()}",
            "-p",
            profile,
        ]
    sandbox = shutil.which("bwrap")
    if not sandbox:
        raise RuntimeError("attribution requires bubblewrap on Linux")
    args = [sandbox, "--unshare-all", "--share-net", "--die-with-parent", "--new-session"]
    for root in (
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/etc/ssl",
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/ld.so.cache",
        "/etc/nsswitch.conf",
        "/etc/localtime",
    ):
        if Path(root).exists():
            args += ["--ro-bind", root, root]
    binary = str(Path(executable).resolve())
    return [
        *args,
        "--ro-bind",
        binary,
        executable,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--bind",
        str(directory),
        str(directory),
        "--chdir",
        str(directory),
        "--",
    ]


def model_identity(model: str, settings: Path) -> dict[str, str]:
    env = _provider_environment(settings)
    resolved = env.get(f"ANTHROPIC_DEFAULT_{model.upper()}_MODEL", model)
    endpoint = env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    return {
        "selector": model,
        "model": resolved,
        "endpointHash": hashlib.sha256(endpoint.encode()).hexdigest(),
    }


def _public_details(
    details: dict[str, Any], directory: Path, session_id: str, env: dict[str, str]
) -> dict[str, Any]:
    details["sessionId"] = session_id
    details["transcript"] = read_transcript(directory, session_id)
    secrets = tuple(env[k] for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") if env.get(k))

    # Tools can echo a credential even without a recognizable key or prefix.
    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "<redacted>")
            return value
        if isinstance(value, dict):
            return {scrub(k): scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return cast(dict[str, Any], scrub(sanitize_value(details)))


async def run(
    request: SkillRunRequest,
    diagnostics: dict[str, Any],
    runner: ClaudeCliRunner,
    binary: str,
    settings: Path,
    *,
    allow_path_fallback: bool,
) -> int:
    session_id = str(uuid4())
    env: dict[str, str] = {}
    details: dict[str, Any] = {}
    directory = await asyncio.to_thread(request.directory.resolve)
    try:
        executable = shutil.which(binary)
        if executable is None and allow_path_fallback:
            executable = shutil.which("claude")
        if executable is None:
            raise RuntimeError("claude executable unavailable")
        env = _environment(directory, _provider_environment(settings))
        argv = [
            *_sandbox(directory, executable),
            executable,
            "-p",
            "--output-format",
            "json",
            "--bare",
            "--session-id",
            session_id,
            "--permission-mode",
            "bypassPermissions",
            "--allow-dangerously-skip-permissions",
            "--model",
            request.model,
            request.prompt,
        ]
        cli = None
        try:
            cli = await runner.run(
                argv, cwd=directory, env=env, timeout_seconds=request.timeout_seconds
            )
        except ClaudeCliCancelled as exc:
            cli = exc.result
            raise
        finally:
            if cli is not None:
                details.update(
                    exitCode=cli.returncode,
                    stderrTail=cli.stderr,
                    stderrTruncated=cli.stderr_truncated,
                )
        if cli.cancelled:
            raise TimeoutError("Claude Skill execution timed out")
        try:
            result = json.loads(cli.stdout)
        except ValueError:
            if cli.returncode:
                raise RuntimeError(
                    f"claude attribution exited with status {cli.returncode}"
                ) from None
            raise
        if not isinstance(result, dict):
            raise ValueError("invalid Claude result")
        details["result"] = {
            k: result[k]
            for k in (
                "subtype",
                "is_error",
                "result",
                "usage",
                "modelUsage",
                "total_cost_usd",
                "num_turns",
                "duration_ms",
            )
            if k in result
        }
        if cli.returncode:
            raise RuntimeError(f"claude attribution exited with status {cli.returncode}")
        if result.get("is_error") or result.get("subtype") != "success":
            raise RuntimeError("claude attribution did not complete")
        usage = result.get("usage", {})
        return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
    finally:
        try:
            diagnostics.update(
                await asyncio.to_thread(_public_details, details, directory, session_id, env)
            )
        except Exception as exc:
            diagnostics["diagnosticError"] = type(exc).__name__
