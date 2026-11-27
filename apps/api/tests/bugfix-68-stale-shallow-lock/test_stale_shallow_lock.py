"""Stale shallow-lock and interrupted-cache recovery for both git caches."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.models.evolution import EvolutionRunRecord
from app.third_party_api.git.cache import (
    cache_flock,
    lock_file_path,
    mark_complete,
    mark_incomplete,
    read_state,
    remove_state,
    state_path,
    sweep_cache_roots,
)
from app.third_party_api.git.content import (
    GitContentUnavailable,
    GitProcessResult,
    SubprocessGitContent,
    _run_process,
)
from app.third_party_api.git.workspace import (
    GitProcessResult as WorkspaceProcessResult,
)
from app.third_party_api.git.workspace import GitWorkspaceManager

NOW = datetime(2026, 11, 27, 9, 30, tzinfo=UTC)
SKILL_BODY = "# Systematic debugging\n\nReproduce before fixing.\n"
LOCK_CONFLICT = "fatal: Unable to create '/tmp/cache/shallow.lock': File exists."


def _git(cwd: Path, *args: str) -> str:
    """Run one deterministic local git command and return stdout."""
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603 - fixed local test binary and argv
        (git, *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _seed_content_repo(tmp_path: Path) -> Path:
    """Create one repository with a tagged target file."""
    repo = tmp_path / "seed"
    (repo / "skills" / "x").mkdir(parents=True)
    (repo / "skills" / "x" / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial")
    _git(repo, "tag", "-a", "v1", "-m", "tag")
    return repo


def _seed_workspace_repo(tmp_path: Path) -> Path:
    """Create one bare remote with a target branch."""
    bare = tmp_path / "remote.git"
    seed = tmp_path / "workspace-seed"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(seed))
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "config", "user.email", "test@example.invalid")
    target = seed / "skills" / "deep-research"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# Feature\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "feature target")
    _git(seed, "push", "origin", "HEAD:refs/heads/feature")
    return bare


def _run(repo_url: str, version: str, *, run_id: str = "run-stale-lock") -> EvolutionRunRecord:
    """Build one run snapshot for real local git operations."""
    return EvolutionRunRecord(
        id=run_id,
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config={"gateway": "fake"},
        target_config_id="target-single",
        target_type="skill",
        target_name="deep-research",
        target_version=version,
        repo_url=repo_url,
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref=version,
        base_commit=None,
        branch_name=None,
        workspace_path=None,
        remote_name="origin",
        push_status="pending",
        pushed_at=None,
        push_error=None,
        window_from=None,
        window_to=None,
        models=[],
        status="preparing",
        blocked_stage=None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=None,
        error_message=None,
        error_at=None,
        progress_unit=0,
        stats={},
        created_by=None,
        created_at=NOW,
        finished_at=None,
    )


class RecordingContentRunner:
    """Delegate to real git while recording every argv array."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def __call__(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> GitProcessResult:
        self.calls.append(argv)
        return await _run_process(argv, cwd)

    @property
    def clone_count(self) -> int:
        """Return how many clone operations reached git."""
        return sum(1 for argv in self.calls if "clone" in argv)


