"""Non-interactive Claude Code invocation in a case-scoped filesystem."""

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from app.third_party_api.ai_agent.claude_code import (
    DEFAULT_CLAUDE_BIN,
    claude_binary,
    claude_settings_file,
)
from app.third_party_api.attribution.backend import AgentBackend
from app.third_party_api.attribution.transcript import read_transcript
from app.utils.redaction import sanitize_value

if TYPE_CHECKING:
    from app.config import Settings

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


class ClaudeBackend(AgentBackend):
    def __init__(self, settings: "Settings | None" = None) -> None:
        self._settings = settings
        self._session_id = str(uuid4())
        self._details: dict[str, Any] = {}
        self._secrets: tuple[str, ...] = ()

    def execution_details(self, directory: Path) -> dict[str, Any]:
        details = sanitize_value(
            {
                **self._details,
                "sessionId": self._session_id,
                "transcript": read_transcript(directory, self._session_id),
            }
        )

        # Tools can echo a provider credential without a recognizable key or prefix.
        def scrub(value: Any) -> Any:
            if isinstance(value, str):
                for secret in self._secrets:
                    value = value.replace(secret, "<redacted>")
                return value
            if isinstance(value, dict):
                return {scrub(k): scrub(v) for k, v in value.items()}
            if isinstance(value, list):
                return [scrub(v) for v in value]
            return value

        return cast(dict[str, Any], scrub(details))

    def model_identity(self, model: str) -> dict[str, str]:
        env = _provider_environment(claude_settings_file(self._settings))
        resolved = env.get(f"ANTHROPIC_DEFAULT_{model.upper()}_MODEL", model)
        # Cache identity covers the endpoint without persisting its path or user info.
        endpoint = env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        return {
            "selector": model,
            "model": resolved,
            "endpointHash": hashlib.sha256(endpoint.encode()).hexdigest(),
        }

    async def execute(self, directory: Path, prompt: str, model: str, timeout_seconds: int) -> int:
        executable = shutil.which(claude_binary(self._settings))
        if executable is None and (
            not self._settings or self._settings.ai_agent_claude_bin == DEFAULT_CLAUDE_BIN
        ):
            executable = shutil.which("claude")
        if executable is None:
            raise RuntimeError("claude executable unavailable")
        directory = await asyncio.to_thread(directory.resolve)
        env = _environment(directory, _provider_environment(claude_settings_file(self._settings)))
        self._secrets = tuple(
            env[k] for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") if env.get(k)
        )
        with tempfile.TemporaryFile() as errors:
            proc = await asyncio.create_subprocess_exec(
                *_sandbox(directory, executable),
                executable,
                "-p",
                "--output-format",
                "json",
                "--bare",
                "--session-id",
                self._session_id,
                "--permission-mode",
                "bypassPermissions",
                "--allow-dangerously-skip-permissions",
                "--model",
                model,
                prompt,
                cwd=directory,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=errors,
                start_new_session=True,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            finally:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
                self._details["exitCode"] = proc.returncode
                size = errors.seek(0, os.SEEK_END)
                errors.seek(max(0, size - 16384))
                self._details["stderrTail"] = errors.read().decode(errors="replace")
                self._details["stderrTruncated"] = size > 16384
        try:
            result = json.loads(stdout)
        except ValueError:
            if proc.returncode:
                raise RuntimeError(
                    f"claude attribution exited with status {proc.returncode}"
                ) from None
            raise
        if not isinstance(result, dict):
            raise ValueError("invalid Claude result")
        self._details["result"] = {
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
        if proc.returncode:
            raise RuntimeError(f"claude attribution exited with status {proc.returncode}")
        if result.get("is_error") or result.get("subtype") != "success":
            raise RuntimeError("claude attribution did not complete")
        usage = result.get("usage", {})
        return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
