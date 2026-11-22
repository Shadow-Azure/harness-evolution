"""Read-only git content reads for target revision resolution.

Target content is read from a per-(repository, ref) shallow repository so the
resolver can ``git show`` a ``SKILL.md``/``AGENT.md`` at the selected tag without
fetching full history. A partial clone (``--filter=blob:none``) fetches only the
target ref and ``git show`` lazily fetches the one blob it needs. Every git
invocation is bounded and failures are classified into a stable reason; raw
process output never reaches the caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import signal
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

type ContentFailureReason = str

_FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
"""Only a full object id can be fetched directly from a partial repository."""

_MISSING_REF_MARKERS = (
    "couldn't find remote ref",
    "could not find remote ref",
    "not found in upstream",
    "not our ref",
)
"""Server responses that mean the requested ref does not exist."""

_MISSING_FILE_MARKERS = (
    "does not exist",
    "exists on disk, but not in",
    "not in tree",
    "unable to read",
)
"""``git show`` responses that mean the file is absent at that commit."""

_NETWORK_MARKERS = (
    "could not fetch",
    "promisor remote",
    "unable to access",
    "could not resolve",
    "timed out",
)
"""Transport markers raised by a lazy partial-clone blob fetch."""


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


type GitContentRunner = Callable[
    [tuple[str, ...], Path | None],
    Awaitable[GitProcessResult],
]


class SubprocessGitContent:
    """Cache one shallow repository per ref and read one file at one commit."""

    def __init__(
        self,
        *,
        cache_root: Path,
        runner: GitContentRunner | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        """Bind the cache root, process seam, and one bounded timeout."""
        self.cache_root = cache_root
        self._runner = runner or _run_process
        self._timeout_seconds = timeout_seconds
        self._cache_locks: dict[str, asyncio.Lock] = {}

    async def read_file(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        ref: str,
        file_name: str,
    ) -> str:
        """Return the exact file body at ``ref`` or raise a stable failure."""
        _, body = await self.read_versioned_file(
            repo_url=repo_url, sub_dir=sub_dir, ref=ref, file_name=file_name
        )
        return body

    async def read_versioned_file(
        self, *, repo_url: str, sub_dir: str, ref: str, file_name: str
    ) -> tuple[str, str]:
        """Read the commit and file together, even when the ref moves."""
        relative = _relative_path(sub_dir, file_name)
        checked_ref = _checked_ref(ref)
        repo_path = self._cache_path(repo_url, checked_ref)
        # Concurrent overview requests may resolve the same ref at once; serialize
        # the whole read so one clone/refresh cannot remove the cache a sibling
        # request is about to read.
        async with self._cache_lock(repo_path):
            commit = await self._ensure_commit(repo_path, repo_url, checked_ref)
            result = await self._git(repo_path, ("git", "show", f"{commit}:{relative}"))
        if result.returncode != 0:
            raise GitContentUnavailable(_show_failure(result.stderr))
        return commit, result.stdout

    def _cache_path(self, repo_url: str, ref: str) -> Path:
        """Return the one cache directory for a repository and ref pair."""
        repo_key = hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:32]
        ref_key = hashlib.sha256(f"{repo_url}\0{ref}".encode()).hexdigest()[:16]
        return self.cache_root / repo_key / ref_key

    def _cache_lock(self, repo_path: Path) -> asyncio.Lock:
        """Return the one process-local lock guarding a ref cache path."""
        key = str(repo_path)
        lock = self._cache_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._cache_locks[key] = lock
        return lock

    async def _ensure_commit(self, repo_path: Path, repo_url: str, ref: str) -> str:
        """Fetch only ``ref`` when needed and return the commit it resolves to."""
        if _FULL_COMMIT.fullmatch(ref):
            if not self._usable(repo_path):
                await self._init_bare(repo_path, repo_url)
            if await self._commit_present(repo_path, ref):
                return ref
            result = await self._git(
                repo_path,
                (
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "--filter=blob:none",
                    "--no-tags",
                    "origin",
                    ref,
                ),
            )
            if result.returncode != 0:
                raise GitContentUnavailable(_fetch_failure(result.stderr))
            commit = await self._resolve_commit(repo_path, "FETCH_HEAD")
            if commit is None:
                raise GitContentUnavailable("ref_not_found")
            return commit

        if not self._usable(repo_path):
            await self._clone_ref(repo_path, repo_url, ref)
            commit = await self._resolve_commit(repo_path, "HEAD")
        else:
            await self._fetch_ref(repo_path, ref)
            commit = await self._resolve_commit(repo_path, "FETCH_HEAD")
        if commit is None:
            raise GitContentUnavailable("ref_not_found")
        return commit

    def _usable(self, repo_path: Path) -> bool:
        """Return whether an existing cache directory is a usable repository."""
        if not repo_path.exists():
            return False
        if (repo_path / ".git").is_dir():
            return True
        return (repo_path / "HEAD").is_file() and (repo_path / "objects").is_dir()

    async def _clone_ref(self, repo_path: Path, repo_url: str, ref: str) -> None:
        """Create a single-branch shallow partial clone for one tag or branch."""
        self._safe_remove(repo_path)
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        result = await self._git(
            None,
            (
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--filter=blob:none",
                "--no-checkout",
                "--branch",
                _branch_name(ref),
                "--",
                repo_url,
                str(repo_path),
            ),
        )
        if result.returncode != 0:
            self._safe_remove(repo_path)
            raise GitContentUnavailable(_fetch_failure(result.stderr))

    async def _init_bare(self, repo_path: Path, repo_url: str) -> None:
        """Create an empty partial-clone repository for a full commit fetch."""
        self._safe_remove(repo_path)
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        commands: tuple[tuple[str, ...], ...] = (
            ("git", "init", "--bare", "--", str(repo_path)),
            ("git", "-C", str(repo_path), "remote", "add", "origin", repo_url),
            ("git", "-C", str(repo_path), "config", "remote.origin.promisor", "true"),
            (
                "git",
                "-C",
                str(repo_path),
                "config",
                "remote.origin.partialclonefilter",
                "blob:none",
            ),
        )
        for command in commands:
            result = await self._git(None, command)
            if result.returncode != 0:
                self._safe_remove(repo_path)
                raise GitContentUnavailable("repo_unreachable")

    async def _fetch_ref(self, repo_path: Path, ref: str) -> None:
        """Refresh exactly one tag or branch in an existing shallow cache."""
        for candidate in _ref_candidates(ref):
            result = await self._git(
                repo_path,
                (
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "--filter=blob:none",
                    "--no-tags",
                    "origin",
                    candidate,
                ),
            )
            if result.returncode == 0:
                return
            if not _missing_ref(result.stderr):
                raise GitContentUnavailable("repo_unreachable")
        raise GitContentUnavailable("ref_not_found")

    async def _commit_present(self, repo_path: Path, commit: str) -> bool:
        """Return whether a full commit id is already present locally."""
        result = await self._git(
            repo_path,
            ("git", "cat-file", "-e", f"{commit}^{{commit}}"),
        )
        return result.returncode == 0

    async def _resolve_commit(self, repo_path: Path, name: str) -> str | None:
        """Return the commit one local ref resolves to, or ``None`` when absent."""
        result = await self._git(
            repo_path,
            ("git", "rev-parse", "--verify", f"{name}^{{commit}}"),
        )
        commit = result.stdout.strip()
        return commit if result.returncode == 0 and commit else None

    async def _git(
        self,
        cwd: Path | None,
        argv: tuple[str, ...],
    ) -> GitProcessResult:
        """Invoke git with one bounded timeout and classify process failures."""
        try:
            return await asyncio.wait_for(
                self._runner(argv, cwd),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            raise GitContentUnavailable("timeout") from None
        except (OSError, RuntimeError):
            raise GitContentUnavailable("git_unavailable") from None

    def _safe_remove(self, repo_path: Path) -> None:
        """Remove a cache directory only inside the configured root."""
        try:
            repo_path.resolve().relative_to(self.cache_root.resolve())
        except (OSError, ValueError):
            return
        shutil.rmtree(repo_path, ignore_errors=True)


def _checked_ref(ref: str) -> str:
    """Reject a ref that could be parsed as an option or spans control chars."""
    if (
        not ref
        or ref.startswith("-")
        or any(character.isspace() or ord(character) < 0x20 for character in ref)
    ):
        raise GitContentUnavailable("ref_invalid")
    return ref


def _branch_name(ref: str) -> str:
    """Reduce a ref to the branch/tag name accepted by ``git clone --branch``."""
    for prefix in ("refs/heads/", "refs/tags/", "origin/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def _ref_candidates(ref: str) -> tuple[str, ...]:
    """Return the full remote refs to try for one user-facing ref."""
    if ref.startswith("refs/"):
        return (ref,)
    if ref.startswith("origin/"):
        return (f"refs/heads/{ref[len('origin/') :]}", f"refs/tags/{ref[len('origin/') :]}")
    return (f"refs/heads/{ref}", f"refs/tags/{ref}")


def _missing_ref(stderr: str) -> bool:
    """Return whether git reported that the remote ref does not exist."""
    diagnostic = stderr.lower()
    return any(marker in diagnostic for marker in _MISSING_REF_MARKERS)


def _fetch_failure(stderr: str) -> ContentFailureReason:
    """Classify a failed clone or fetch without exposing raw diagnostics."""
    if _missing_ref(stderr):
        return "ref_not_found"
    return "repo_unreachable"


def _show_failure(stderr: str) -> ContentFailureReason:
    """Classify a failed ``git show`` including a lazy blob fetch failure."""
    diagnostic = stderr.lower()
    if any(marker in diagnostic for marker in _MISSING_FILE_MARKERS):
        return "file_not_found"
    if any(marker in diagnostic for marker in _NETWORK_MARKERS):
        return "repo_unreachable"
    return "file_not_found"


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
