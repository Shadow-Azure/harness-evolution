"""Prepare orchestration against real SQLite state and a local bare remote."""

from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select
from sqlalchemy import update as sql_update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.db.models.evolution import (
    ProbeClusterRecord,
    evolution_rounds,
    evolution_runs,
)
from app.db.models.jobs import JobRunRecord
from app.service.evolution.engine.contracts import RunBlocked
from app.service.evolution.git_candidate import (
    CandidateTrace,
    EvolutionCandidateService,
)
from app.service.evolution.prepare import EvolutionPrepareService, RepositoryProbeReader
from app.third_party_api.git.workspace import GitOperationError, GitWorkspaceManager

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)


def _git(cwd: Path, *args: str) -> str:
    """Run one deterministic local git command."""
    return subprocess.run(
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _remote(tmp_path: Path) -> tuple[Path, str]:
    """Create one tagged local remote with a target subdirectory."""
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
    _git(seed, "commit", "-m", "initial")
    _git(seed, "tag", "v2.0.0")
    _git(seed, "push", "origin", "HEAD:refs/heads/main", "--tags")
    return bare, _git(seed, "rev-parse", "HEAD")


@pytest_asyncio.fixture
async def prepare_state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str]]:
    """Provide migrated SQLite state, two probes, and the real prepare service."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-09-prepare-test-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    bare, base_commit = _remote(tmp_path)
    async with database.transaction() as session:
        for index, attribute_type in enumerate(("model", "error"), start=1):
            probe_id = f"probe-{index}"
            bad_case_id = f"case-{index}"
            await session.execute(
                insert(probe_reports).values(
                    probe_id=probe_id,
                    session_id=f"session-{index}",
                    probe_type="skill",
                    probe_object="deep-research",
                    object_version="v2.0.0",
                    attribute_type=attribute_type,
                    probe_description=f"{attribute_type} issue",
                    probe_analysis=f"{attribute_type} analysis",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            await session.execute(
                insert(bad_cases).values(
                    bad_case_id=bad_case_id,
                    bad_case_session_id=f"session-{index}",
                    bad_case_type="behavior",
                    object_name="deep-research",
                    object_type="skill",
                    object_version="v2.0.0",
                    bad_case_agent_id=None,
                    reason="observed issue",
                    meta_data={},
                    source="fixture",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
            await session.execute(
                insert(bad_case_analysis).values(
                    bad_case_id=bad_case_id,
                    analysis_status="analyzed_issue",
                    probe_id=probe_id,
                    analysis_result={},
                    updated_at=NOW,
                ),
            )
    repository = EvolutionRepository(database)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    service = EvolutionPrepareService(
        repository,
        RepositoryProbeReader(ProbeQueryRepository(database)),
        manager,
    )
    try:
        yield database, repository, service, str(bare), base_commit
    finally:
        await database.dispose()


def _run_values(repo_url: str, base_commit: str, *, mode: str = "full") -> dict[str, object]:
    """Return one full run snapshot ready for prepare."""
    return {
        "id": "run-m5-09-prepare",
        "title": "deep-research evolution",
        "mode": mode,
        "engine_key": mode,
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": repo_url,
        "sub_dir": "skills/deep-research",
        "base_ref": "v2.0.0",
        "base_commit": base_commit,
        "window_from": None,
        "window_to": None,
        "models": [],
        "stats": {},
        "created_by": None,
        "created_at": NOW,
    }


def _job(run_id: str) -> JobRunRecord:
    """Build one evolution prepare job in launch payload shape."""
    return JobRunRecord(
        id="job-prepare",
        kind="evolution_prepare",
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="local",
        external_job_id=None,
        attempt=0,
        payload={
            "runId": run_id,
            "query": {
                "targetType": "skill",
                "targetName": "deep-research",
                "targetVersion": "v2.0.0",
                "from": None,
                "to": None,
                "models": [],
            },
        },
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


async def test_full_prepare_creates_workspace_clusters_rounds_and_is_idempotent(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
) -> None:
    """Full preparation advances all setup steps once and creates ranked rounds."""
    database, repository, service, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))

    result = await service.handle(_job("run-m5-09-prepare"))

    assert result["status"] == "running"
    assert result["progressUnit"] == 4
    assert result["rounds"] == 2
    run = await repository.get_run("run-m5-09-prepare")
    assert run is not None
    assert run.branch_name == "evo/20261028-run-m5-09-prepare"
    assert run.workspace_path is not None
    assert Path(run.workspace_path).is_dir()
    clusters = await repository.list_clusters(run.id)
    assert [cluster.probe_cluster_type for cluster in clusters] == ["model", "error"]
    assert all(cluster.confidence is not None for cluster in clusters)
    assert [cluster.rank for cluster in clusters] == [2, 1]
    rounds = await repository.list_rounds(run.id)
    assert [round_.status for round_ in rounds] == ["pending", "pending"]
    assert rounds[0].probe_cluster_id == clusters[1].probe_cluster_id

    repeated = await service.handle(_job(run.id))
    assert repeated["reused"] is True
    assert len(await repository.list_rounds(run.id)) == 2
    async with database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_runs).where(evolution_runs.c.id == run.id),
                )
            )
            .mappings()
            .one()
        )
    assert row["progress_unit"] == 4


async def test_cluster_only_prepare_skips_git_and_rounds(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
) -> None:
    """Cluster-only previews complete after scoring without repository writes."""
    _database, repository, service, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit, mode="cluster_only"))

    result = await service.handle(_job("run-m5-09-prepare"))

    assert result["status"] == "completed"
    assert result["rounds"] == 0
    run = await repository.get_run("run-m5-09-prepare")
    assert run is not None
    assert run.workspace_path is None
    assert run.branch_name is None
    assert await repository.list_rounds(run.id) == ()


async def test_candidate_accept_and_reject_preserve_run_branch_history(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """Accept fast-forwards and reject deletes only the temporary candidate."""
    database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    await prepare.handle(_job("run-m5-09-prepare"))
    run = await repository.get_run("run-m5-09-prepare")
    assert run is not None
    rounds = await repository.list_rounds(run.id)
    clusters = await repository.list_clusters(run.id)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    candidate_service = EvolutionCandidateService(repository, manager)
    first = await candidate_service.publish(run, rounds[0], _trace(clusters[1]))
    assert first.status == "evaluating"
    assert first.candidate_ref is not None
    assert first.candidate_commit is not None
    assert _remote_tag(repo_url, first.candidate_ref) == first.candidate_commit

    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == first.id)
            .values(eval_status="completed"),
        )
    fresh = await repository.get_round(first.id)
    assert fresh is not None
    accepted = await candidate_service.accept(
        run,
        fresh,
        _trace(clusters[1]),
        current_score=80.0,
        candidate_score=85.0,
        reason="候选分 85.0 高于基线 80.0（+5.0），按 external-verdict 规则接纳",
    )
    assert accepted.status == "accepted"
    assert accepted.commit_hash is not None
    assert accepted.candidate_ref is not None
    assert _remote_tag(repo_url, accepted.candidate_ref) is None
    accepted_commit = _remote_branch(repo_url, run.branch_name or "")
    assert accepted_commit == accepted.commit_hash

    updated = await repository.get_run(run.id)
    assert updated is not None
    second = await candidate_service.publish(updated, rounds[1], _trace(clusters[0]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == second.id)
            .values(eval_status="completed"),
        )
    fresh_second = await repository.get_round(second.id)
    assert fresh_second is not None
    rejected = await candidate_service.reject(
        updated,
        fresh_second,
        reason="候选分没有超过基线",
    )
    assert rejected.status == "rejected"
    assert _remote_branch(repo_url, run.branch_name or "") == accepted_commit
    assert _remote_tag(repo_url, second.candidate_ref or "") is None


async def test_transient_candidate_push_failure_blocks_after_three_attempts(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three transient failures retain the candidate and enter blocked/push."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    await prepare.handle(_job("run-m5-09-prepare"))
    run = await repository.get_run("run-m5-09-prepare")
    assert run is not None
    rounds = await repository.list_rounds(run.id)
    clusters = await repository.list_clusters(run.id)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )

    async def fail_push(*_args: object, **_kwargs: object) -> None:
        raise GitOperationError(
            "temporary transport failure",
            stage="push",
            retryable=True,
        )

    monkeypatch.setattr(manager, "push_candidate", fail_push)
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    candidate_service = EvolutionCandidateService(
        repository,
        manager,
        push_interval_seconds=5.0,
        sleep=sleep,
    )
    with pytest.raises(RunBlocked) as blocked:
        await candidate_service.publish(run, rounds[0], _trace(clusters[1]))

    assert blocked.value.stage == "push"
    assert sleeps == [5.0, 5.0]
    round_ = await repository.get_round(rounds[0].id)
    assert round_ is not None
    assert round_.status == "pushing"
    assert round_.push_status == "failed"
    assert round_.push_attempts == 3
    current = await repository.get_run(run.id)
    assert current is not None
    assert current.status == "blocked"
    assert current.blocked_stage == "push"


def _trace(cluster: ProbeClusterRecord) -> CandidateTrace:
    """Build the trace passed by the future stage orchestrator."""
    return CandidateTrace(
        cluster_id=cluster.probe_cluster_id,
        cluster_title=cluster.probe_cluster_description,
        probes=tuple(f"probe-{index}" for index in range(1, 3)),
        bad_cases=tuple(f"case-{index}" for index in range(1, 3)),
        analysis="transport analysis",
    )


def _remote_tag(repo_url: str, ref: str) -> str | None:
    """Read one candidate tag from the local bare remote."""
    if not ref:
        return None
    output = subprocess.run(
        ("git", "ls-remote", "--tags", repo_url, f"refs/tags/{ref}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return output.split("\t", 1)[0] if output else None


def _remote_branch(repo_url: str, branch: str) -> str | None:
    """Read one run branch from the local bare remote."""
    output = subprocess.run(
        ("git", "ls-remote", "--heads", repo_url, f"refs/heads/{branch}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return output.split("\t", 1)[0] if output else None
