"""Real local-git contracts for preparation, candidate, accept, and reject."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.git_candidate import (
    CandidateTrace,
    build_accepted_message,
    build_candidate_message,
)
from app.third_party_api.git.workspace import (
    GitOperationError,
    GitWorkspaceManager,
    Patch,
    retry_push,
)

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=UTC)


def _git(cwd: Path, *args: str) -> str:
    """Run one deterministic local git command and return stdout."""
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def remote_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a bare remote with a tagged target directory and one commit."""
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(seed))
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "config", "user.email", "test@example.invalid")
    target = seed / "skills" / "deep-research"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# Deep Research\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial target")
    _git(seed, "tag", "v2.0.0")
    _git(seed, "push", "origin", "HEAD:refs/heads/main", "--tags")
    return bare, seed, _git(seed, "rev-parse", "HEAD")


def _run(repo_url: str, base_commit: str) -> EvolutionRunRecord:
    """Build one run snapshot for real local git operations."""
    return EvolutionRunRecord(
        id="run-m5-09",
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config={"gateway": "fake"},
        target_config_id="target-m5-09",
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


async def test_prepare_creates_isolated_workspace_and_run_branch(
    tmp_path: Path,
    remote_repo: tuple[Path, Path, str],
) -> None:
    """Preparation clones the tagged commit and creates a clean run branch."""
    bare, _seed, base_commit = remote_repo
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )

    prepared = await manager.prepare(_run(str(bare), base_commit))

    assert prepared.base_commit == base_commit
    assert prepared.branch == "evo/20261028-run-m5-09"
    assert prepared.path == tmp_path / "workspaces" / "run-m5-09"
    assert prepared.repo_path == tmp_path / "repos" / "target-m5-09"
    assert prepared.path.is_dir()
    assert (prepared.path / "skills" / "deep-research" / "SKILL.md").is_file()
    assert _git(prepared.path, "status", "--porcelain") == ""
    assert _git(prepared.path, "rev-parse", "HEAD") == base_commit
    assert _git(prepared.path, "branch", "--show-current") == prepared.branch


async def test_prepare_rejects_missing_ref_and_subdirectory(
    tmp_path: Path,
    remote_repo: tuple[Path, Path, str],
) -> None:
    """Invalid refs and target directories fail before any run branch exists."""
    bare, _seed, base_commit = remote_repo
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )

    with pytest.raises(GitOperationError, match="reference"):
        await manager.prepare(
            replace(_run(str(bare), base_commit), target_version="missing-tag"),
        )

    with pytest.raises(GitOperationError, match="subdirectory"):
        await manager.prepare(
            replace(_run(str(bare), base_commit), sub_dir="skills/missing"),
        )


