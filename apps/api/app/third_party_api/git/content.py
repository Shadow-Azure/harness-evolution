"""Read-only git content reads for target revision resolution.

Target content is read from a mirror cache so the resolver can ``git show`` a
``SKILL.md``/``AGENT.md`` at the selected tag without a working tree. Every git
invocation is bounded and failures are classified into a stable reason; raw
process output never reaches the caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import signal
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

type ContentFailureReason = str


class GitContentUnavailable(RuntimeError):
    """A target file could not be read without exposing process output."""

    def __init__(
        self,
        reason: ContentFailureReason = "content_unavailable",
    ) -> None:
        """Store one stable machine-readable reason."""
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GitProcessResult:
    """Captured output from one argument-array git process."""

    returncode: int
    stdout: str
    stderr: str


type GitContentRunner = Callable[[tuple[str, ...], Path | None], Awaitable[GitProcessResult]]


class SubprocessGitContent:
    """Clone mirrors lazily and read one file at one commit."""

    def __init__(
        self,
        *,
        cache_root: Path,
        runner: GitContentRunner | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        """Bind the mirror cache root, process seam, and one bounded timeout."""
        self.cache_root = cache_root
        self._runner = runner or _run_process
        self._timeout_seconds = timeout_seconds
        self._mirror_locks: dict[str, asyncio.Lock] = {}

    async def read_file(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        ref: str,
        file_name: str,
    ) -> str:
        """Return the exact file body at ``ref`` or raise a stable failure."""
        repo_path = self.cache_root / hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:32]
        # Concurrent overview requests may resolve the same repository at once;
        # serialize the whole read so one clone/refresh cannot remove the cache a
        # sibling request is about to read.
        async with self._mirror_lock(repo_path):
            await self._ensure_mirror(repo_path, repo_url)
            commit = await self._resolve_commit(repo_path, ref)
            if commit is None:
                # A mirror is append-mostly: a missing tag is usually a cache that
                # predates the tag, so refresh once before giving up.
                await self._check(repo_path, ("git", "remote", "update", "--prune"))
                commit = await self._resolve_commit(repo_path, ref)
            if commit is None:
                raise GitContentUnavailable("ref_not_found")
            relative = _relative_path(sub_dir, file_name)
            result = await self._git(repo_path, ("git", "show", f"{commit}:{relative}"))
        if result.returncode != 0:
            raise GitContentUnavailable("file_not_found")
        return result.stdout

    def _mirror_lock(self, repo_path: Path) -> asyncio.Lock:
        """Return the one process-local lock guarding a mirror cache path."""
        key = str(repo_path)
        lock = self._mirror_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._mirror_locks[key] = lock
        return lock

    async def _ensure_mirror(self, repo_path: Path, repo_url: str) -> None:
        """Create or verify the read-only mirror for one repository."""
        self.cache_root.mkdir(parents=True, exist_ok=True)
        if repo_path.exists():  # noqa: ASYNC240 - cache inspection is local metadata
            current = await self._git(repo_path, ("git", "remote", "get-url", "origin"))
            if current.returncode != 0 or current.stdout.strip() != repo_url:
                self._safe_remove(repo_path)
        if repo_path.exists():  # noqa: ASYNC240 - cache inspection is local metadata
            return
        result = await self._git(
            None,
            (
                "git",
                "clone",
                "--mirror",
                "--no-hardlinks",
                "--",
                repo_url,
                str(repo_path),
            ),
        )
        if result.returncode != 0:
            self._safe_remove(repo_path)
            raise GitContentUnavailable("repo_unreachable")

    async def _resolve_commit(self, repo_path: Path, ref: str) -> str | None:
        """Return the commit one ref resolves to, or ``None`` when absent."""
        result = await self._git(
            repo_path,
            ("git", "rev-parse", "--verify", f"{ref}^{{commit}}"),
        )
        commit = result.stdout.strip()
        return commit if result.returncode == 0 and commit else None

    async def _check(self, repo_path: Path, argv: tuple[str, ...]) -> None:
        """Run one refresh step without turning a transient failure into a read."""
        result = await self._git(repo_path, argv)
        if result.returncode != 0:
            raise GitContentUnavailable("repo_unreachable")

    async def _git(
        self,
        cwd: Path | None,
        argv: tuple[str, ...],
    ) -> GitProcessResult:
        """Invoke git with one bounded timeout and classify process failures."""
        try:
            return await asyncio.wait_for(self._runner(argv, cwd), timeout=self._timeout_seconds)
        except TimeoutError:
            raise GitContentUnavailable("timeout") from None
        except (OSError, RuntimeError):
            raise GitContentUnavailable("git_unavailable") from None

    @staticmethod
    def _safe_remove(repo_path: Path) -> None:
        """Remove a cache directory only inside the configured root."""
        shutil.rmtree(repo_path, ignore_errors=True)


def _relative_path(sub_dir: str, file_name: str) -> str:
    """Build a repository-relative POSIX path and reject traversal."""
    directory = PurePosixPath((sub_dir or ".").strip())
    if directory.is_absolute() or ".." in directory.parts:
        raise GitContentUnavailable("path_invalid")
    file_path = PurePosixPath(file_name)
    if file_path.is_absolute() or len(file_path.parts) != 1:
        raise GitContentUnavailable("path_invalid")
    return (directory / file_name).as_posix()


async def _run_process(
    argv: tuple[str, ...],
    cwd: Path | None,
) -> GitProcessResult:
    """Execute git through a sanitized argument array with prompts disabled."""
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
        },
    )
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd is not None else None,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
        start_new_session=sys.platform != "win32",
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        # The overview timeout cancels this coroutine; kill the whole git process
        # group so a slow clone cannot outlive the request.
        if process.returncode is None:
            try:
                if sys.platform == "win32":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        raise
    return GitProcessResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )
