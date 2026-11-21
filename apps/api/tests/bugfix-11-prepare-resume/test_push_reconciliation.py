"""Push reconciliation and detailed Git failure classification across restarts."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from app.db.models.evolution import EvolutionRunRecord
from app.third_party_api.git import workspace as workspace_module
from app.third_party_api.git.provider import GitPushProvider
from app.third_party_api.git.workspace import (
    GitOperationError,
    GitProcessResult,
    GitWorkspaceManager,
)

NOW = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)


def _git(cwd: Path, *args: str) -> str:
    """Run one deterministic local git command and return stdout."""
    return subprocess.run(
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repositories(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create one read-only upstream and one writable fork bare repository."""
    upstream = tmp_path / "upstream.git"
    seed = tmp_path / "seed"
    fork = tmp_path / "fork.git"
    _git(tmp_path, "init", "--bare", str(upstream))
    _git(tmp_path, "init", "--bare", str(fork))
    _git(tmp_path, "clone", str(upstream), str(seed))
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "config", "user.email", "test@example.invalid")
    target = seed / "skills" / "deep-research"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# Deep Research\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial target")
    _git(seed, "tag", "v2.0.0")
    _git(seed, "push", "origin", "HEAD:refs/heads/main", "--tags")
    return upstream, fork, _git(seed, "rev-parse", "HEAD")


def _run(repo_url: str, base_commit: str) -> EvolutionRunRecord:
    """Build one full run snapshot for a local-git reconciliation test."""
    return EvolutionRunRecord(
        id="run-resume",
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config={"gateway": "fake"},
        target_config_id="target-resume",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url=repo_url,
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref="v2.0.0",
        base_commit=base_commit,
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


class FakeProvider(GitPushProvider):
    """A provider whose fork is a local bare repository."""

    provider_id = "fake"
    git_username = "x-access-token"

    def __init__(self, fork_url: str) -> None:
        """Bind the local bare fork URL."""
        super().__init__(token=SecretStr("fake-provider-token"))
        self.fork_url = fork_url

    def remote_url(
        self,
        repo_url: str,
        *,
        fork: bool = False,
        owner: str | None = None,
    ) -> str:
        """Return the local path unchanged for both upstream and fork."""
        return repo_url

    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        """Return the writable fork path."""
        return self.fork_url

    async def open_pull_request(
        self,
        fork_url: str,
        upstream_url: str,
        branch: str,
        title: str,
    ) -> str | None:
        """Skip pull-request creation for the local-git test."""
        return None


def _manager(
    tmp_path: Path,
    fork: Path,
    runner: workspace_module.GitRunner | None = None,
) -> GitWorkspaceManager:
    """Build a manager that talks to the local bare fork."""
    return GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        runner=runner,
        provider=FakeProvider(str(fork)),
    )


def _advance_branch(prepared: Any) -> str:
    """Create one local run-branch commit on top of the published base."""
    path = Path(prepared.path)
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.invalid")
    (path / "README.md").write_text("# Run progress\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "advance run branch")
    return _git(path, "rev-parse", "HEAD")


async def test_publish_skips_push_when_remote_already_matches(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """Recovery does not push again when the ref already points at HEAD."""
    upstream, fork, base_commit = repositories
    run = _run(str(upstream), base_commit)
    manager = _manager(tmp_path, fork)
    prepared = await manager.prepare(run)
    assert _git(fork, "rev-parse", f"refs/heads/{prepared.branch}") == base_commit

    pushes: list[tuple[str, ...]] = []

    async def counting_runner(argv: tuple[str, ...], cwd: Path | None) -> GitProcessResult:
        if argv[:2] == ("git", "push"):
            pushes.append(argv)
        return await workspace_module._run_process(argv, cwd)

    resumed = _manager(tmp_path, fork, counting_runner)
    await resumed.publish_run_branch(prepared, run)

    assert pushes == []


async def test_nonzero_push_is_reconciled_when_remote_already_advanced(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """A killed client's non-zero push exits success when the remote has the commit."""
    upstream, fork, base_commit = repositories
    run = _run(str(upstream), base_commit)
    manager = _manager(tmp_path, fork)
    prepared = await manager.prepare(run)
    head = _advance_branch(prepared)

    async def killed_client(argv: tuple[str, ...], cwd: Path | None) -> GitProcessResult:
        result = await workspace_module._run_process(argv, cwd)
        if argv[:2] == ("git", "push"):
            return GitProcessResult(
                returncode=1,
                stdout=result.stdout,
                stderr="fatal: the remote end hung up unexpectedly",
            )
        return result

    resumed = _manager(tmp_path, fork, killed_client)
    await resumed.publish_run_branch(prepared, run)

    assert _git(fork, "rev-parse", f"refs/heads/{prepared.branch}") == head


async def test_real_push_failure_keeps_sanitized_detail(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """A push that did not update the remote still raises with a safe diagnostic."""
    upstream, fork, base_commit = repositories
    run = _run(str(upstream), base_commit)
    manager = _manager(tmp_path, fork)
    prepared = await manager.prepare(run)
    _advance_branch(prepared)

    async def denied(argv: tuple[str, ...], cwd: Path | None) -> GitProcessResult:
        if argv[:2] == ("git", "push"):
            return GitProcessResult(
                returncode=128,
                stdout="",
                stderr=(
                    "fatal: Authentication failed for "
                    "'https://x-access-token:ghp_supersecret@example.invalid/repo'"
                ),
            )
        return await workspace_module._run_process(argv, cwd)

    resumed = _manager(tmp_path, fork, denied)
    with pytest.raises(GitOperationError) as failure:
        await resumed.publish_run_branch(prepared, run)

    assert failure.value.stage == "push"
    assert failure.value.detail is not None
    assert "Authentication failed" in failure.value.detail
    assert "ghp_supersecret" not in failure.value.detail