async def test_candidate_accept_amends_ffs_run_branch_and_removes_candidate(
    tmp_path: Path,
    remote_repo: tuple[Path, Path, str],
) -> None:
    """Accepted work updates candidate and run refs without rewriting run history."""
    bare, _seed, base_commit = remote_repo
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    run = _run(str(bare), base_commit)
    prepared = await manager.prepare(run)
    trace = CandidateTrace(
        cluster_id="cluster-1",
        cluster_title="检索索引读取失败",
        probes=("probe-1",),
        bad_cases=("case-1",),
        analysis="读取快照前缺少字段校验。",
    )
    candidate_message = build_candidate_message(
        run,
        round_seq=1,
        trace=trace,
        patch_sha256="a" * 64,
        created_at=NOW,
        web_base_url="https://harness.example",
    )
    assert "https://harness.example/evolution/runs/run-m5-09?step=iteration" in candidate_message
    assert "https://harness.example/evolution/runs/run-m5-09?step=clusters&cluster=cluster-1" in (
        candidate_message
    )

    candidate = await manager.create_candidate(
        prepared,
        run_branch=prepared.branch,
        candidate_ref=f"{prepared.branch}/candidate/r1",
        patch=Patch(
            file="skills/deep-research/EVOLUTION.md",
            lines=("placeholder candidate",),
        ),
        message=candidate_message,
    )
    await manager.push_candidate(candidate, expected_remote_commit=None)
    remote_candidate = _git(bare, "rev-parse", f"refs/tags/{candidate.ref}")
    assert remote_candidate == candidate.commit

    accepted_message = build_accepted_message(
        run,
        round_seq=1,
        trace=trace,
        patch_sha256="a" * 64,
        created_at=NOW,
        evaluated_commit=candidate.commit,
        current_score=80.0,
        candidate_score=85.0,
        reason="候选分 85.0 高于基线 80.0（+5.0），按 external-verdict 规则接纳",
        web_base_url="https://harness.example",
    )
    final = await manager.accept_candidate(
        candidate,
        run_branch=prepared.branch,
        message=accepted_message,
    )

    assert final.commit != candidate.commit
    assert _git(bare, "rev-parse", prepared.branch) == final.commit
    run_branch_log = _git(bare, "log", "--format=%s", prepared.branch)
    assert "修复检索索引读取失败" in run_branch_log
    remote_candidate_after = subprocess.run(
        ("git", "ls-remote", "--tags", str(bare), f"refs/tags/{candidate.ref}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert remote_candidate_after == ""


async def test_reject_deletes_candidate_and_leaves_run_branch_unchanged(
    tmp_path: Path,
    remote_repo: tuple[Path, Path, str],
) -> None:
    """Rejected work removes only the candidate ref and returns to the baseline."""
    bare, _seed, base_commit = remote_repo
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    prepared = await manager.prepare(_run(str(bare), base_commit))
    candidate = await manager.create_candidate(
        prepared,
        run_branch=prepared.branch,
        candidate_ref=f"{prepared.branch}/candidate/r1",
        patch=Patch(file="skills/deep-research/EVOLUTION.md", lines=("rejected",)),
        message="candidate",
    )
    await manager.push_candidate(candidate, expected_remote_commit=None)

    await manager.reject_candidate(candidate, run_branch=prepared.branch)

    assert _git(bare, "rev-parse", prepared.branch) == base_commit
    assert _git(candidate.workspace_path, "branch", "--show-current") == prepared.branch
    remote_candidate_after = subprocess.run(
        ("git", "ls-remote", "--tags", str(bare), f"refs/tags/{candidate.ref}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert remote_candidate_after == ""


def test_commit_messages_are_traceable_and_probe_analysis_is_truncated(
    remote_repo: tuple[Path, Path, str],
) -> None:
    """Messages retain IDs and trailers while bounded probe analysis stays readable."""
    bare, _seed, base_commit = remote_repo
    run = _run(str(bare), base_commit)
    trace = CandidateTrace(
        cluster_id="cluster-1",
        cluster_title="检索索引读取失败",
        probes=("probe-1",),
        bad_cases=("case-1",),
        analysis="\n".join(f"line {index}" for index in range(40)),
    )

    candidate = build_candidate_message(
        run,
        round_seq=2,
        trace=trace,
        patch_sha256="b" * 64,
        created_at=NOW,
        web_base_url=None,
    )
    accepted = build_accepted_message(
        run,
        round_seq=2,
        trace=trace,
        patch_sha256="b" * 64,
        created_at=NOW,
        evaluated_commit="c" * 40,
        current_score=70.0,
        candidate_score=79.0,
        reason="候选分 79.0 高于基线 70.0（+9.0），按 external-verdict 规则接纳",
        web_base_url=None,
    )

    assert candidate.splitlines()[0].endswith("候选变更")
    assert "Harness-Run-Id: run-m5-09" in candidate
    assert "Harness-Cluster-Id: cluster-1" in candidate
    assert "完整推导见归因链接" in candidate
    assert "line 30" not in candidate
    assert "https://" not in candidate
    assert "Harness-Evaluated-Commit: " + ("c" * 40) in accepted
    assert "为什么接纳" in accepted


async def test_immediate_push_retry_stops_on_success_and_never_retries_permanent_errors() -> None:
    """Only transient failures retry, with two five-second waits before success."""
    attempts = 0
    sleeps: list[float] = []

    async def flaky_push() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise GitOperationError("temporary", stage="push", retryable=True)

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    completed = await retry_push(flaky_push, sleep=sleep)
    assert completed == 3
    assert sleeps == [5.0, 5.0]

    permanent_attempts = 0

    async def permanent_push() -> None:
        nonlocal permanent_attempts
        permanent_attempts += 1
        raise GitOperationError("denied", stage="push", retryable=False)

    with pytest.raises(GitOperationError, match="denied"):
        await retry_push(permanent_push, sleep=sleep)
    assert permanent_attempts == 1


def test_workspace_cleanup_keeps_active_and_newest_inactive_runs(tmp_path: Path) -> None:
    """Retention removes old inactive workspaces but never an active run."""
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    manager.workspaces_root.mkdir(parents=True)
    created: list[Path] = []
    for index in range(23):
        path = manager.workspaces_root / f"run-{index:02d}"
        path.mkdir()
        (path / "marker").touch(exist_ok=False)
        created.append(path)
    active = created[0]

    removed = manager.cleanup_workspaces(active_run_ids={active.name}, keep=20)

    assert active.exists()
    assert len(removed) == 2
    assert created[1] in removed
    assert created[2] in removed
