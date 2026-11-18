"""Read-only git remote validation through a sanitized process boundary."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, Protocol

type RepoFailureReason = Literal[
    "ref_not_found",
    "repo_unreachable",
    "git_timeout",
    "git_unavailable",
]


class RepoInvalid(Exception):
    """A remote or reference could not be validated.

    The message stays generic; machine-readable ``reason`` and bounded process
    metadata let the service build an administrator-facing diagnostic without
    exposing raw runner text.
    """

    def __init__(
        self,
        message: str = "repository or ref is invalid",
        *,
        reason: RepoFailureReason = "repo_unreachable",
        exit_code: int | None = None,
        stderr: str = "",
    ) -> None:
        """Record one failure classification and its captured output."""
        super().__init__(message)
        self.reason = reason
        self.exit_code = exit_code
        self.stderr = stderr


class GitRemote(Protocol):
    """Read-only git operations required by target configuration."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Require the remote to resolve one reference."""

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Return the remote's sorted unique tag names."""


@dataclass(frozen=True, slots=True)
class GitProcessResult:
    """Captured process output used by the injectable git runner."""

    returncode: int
    stdout: str
    stderr: str


type GitProcessRunner = Callable[[tuple[str, ...]], Awaitable[GitProcessResult]]


class SubprocessGitRemote:
    """Invoke git without a shell and collapse every failure into `RepoInvalid`."""

    def __init__(
        self,
        *,
        runner: GitProcessRunner | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        """Bind an optional runner for tests and one bounded timeout."""
        self._runner = runner or self._run_process
        self._timeout_seconds = timeout_seconds

    async def validate(self, repo_url: str, ref: str) -> None:
        """Require one remote reference to resolve."""
        await self._run(
            ("git", "ls-remote", "--exit-code", "--", repo_url, ref),
            ref_check=True,
        )

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Read and normalize tags from one remote."""
        result = await self._run(
            ("git", "ls-remote", "--tags", "--refs", "--", repo_url),
        )
        tags: set[str] = set()
        for line in result.stdout.splitlines():
            _object_id, separator, ref = line.partition("\t")
            if not separator or not ref.startswith("refs/tags/") or ref.endswith("^{}"):
                continue
            tag = ref.removeprefix("refs/tags/")
            if tag:
                tags.add(tag)
        return tuple(sorted(tags))

    async def _run(
        self,
        argv: tuple[str, ...],
        *,
        ref_check: bool = False,
    ) -> GitProcessResult:
        """Run one bounded argv and classify failures for the caller.

        Exit code 2 from ``git ls-remote --exit-code`` means the repository was
        reachable but the requested ref was absent. ``list_tags`` never passes
        ``ref_check``, so its exit code 2 maps to an unreachable remote.
        """
        try:
            result = await asyncio.wait_for(
                self._runner(argv),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            raise RepoInvalid(reason="git_timeout") from None
        except (OSError, RuntimeError):
            raise RepoInvalid(reason="git_unavailable") from None
        if result.returncode != 0:
            reason: RepoFailureReason = (
                "ref_not_found" if ref_check and result.returncode == 2 else "repo_unreachable"
            )
            raise RepoInvalid(
                reason=reason,
                exit_code=result.returncode,
                stderr=result.stderr,
            )
        return result

    @staticmethod
    async def _run_process(argv: tuple[str, ...]) -> GitProcessResult:
        """Execute git as a child process with an argument array."""
        environment = dict(os.environ)
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
            },
        )
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
            start_new_session=sys.platform != "win32",
        )
        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            with suppress(ProcessLookupError):
                if sys.platform == "win32":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            raise
        return GitProcessResult(
            returncode=process.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )
