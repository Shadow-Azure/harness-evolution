"""Per-run push target selection and provider failure classification."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.db.models.evolution import EvolutionRunRecord
from app.third_party_api.git.provider import (
    GitPushProvider,
    GitPushProviderError,
)
from app.third_party_api.git.workspace import (
    GitOperationError,
    GitWorkspaceManager,
    Patch,
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
    """Build one full run snapshot for a local-git provider test."""
    return EvolutionRunRecord(
        id="run-fork",
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config={"gateway": "fake"},
        target_config_id="target-fork",
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

    def __init__(
        self,
        fork_url: str | None = None,
        *,
        failure: GitPushProviderError | None = None,
    ) -> None:
        super().__init__(token=SecretStr("fake-provider-token"))
        self.fork_url = fork_url
        self.failure = failure
        self.calls: list[str] = []

    def remote_url(
        self,
        repo_url: str,
        *,
        fork: bool = False,
        owner: str | None = None,
    ) -> str:
        return repo_url

    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        self.calls.append(upstream_url)
        if self.failure is not None:
            raise self.failure
        assert self.fork_url is not None
        return self.fork_url

    async def open_pull_request(
        self,
        fork_url: str,
        upstream_url: str,
        branch: str,
        title: str,
    ) -> str | None:
        return None


def _candidate_message(run: EvolutionRunRecord) -> str:
    """Return one commit message carrying the required run trailer."""
    return f"fix: adjust research instructions\n\nHarness-Run-Id: {run.id}"


async def test_prepare_candidate_and_accept_share_the_per_run_fork(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """Every push goes to the provider fork derived once for this run."""
    upstream, fork, base_commit = repositories
    run = _run(str(upstream), base_commit)
    provider = FakeProvider(str(fork))
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        provider=provider,
    )

    prepared = await manager.prepare(run)

    assert provider.calls == [str(upstream)]
    assert prepared.push_url == str(fork)
    assert (
        _git(
            fork,
            "rev-parse",
            f"refs/heads/{prepared.branch}",
        )
        == base_commit
    )
    assert _git(prepared.path, "remote", "get-url", "push") == str(fork)

    candidate = await manager.create_candidate(
        prepared,
        run_branch=prepared.branch,
        candidate_ref=f"{prepared.branch}/candidate/r1",
        patch=Patch(
            file="skills/deep-research/SKILL.md",
            lines=("# Deep Research v2\n",),
            overwrite=True,
        ),
        message=_candidate_message(run),
        expected_run_id=run.id,
    )
    await manager.push_candidate(candidate, expected_remote_commit=None)

    assert candidate.push_url == str(fork)
    assert _git(fork, "rev-parse", f"refs/tags/{candidate.ref}") == candidate.commit

    accepted = await manager.accept_candidate(
        candidate,
        run_branch=prepared.branch,
        message=(
            "fix: adjust research instructions\n\n"
            f"Harness-Run-Id: {run.id}\n"
            f"Harness-Evaluated-Commit: {candidate.commit}"
        ),
    )

    assert _git(fork, "rev-parse", f"refs/heads/{prepared.branch}") == accepted.commit
    assert _git(fork, "tag", "--list", candidate.ref) == ""


async def test_prepare_reuses_the_persisted_push_target_without_fork_lookup(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """A retry uses the run snapshot instead of asking the host again."""
    upstream, fork, base_commit = repositories
    run = replace(
        _run(str(upstream), base_commit),
        push_repo_url=str(fork),
    )
    provider = FakeProvider(str(fork))
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        provider=provider,
    )

    prepared = await manager.prepare(run)

    assert provider.calls == []
    assert prepared.push_url == str(fork)
    assert _git(fork, "rev-parse", f"refs/heads/{prepared.branch}") == base_commit


async def test_provider_failure_becomes_a_sanitized_push_error(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """A rejected PAT blocks the push stage without leaking the credential."""
    upstream, _fork, base_commit = repositories
    run = _run(str(upstream), base_commit)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        provider=FakeProvider(
            failure=GitPushProviderError(
                "git host API request failed",
                status_code=401,
            ),
        ),
    )

    with pytest.raises(
        GitOperationError,
        match=r"push fork preparation failed \(HTTP 401\)",
    ) as raised:
        await manager.prepare(run)

    assert raised.value.stage == "push"
    assert raised.value.retryable is False
    assert "fake-provider-token" not in str(raised.value)


async def test_global_push_url_remains_the_fallback_without_a_provider(
    tmp_path: Path,
    repositories: tuple[Path, Path, str],
) -> None:
    """Existing HE_GIT_PUSH_URL deployments keep pushing to their configured fork."""
    upstream, fork, base_commit = repositories
    run = _run(str(upstream), base_commit)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_url=str(fork),
    )

    prepared = await manager.prepare(run)

    assert prepared.push_url == str(fork)
    assert _git(fork, "rev-parse", f"refs/heads/{prepared.branch}") == base_commit