class FlakyLockContentRunner(RecordingContentRunner):
    """Return one git lock conflict for the first fetch, then delegate to git."""

    def __init__(self) -> None:
        super().__init__()
        self.fetches = 0

    async def __call__(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> GitProcessResult:
        if len(argv) > 1 and argv[1] == "fetch":
            self.fetches += 1
            if self.fetches == 1:
                return GitProcessResult(returncode=128, stdout="", stderr=LOCK_CONFLICT)
        return await super().__call__(argv, cwd)


class LockConflictContentRunner(RecordingContentRunner):
    """Fail every fetch as if a stale shallow lock still existed."""

    async def __call__(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> GitProcessResult:
        if len(argv) > 1 and argv[1] == "fetch":
            self.calls.append(argv)
            return GitProcessResult(returncode=128, stdout="", stderr=LOCK_CONFLICT)
        return await super().__call__(argv, cwd)


class FlakyLockWorkspaceRunner:
    """Return one git lock conflict for the first fetch, then delegate to git."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fetches = 0

    async def __call__(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> WorkspaceProcessResult:
        self.calls.append(argv)
        if len(argv) > 1 and argv[1] == "fetch":
            self.fetches += 1
            if self.fetches == 1:
                return WorkspaceProcessResult(returncode=128, stdout="", stderr=LOCK_CONFLICT)
        from app.third_party_api.git.workspace import _run_process as run_workspace_process

        return await run_workspace_process(argv, cwd)


async def test_stale_shallow_lock_is_cleaned_and_read_recovers(tmp_path: Path) -> None:
    """A leftover shallow.lock in a complete cache is removed before the refresh."""
    repo = _seed_content_repo(tmp_path)
    content = SubprocessGitContent(cache_root=tmp_path / "cache")
    first = await content.read_file(
        repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"
    )
    assert first == SKILL_BODY

    cache_path = content._cache_path(str(repo), "v1")
    lock = cache_path / ".git" / "shallow.lock"
    lock.write_text("stale", encoding="utf-8")

    body = await content.read_file(
        repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"
    )

    assert body == SKILL_BODY
    assert not lock.exists()
    state = read_state(cache_path)
    assert state is not None and state.is_complete


async def test_persistent_lock_conflict_is_retried_then_classified(tmp_path: Path) -> None:
    """A lock that survives one cleanup retry becomes a stable cache reason."""
    repo = _seed_content_repo(tmp_path)
    runner = LockConflictContentRunner()
    content = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    await content.read_file(repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md")
    fetches_before = sum(1 for argv in runner.calls if "fetch" in argv)

    with pytest.raises(GitContentUnavailable) as raised:
        await content.read_file(
            repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"
        )

    assert raised.value.reason == "cache_stale_lock"
    fetches_after = sum(1 for argv in runner.calls if "fetch" in argv)
    assert fetches_after - fetches_before == 2
    # The previous complete cache is kept for a later retry.
    state = read_state(content._cache_path(str(repo), "v1"))
    assert state is not None and state.is_complete


async def test_lock_conflict_is_cleaned_and_retried_once(tmp_path: Path) -> None:
    """A transient git lock conflict does not surface to the caller."""
    repo = _seed_content_repo(tmp_path)
    runner = FlakyLockContentRunner()
    content = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    await content.read_file(repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md")

    body = await content.read_file(
        repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"
    )

    assert body == SKILL_BODY
    # The retried branch candidate does not exist, so git is asked for the tag
    # candidate afterwards; the lock conflict itself cost exactly one retry.
    assert runner.fetches == 3


async def test_incomplete_cache_is_rebuilt_instead_of_reused(tmp_path: Path) -> None:
    """A cache left incomplete by a killed fetch is rebuilt from the remote."""
    repo = _seed_content_repo(tmp_path)
    runner = RecordingContentRunner()
    content = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    await content.read_file(repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md")
    cache_path = content._cache_path(str(repo), "v1")
    sentinel = cache_path / "interrupted-object"
    sentinel.write_text("partial", encoding="utf-8")
    mark_incomplete(cache_path, repo_url=str(repo), ref="v1")
    clones_before = runner.clone_count

    body = await content.read_file(
        repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"
    )

    assert body == SKILL_BODY
    assert not sentinel.exists()
    assert runner.clone_count > clones_before
    recovered = read_state(cache_path)
    assert recovered is not None and recovered.is_complete


async def test_legacy_cache_with_lock_is_rebuilt(tmp_path: Path) -> None:
    """A marker-less cache with a git lock is not adopted after an interrupted clone."""
    repo = _seed_content_repo(tmp_path)
    runner = RecordingContentRunner()
    content = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    await content.read_file(repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md")
    cache_path = content._cache_path(str(repo), "v1")
    remove_state(cache_path)
    (cache_path / ".git" / "shallow.lock").write_text("stale", encoding="utf-8")

    body = await content.read_file(
        repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"
    )

    assert body == SKILL_BODY
    assert runner.clone_count == 2
    recovered = read_state(cache_path)
    assert recovered is not None and recovered.is_complete


async def test_concurrent_managers_share_one_clone(tmp_path: Path) -> None:
    """Two managers racing on one cache key serialize through the file lock."""
    repo = _seed_content_repo(tmp_path)
    runner = RecordingContentRunner()
    first = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    second = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)

    bodies = await asyncio.gather(
        first.read_file(repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"),
        second.read_file(repo_url=str(repo), sub_dir="skills/x", ref="v1", file_name="SKILL.md"),
    )

    assert list(bodies) == [SKILL_BODY, SKILL_BODY]
    assert runner.clone_count == 1


async def test_workspace_stale_shallow_lock_recovers(tmp_path: Path) -> None:
    """A stale lock in a run cache is cleaned before the next prepare."""
    bare = _seed_workspace_repo(tmp_path)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_enabled=False,
    )
    first = await manager.prepare(_run(str(bare), "feature", run_id="run-lock-1"))
    lock = first.repo_path / "shallow.lock"
    lock.write_text("stale", encoding="utf-8")

    second = await manager.prepare(_run(str(bare), "feature", run_id="run-lock-2"))

    assert second.cache_hit is True
    assert second.base_commit == first.base_commit
    assert not lock.exists()
    state = read_state(second.repo_path)
    assert state is not None and state.is_complete


async def test_workspace_lock_conflict_is_retried_once(tmp_path: Path) -> None:
    """The workspace fetch path also cleans and retries a single lock conflict."""
    bare = _seed_workspace_repo(tmp_path)
    first = await GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_enabled=False,
    ).prepare(_run(str(bare), "feature", run_id="run-flaky-1"))
    runner = FlakyLockWorkspaceRunner()
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        runner=runner,
        push_enabled=False,
    )

    second = await manager.prepare(_run(str(bare), "feature", run_id="run-flaky-2"))

    assert second.cache_hit is True
    assert second.base_commit == first.base_commit
    assert runner.fetches == 2


async def test_workspace_incomplete_cache_is_rebuilt(tmp_path: Path) -> None:
    """An incomplete run cache is rebuilt and its commit still resolves."""
    bare = _seed_workspace_repo(tmp_path)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_enabled=False,
    )
    first = await manager.prepare(_run(str(bare), "feature", run_id="run-incomplete-1"))
    sentinel = first.repo_path / "interrupted-object"
    sentinel.write_text("partial", encoding="utf-8")
    mark_incomplete(first.repo_path, repo_url=str(bare), ref="feature")

    second = await manager.prepare(_run(str(bare), "feature", run_id="run-incomplete-2"))

    assert second.cache_hit is False
    assert second.base_commit == first.base_commit
    assert not sentinel.exists()
    rebuilt = read_state(second.repo_path)
    assert rebuilt is not None and rebuilt.is_complete


def test_startup_sweep_removes_incomplete_and_locked_legacy_caches(tmp_path: Path) -> None:
    """Startup deletes interrupted caches but keeps healthy marker-less caches."""
    root = tmp_path / "cache"

    complete = root / "complete" / "ref"
    (complete / ".git").mkdir(parents=True)
    (complete / ".git" / "shallow.lock").write_text("stale", encoding="utf-8")
    (complete / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    mark_complete(
        complete,
        repo_url="https://example.invalid/x.git",
        ref="main",
        commit="a" * 40,
    )

    incomplete = root / "incomplete" / "ref"
    incomplete.mkdir(parents=True)
    state_path(incomplete).write_text(
        '{"phase":"incomplete","repo_url":"https://example.invalid/x.git",'
        '"ref":"main","started_at":1}',
        encoding="utf-8",
    )

    legacy_locked = root / "legacy-locked" / "ref"
    (legacy_locked / ".git").mkdir(parents=True)
    (legacy_locked / ".git" / "shallow.lock").write_text("stale", encoding="utf-8")

    legacy_healthy = root / "legacy-healthy" / "ref"
    (legacy_healthy / ".git").mkdir(parents=True)
    (legacy_healthy / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    result = sweep_cache_roots(root)

    assert result.caches_removed == 2
    assert result.locks_removed == 1
    assert not incomplete.exists()
    assert not legacy_locked.exists()
    assert complete.is_dir()
    assert not (complete / ".git" / "shallow.lock").exists()
    assert legacy_healthy.is_dir()


async def test_startup_sweep_skips_a_cache_held_by_an_active_process(tmp_path: Path) -> None:
    """The sweep must not delete an incomplete cache while another process uses it."""
    root = tmp_path / "cache"
    cache_path = root / "repo" / "ref"
    cache_path.mkdir(parents=True)
    mark_incomplete(cache_path, repo_url="https://example.invalid/x.git", ref="main")
    async with cache_flock(root, cache_path):
        held = await asyncio.to_thread(sweep_cache_roots, root)
        assert held.caches_removed == 0
        assert cache_path.is_dir()
    released = sweep_cache_roots(root)
    assert released.caches_removed == 1
    assert not cache_path.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock crash semantics")
async def test_flock_is_released_when_holder_is_killed(tmp_path: Path) -> None:
    """SIGKILL releases the cross-process cache lock so recovery never blocks."""
    root = tmp_path / "cache"
    cache_path = root / "repo" / "ref"
    lock_path = lock_file_path(root, cache_path)
    lock_path.parent.mkdir(parents=True)
    script = (
        "import fcntl, os, sys, time\n"
        "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "print('locked', flush=True)\n"
        "time.sleep(60)\n"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(lock_path),
        stdout=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert await process.stdout.readline() == b"locked\n"
    process.kill()
    await process.wait()

    async with asyncio.timeout(5):
        async with cache_flock(root, cache_path):
            pass


def test_state_marker_is_read_back_after_atomic_write(tmp_path: Path) -> None:
    """A completed marker records repo, ref, and commit for later validation."""
    cache_path = tmp_path / "cache" / "repo" / "ref"
    cache_path.mkdir(parents=True)
    mark_incomplete(cache_path, repo_url="https://example.invalid/x.git", ref="main")
    interrupted = read_state(cache_path)
    assert interrupted is not None and not interrupted.is_complete

    mark_complete(
        cache_path,
        repo_url="https://example.invalid/x.git",
        ref="main",
        commit="b" * 40,
    )
    complete = read_state(cache_path)
    assert complete is not None and complete.is_complete
    assert complete.commit == "b" * 40

    remove_state(cache_path)
    assert read_state(cache_path) is None
