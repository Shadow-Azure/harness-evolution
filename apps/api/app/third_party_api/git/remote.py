"""Read-only git remote validation through a sanitized process boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol


class RepoInvalid(Exception):
    """A remote or reference could not be validated without exposing details."""


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

    async def _run(self, argv: tuple[str, ...]) -> GitProcessResult:
        """Run one bounded argv and discard all underlying diagnostic text."""
        try:
            result = await asyncio.wait_for(
                self._runner(argv),
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, OSError, RuntimeError):
            raise RepoInvalid("repository or ref is invalid") from None
        if result.returncode != 0:
            raise RepoInvalid("repository or ref is invalid")
        return result

    @staticmethod
    async def _run_process(argv: tuple[str, ...]) -> GitProcessResult:
        """Execute git as a child process with an argument array."""
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise
        return GitProcessResult(
            returncode=process.returncode or 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )
