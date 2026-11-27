"""Derived-cache ownership, lifecycle markers, and startup recovery.

Both shallow caches under ``HE_DATA_DIR`` (``target-content`` for definition
reads and ``repos`` for run preparation) are derived data: a complete cache can
always be rebuilt from the remote. A cache interrupted mid-clone or mid-fetch
therefore must not be trusted just because its directory still looks like a
repository.

This module owns the rules shared by both entry points:

* a cross-process ``flock`` per cache key, stored outside the cache directory so
  a rebuild cannot invalidate a lock another process is waiting on;
* an atomically written ``incomplete``/``complete`` state marker next to the
  cache directory (``git clone`` requires an empty destination, so the marker
  cannot live inside);
* removal of git lock files (``shallow.lock`` and friends) while the flock is
  held, when no active git process of this service can own them;
* classification of git's lock-conflict diagnostics;
* the startup sweep that drops incomplete caches and stale legacy caches before
  job recovery starts.

The marker is advisory for legacy caches written by earlier versions: a
marker-less cache with a valid repository structure and no git lock files is
adopted by writing ``complete`` after it is validated, so an upgrade does not
rebuild every ref.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import shutil
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

STATE_SUFFIX = ".state.json"
"""Suffix of the state marker stored next to one cache directory."""

LOCK_DIRECTORY = ".locks"
"""Directory under a cache root holding cross-process lock files."""

_LOCK_RETRY_SECONDS = 0.05
"""Delay between non-blocking flock attempts so cancellation stays responsive."""

_GIT_LOCK_NAMES = (
    "shallow.lock",
    "index.lock",
    "HEAD.lock",
    "config.lock",
    "packed-refs.lock",
)
"""Git lock files, relative to the repository's git directory."""

type CachePhase = Literal["incomplete", "complete"]


class CacheBusyError(RuntimeError):
    """The cross-process cache lock is held by another live operation."""


@dataclass(frozen=True, slots=True)
class CacheState:
    """Lifecycle marker of one derived cache directory."""

    phase: CachePhase
    repo_url: str
    ref: str
    started_at: float
    commit: str | None = None

    @property
    def is_complete(self) -> bool:
        """Return whether the last clone/fetch finished successfully."""
        return self.phase == "complete"


@dataclass(frozen=True, slots=True)
class CacheSweepResult:
    """Summary of one startup sweep over a cache root."""

    caches_removed: int = 0
    locks_removed: int = 0


def state_path(cache_path: Path) -> Path:
    """Return the state marker path next to one cache directory.

    ``git clone`` refuses a non-empty destination, so the marker is a sibling
    of the cache directory rather than a file inside it.
    """
    return cache_path.with_name(cache_path.name + STATE_SUFFIX)


def read_state(cache_path: Path) -> CacheState | None:
    """Read one marker, treating corruption as absence so it can be rebuilt."""
    try:
        payload = json.loads(state_path(cache_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    phase_value = payload.get("phase")
    repo_url = payload.get("repo_url")
    ref = payload.get("ref")
    started_at = payload.get("started_at")
    commit = payload.get("commit")
    if phase_value not in {"incomplete", "complete"}:
        return None
    if not isinstance(repo_url, str) or not isinstance(ref, str):
        return None
    if not isinstance(started_at, (int, float)) or isinstance(started_at, bool):
        return None
    if commit is not None and not isinstance(commit, str):
        return None
    phase: CachePhase = "complete" if phase_value == "complete" else "incomplete"
    return CacheState(
        phase=phase,
        repo_url=repo_url,
        ref=ref,
        started_at=float(started_at),
        commit=commit,
    )


def write_state(
    cache_path: Path,
    phase: CachePhase,
    *,
    repo_url: str,
    ref: str,
    commit: str | None = None,
) -> None:
    """Atomically replace one marker and fsync it before a git process starts."""
    destination = state_path(cache_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "phase": phase,
            "repo_url": repo_url,
            "ref": ref,
            "started_at": time.time(),
            "commit": commit,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def mark_incomplete(cache_path: Path, *, repo_url: str, ref: str) -> None:
    """Record that a clone or fetch is about to mutate this cache."""
    write_state(cache_path, "incomplete", repo_url=repo_url, ref=ref)


def mark_complete(
    cache_path: Path,
    *,
    repo_url: str,
    ref: str,
    commit: str | None,
) -> None:
    """Record that the cache now holds a consistent repository for repo/ref."""
    write_state(cache_path, "complete", repo_url=repo_url, ref=ref, commit=commit)


def remove_state(cache_path: Path) -> None:
    """Drop the marker of a cache that is being deleted."""
    state_path(cache_path).unlink(missing_ok=True)


def matches(state: CacheState | None, *, repo_url: str, ref: str) -> bool:
    """Return whether a marker describes this exact repository and ref."""
    return (
        state is not None and state.is_complete and state.repo_url == repo_url and state.ref == ref
    )


def git_directory(cache_path: Path) -> Path:
    """Return the repository's git directory for a bare or non-bare cache."""
    nested = cache_path / ".git"
    return nested if nested.is_dir() else cache_path


def git_lock_files(cache_path: Path) -> list[Path]:
    """Return every git lock file currently held inside one cache."""
    directory = git_directory(cache_path)
    found = [directory / name for name in _GIT_LOCK_NAMES if (directory / name).exists()]
    refs = directory / "refs"
    if refs.is_dir():
        found.extend(refs.rglob("*.lock"))
    return found


def has_git_locks(cache_path: Path) -> bool:
    """Return whether the cache contains a lock that a live git process might own."""
    return bool(git_lock_files(cache_path))


def clean_git_locks(cache_path: Path) -> int:
    """Delete git lock files in a cache owned by the held cross-process flock."""
    removed = 0
    for path in git_lock_files(cache_path):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue
        removed += 1
    return removed


def is_lock_conflict(stderr: str) -> bool:
    """Return whether git refused to start because a lock file exists."""
    diagnostic = stderr.lower()
    return "another git process seems to be running" in diagnostic or (
        "unable to create" in diagnostic and ".lock" in diagnostic
    )


def cache_host(repo_url: str) -> str:
    """Return the repository host without credentials, path, or query."""
    try:
        parsed = urlsplit(repo_url)
        hostname = parsed.hostname
    except ValueError:
        return "unknown"
    if hostname:
        return hostname
    # Local test remotes and scp-like addresses have no URL scheme.
    stripped = repo_url.split("@", 1)[-1]
    host = stripped.split(":", 1)[0].split("/", 1)[0]
    return host or "local"


def log_stale_lock(cache_root: Path, cache_path: Path, *, repo_url: str, ref: str) -> None:
    """Emit one credential-free structured warning about a stale git lock."""
    try:
        cache_key = cache_path.relative_to(cache_root).as_posix()
    except ValueError:
        cache_key = cache_path.name
    logger.warning(
        "git cache stale lock",
        extra={
            "event": "git.cache.stale_lock",
            "cacheKey": cache_key,
            "repoHost": cache_host(repo_url),
            "refHash": hashlib.sha256(ref.encode("utf-8")).hexdigest()[:16],
        },
    )


def lock_file_path(cache_root: Path, cache_path: Path) -> Path:
    """Return the stable cross-process lock file for one cache key."""
    try:
        key = cache_path.relative_to(cache_root).as_posix()
    except ValueError:
        key = str(cache_path)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return cache_root / LOCK_DIRECTORY / f"{digest}.lock"


@asynccontextmanager
async def cache_flock(cache_root: Path, cache_path: Path) -> AsyncIterator[None]:
    """Serialize one cache key across processes for the whole operation.

    ``flock`` is released by the kernel when the process exits, including
    ``SIGKILL``, so a dead holder never leaves the cache permanently locked.
    The non-blocking retry loop stays cancellable: a cancelled read closes its
    descriptor instead of leaking a lock until the process restarts.
    """
    path = lock_file_path(cache_root, cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        await _await_flock(descriptor)
        acquired = True
        yield
    finally:
        if acquired:
            _release_flock(descriptor)
        else:
            os.close(descriptor)


def sweep_cache_root(cache_root: Path) -> CacheSweepResult:
    """Clean one cache root before job recovery accepts new git work.

    Incomplete caches are deleted (a rebuild is bounded and cheaper than
    trusting a half-written repository). Marker-less legacy caches with git
    locks are removed for the same reason; healthy legacy caches are left for
    read-time adoption.
    """
    if not cache_root.is_dir():
        return CacheSweepResult()
    removed = 0
    cleaned = 0
    for cache_path in sorted(_cache_directories(cache_root)):
        try:
            handle = _try_flock(cache_root, cache_path)
        except CacheBusyError:
            # Another process is actively using this cache; the startup sweep
            # must not delete it from under that operation.
            continue
        with handle:
            state = read_state(cache_path)
            if state is not None and not state.is_complete:
                if _remove_cache_directory(cache_root, cache_path):
                    remove_state(cache_path)
                    removed += 1
                continue
            if state is None and has_git_locks(cache_path):
                # Legacy caches use the same rule as read time: a lock proves
                # the previous clone/fetch did not finish cleanly.
                if _remove_cache_directory(cache_root, cache_path):
                    removed += 1
                continue
            cleaned += clean_git_locks(cache_path)
    for state_file in sorted(cache_root.glob(f"*/*{STATE_SUFFIX}")):
        cache_path = state_file.with_name(state_file.name[: -len(STATE_SUFFIX)])
        if not cache_path.exists():
            state_file.unlink(missing_ok=True)
    if removed or cleaned:
        logger.info(
            "git cache sweep",
            extra={
                "event": "git.cache.sweep",
                "cacheRoot": str(cache_root),
                "cachesRemoved": removed,
                "locksRemoved": cleaned,
            },
        )
    return CacheSweepResult(caches_removed=removed, locks_removed=cleaned)


def sweep_cache_roots(*roots: Path) -> CacheSweepResult:
    """Sweep every configured cache root and combine the summaries."""
    removed = 0
    cleaned = 0
    for root in roots:
        try:
            result = sweep_cache_root(root)
        except OSError:
            logger.warning(
                "git cache sweep failed",
                extra={"event": "git.cache.sweep_failed", "cacheRoot": str(root)},
                exc_info=True,
            )
            continue
        removed += result.caches_removed
        cleaned += result.locks_removed
    return CacheSweepResult(caches_removed=removed, locks_removed=cleaned)


def _cache_directories(cache_root: Path) -> list[Path]:
    """Return the two-level cache directories under one root."""
    directories: list[Path] = []
    for parent in cache_root.iterdir():
        if not parent.is_dir() or parent.name == LOCK_DIRECTORY:
            continue
        for child in parent.iterdir():
            if child.is_dir():
                directories.append(child)
    return directories


def _remove_cache_directory(cache_root: Path, cache_path: Path) -> bool:
    """Delete one cache directory only inside the configured root."""
    try:
        cache_path.resolve().relative_to(cache_root.resolve())
    except (OSError, ValueError):
        return False
    if not cache_path.is_dir():
        return False
    shutil.rmtree(cache_path, ignore_errors=True)
    return not cache_path.exists()


def _try_flock(cache_root: Path, cache_path: Path) -> _FlockHandle:
    """Acquire a non-blocking flock for the startup sweep."""
    path = lock_file_path(cache_root, cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _flock_descriptor(descriptor)
    except BlockingIOError:
        os.close(descriptor)
        raise CacheBusyError(str(path)) from None
    return _FlockHandle(descriptor)


class _FlockHandle:
    """Non-blocking flock handle released through the context manager protocol."""

    def __init__(self, descriptor: int) -> None:
        """Store the open descriptor owning the kernel lock."""
        self._descriptor = descriptor

    def __enter__(self) -> None:
        """Return without doing work; the lock is already held."""
        return None

    def __exit__(self, *_: object) -> None:
        """Release the kernel lock and close the descriptor."""
        _release_flock(self._descriptor)


async def _await_flock(descriptor: int) -> None:
    """Wait for the exclusive kernel lock without blocking the event loop."""
    while True:
        try:
            _flock_descriptor(descriptor)
            return
        except BlockingIOError:
            await asyncio.sleep(_LOCK_RETRY_SECONDS)


def _flock_descriptor(descriptor: int) -> None:
    """Try one exclusive non-blocking lock for the current platform."""
    if sys.platform == "win32":
        msvcrt = importlib.import_module("msvcrt")
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BlockingIOError from None
        return
    fcntl = importlib.import_module("fcntl")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise


def _release_flock(descriptor: int) -> None:
    """Release one kernel lock and close its descriptor."""
    try:
        if sys.platform == "win32":
            msvcrt = importlib.import_module("msvcrt")
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl = importlib.import_module("fcntl")
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry where the platform supports it."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)
