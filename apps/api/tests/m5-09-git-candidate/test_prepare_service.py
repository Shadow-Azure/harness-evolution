"""Prepare orchestration against real SQLite state and a local bare remote."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator
from dataclasses import replace
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
    EvolutionRunRecord,
    ProbeClusterRecord,
    evolution_rounds,
    evolution_runs,
)
from app.db.models.jobs import JobRunRecord
from app.main import create_app
from app.service.evolution.advance import EvolutionAdvanceService, EvolutionJobLifecycle
from app.service.evolution.engine.contracts import RunBlocked
from app.service.evolution.git_candidate import (
    CandidateTrace,
    EvolutionCandidateService,
)
from app.service.evolution.prepare import EvolutionPrepareService, RepositoryProbeReader
from app.service.evolution.state import StageConflict
from app.third_party_api.git.workspace import (
    GitOperationError,
    GitWorkspaceManager,
    PreparedWorkspace,
)

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
                    title="observed issue",
                    bad_case_description="observed issue",
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
    published_run = await repository.get_run(run.id)
    assert published_run is not None
    assert published_run.push_status == "succeeded"
    assert published_run.pushed_at is not None

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
    assert current.push_status == "failed"
    assert current.push_error is not None


async def test_disabled_push_persists_skipped_without_remote_or_evaluation(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """Local-only mode keeps the candidate local and never claims remote success."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "local-repos",
        workspaces_root=tmp_path / "local-workspaces",
        push_enabled=False,
    )
    local_prepare = EvolutionPrepareService(
        repository,
        prepare._probes,
        manager,
    )
    await local_prepare.handle(_job("run-m5-09-prepare"))
    run = await repository.get_run("run-m5-09-prepare")
    assert run is not None
    rounds = await repository.list_rounds(run.id)
    clusters = await repository.list_clusters(run.id)

    class Events:
        def __init__(self) -> None:
            self.types: list[str] = []

        async def record(self, _run_id: str, event_type: str, **_kwargs: object) -> None:
            self.types.append(event_type)

    events = Events()
    service = EvolutionCandidateService(
        repository,
        manager,
        events=events,  # type: ignore[arg-type]
    )

    published = await service.publish(run, rounds[0], _trace(clusters[1]))

    assert published.status == "skipped"
    assert published.push_status == "skipped"
    assert published.eval_status == "pending"
    assert published.finished_at is not None
    assert events.types[-1] == "candidate_committed"
    assert "push_started" not in events.types
    assert "push_succeeded" not in events.types
    assert "push_failed" not in events.types
    persisted_run = await repository.get_run(run.id)
    assert persisted_run is not None
    assert persisted_run.push_status == "skipped"
    assert persisted_run.pushed_at is None
    assert _remote_tag(repo_url, published.candidate_ref or "") is None
    assert _remote_branch(repo_url, run.branch_name or "") is None

    repeated = await service.publish(persisted_run, published, _trace(clusters[1]))
    assert repeated.id == published.id
    assert repeated.status == "skipped"
    assert events.types.count("candidate_committed") == 1


async def test_prepare_resumes_from_each_persisted_checkpoint(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash after advance to unit 1 must replay the remaining work, not conflict."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    original_prepare = prepare._workspaces.prepare
    failed = False

    async def fail_first(run: EvolutionRunRecord) -> PreparedWorkspace:
        nonlocal failed
        if not failed:
            failed = True
            raise GitOperationError("workspace unavailable", stage="workspace")
        return await original_prepare(run)

    monkeypatch.setattr(prepare._workspaces, "prepare", fail_first)
    with pytest.raises(GitOperationError):
        await prepare.handle(_job("run-m5-09-prepare"))
    checkpoint = await repository.get_run("run-m5-09-prepare")
    assert checkpoint is not None
    assert checkpoint.progress_unit == 1

    resumed = await prepare.handle(_job("run-m5-09-prepare"))

    assert resumed["status"] == "running"
    rounds = await repository.list_rounds("run-m5-09-prepare")
    assert len(rounds) == 2


@pytest.mark.parametrize("retryable", [True, False])
async def test_prepare_run_branch_push_failure_always_blocks_push(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    monkeypatch: pytest.MonkeyPatch,
    retryable: bool,
) -> None:
    """Transient and permanent publication failures retain the candidate-capable run."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))

    async def fail_push(_run: EvolutionRunRecord) -> PreparedWorkspace:
        raise GitOperationError(
            "push denied",
            stage="push",
            retryable=retryable,
        )

    monkeypatch.setattr(prepare._workspaces, "prepare", fail_push)

    with pytest.raises(RunBlocked) as blocked:
        await prepare.handle(_job("run-m5-09-prepare"))

    assert blocked.value.stage == "push"
    run = await repository.get_run("run-m5-09-prepare")
    assert run is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "push"
    assert run.error_stage == "push"


async def test_prepare_does_not_record_blocked_before_job_boundary(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepare persists state once and lets JobRunner own the durable blocked event."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))

    async def fail_push(_run: EvolutionRunRecord) -> PreparedWorkspace:
        raise GitOperationError("push denied", stage="push")

    class Events:
        def __init__(self) -> None:
            self.blocked = 0

        async def record(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def record_blocked(self, *_args: object, **_kwargs: object) -> int:
            self.blocked += 1
            return 1

    events = Events()
    service = EvolutionPrepareService(
        repository,
        prepare._probes,
        prepare._workspaces,
        events,
    )
    monkeypatch.setattr(service._workspaces, "prepare", fail_push)

    with pytest.raises(RunBlocked):
        await service.handle(_job("run-m5-09-prepare"))

    assert events.blocked == 0


@pytest.mark.parametrize(
    ("method_name", "checkpoint"),
    (
        ("write_cluster_confidence", 2),
        ("write_cluster_severity", 3),
        ("mark_prepared", 4),
    ),
)
async def test_prepare_resumes_after_failure_at_later_checkpoints(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    checkpoint: int,
) -> None:
    """Every persisted prepare checkpoint can replay without duplicate candidate work."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    original = getattr(repository, method_name)

    async def fail_once(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected checkpoint failure")

    monkeypatch.setattr(repository, method_name, fail_once)
    with pytest.raises(RuntimeError, match="injected"):
        await prepare.handle(_job("run-m5-09-prepare"))
    persisted = await repository.get_run("run-m5-09-prepare")
    assert persisted is not None
    assert persisted.progress_unit == checkpoint

    monkeypatch.setattr(repository, method_name, original)
    result = await prepare.handle(_job("run-m5-09-prepare"))

    assert result["status"] == "running"
    assert len(await repository.list_rounds("run-m5-09-prepare")) == 2


async def test_terminal_round_states_are_absorbing_and_opposite_actions_conflict(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """Accepted/rejected rounds cannot be rewritten by stale opposite-direction jobs."""
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
    service = EvolutionCandidateService(repository, manager)
    first = await service.publish(run, rounds[0], _trace(clusters[1]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == first.id)
            .values(eval_status="completed"),
        )
    fresh = await repository.get_round(first.id)
    assert fresh is not None
    accepted = await service.accept(
        run,
        fresh,
        _trace(clusters[1]),
        current_score=80.0,
        candidate_score=85.0,
        reason="accepted",
    )

    duplicate = await service.accept(
        run,
        accepted,
        _trace(clusters[1]),
        current_score=80.0,
        candidate_score=85.0,
        reason="accepted",
    )
    assert duplicate.status == "accepted"
    with pytest.raises(StageConflict):
        await service.reject(run, accepted, reason="stale reject")
    with pytest.raises(StageConflict):
        await repository.reject_round(accepted.id, finished_at=NOW)
    with pytest.raises(StageConflict):
        await repository.accept_round(
            accepted.id,
            final_commit="a" * 40,
            final_message="stale",
            finished_at=NOW,
        )

    rejected_round = await repository.get_round(rounds[0].id)
    assert rejected_round is not None
    assert rejected_round.status == "accepted"

    second = await service.publish(run, rounds[1], _trace(clusters[0]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == second.id)
            .values(eval_status="completed"),
        )
    second_fresh = await repository.get_round(second.id)
    assert second_fresh is not None
    rejected = await service.reject(run, second_fresh, reason="not better")
    with pytest.raises(StageConflict):
        await service.accept(
            run,
            rejected,
            _trace(clusters[0]),
            current_score=80.0,
            candidate_score=81.0,
            reason="stale accept",
        )


async def test_candidate_push_failure_records_durable_push_failed_event(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blocked push persists the precise push_failed event before the job boundary."""
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
        raise GitOperationError("denied", stage="push", retryable=False)

    monkeypatch.setattr(manager, "push_candidate", fail_push)

    class Events:
        def __init__(self) -> None:
            self.types: list[str] = []

        async def record(self, _run_id: str, event_type: str, **_kwargs: object) -> None:
            self.types.append(event_type)

    events = Events()
    service = EvolutionCandidateService(repository, manager, events=events)  # type: ignore[arg-type]
    with pytest.raises(RunBlocked):
        await service.publish(run, rounds[0], _trace(clusters[1]))

    assert events.types[-1] == "push_failed"


async def test_retryable_candidate_commit_failure_blocks_patch(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient patch/commit failure crosses the boundary as blocked patch."""
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

    async def fail_commit(*_args: object, **_kwargs: object) -> None:
        raise GitOperationError("commit lock timed out", stage="commit", retryable=True)

    monkeypatch.setattr(manager, "create_candidate", fail_commit)

    class Events:
        def __init__(self) -> None:
            self.types: list[str] = []

        async def record(self, _run_id: str, event_type: str, **_kwargs: object) -> None:
            self.types.append(event_type)

    events = Events()
    service = EvolutionCandidateService(
        repository,
        manager,
        events=events,  # type: ignore[arg-type]
    )

    with pytest.raises(RunBlocked) as blocked:
        await service.publish(
            run,
            rounds[0],
            _trace(clusters[1]),
            job_id="job-commit-timeout",
        )

    assert blocked.value.stage == "patch"
    persisted_run = await repository.get_run(run.id)
    persisted_round = await repository.get_round(rounds[0].id)
    assert persisted_run is not None
    assert persisted_run.status == "blocked"
    assert persisted_run.blocked_stage == "patch"
    assert persisted_round is not None
    assert persisted_round.status == "patching"
    assert "run_blocked" not in events.types


async def test_accept_cleanup_failure_persists_accepted_with_warning(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup warnings are durable accepted-event facts, never blocked publication."""
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

    class Events:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def record(
            self,
            _run_id: str,
            event_type: str,
            **kwargs: object,
        ) -> None:
            if event_type == "cluster_accepted":
                payload = kwargs.get("payload")
                assert isinstance(payload, dict)
                self.payloads.append(payload)

    events = Events()
    service = EvolutionCandidateService(
        repository,
        manager,
        events=events,  # type: ignore[arg-type]
    )
    candidate = await service.publish(run, rounds[0], _trace(clusters[1]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == candidate.id)
            .values(eval_status="completed"),
        )
    fresh = await repository.get_round(candidate.id)
    assert fresh is not None

    async def fail_cleanup(*_args: object, **_kwargs: object) -> None:
        raise GitOperationError("candidate delete denied", stage="push")

    monkeypatch.setattr(manager, "_delete_remote_tag", fail_cleanup)
    accepted = await service.accept(
        run,
        fresh,
        _trace(clusters[1]),
        current_score=80.0,
        candidate_score=85.0,
        reason="candidate wins",
        job_id="job-cleanup-warning",
    )

    assert accepted.status == "accepted"
    assert events.payloads[-1]["cleanupError"] == "candidate delete denied"
    persisted_run = await repository.get_run(run.id)
    assert persisted_run is not None
    assert persisted_run.status != "blocked"


@pytest.mark.parametrize(
    ("retryable", "expected_exception", "expected_stage"),
    [
        (True, RunBlocked, "patch"),
        (False, GitOperationError, "commit"),
    ],
)
async def test_accept_commit_failure_uses_shared_classifier(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    retryable: bool,
    expected_exception: type[BaseException],
    expected_stage: str,
) -> None:
    """Retryable commit failures block patch; permanent failures retain commit."""
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
    service = EvolutionCandidateService(repository, manager)
    candidate = await service.publish(run, rounds[0], _trace(clusters[1]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == candidate.id)
            .values(eval_status="completed"),
        )
    fresh = await repository.get_round(candidate.id)
    assert fresh is not None

    async def fail_accept(*_args: object, **_kwargs: object) -> None:
        raise GitOperationError(
            "commit failed",
            stage="commit",
            retryable=retryable,
        )

    monkeypatch.setattr(manager, "accept_candidate", fail_accept)
    with pytest.raises(expected_exception) as captured:
        await service.accept(
            run,
            fresh,
            _trace(clusters[1]),
            current_score=80.0,
            candidate_score=85.0,
            reason="accepted",
        )

    assert getattr(captured.value, "stage", None) == expected_stage
    persisted_run = await repository.get_run(run.id)
    assert persisted_run is not None
    if retryable:
        assert persisted_run.status == "blocked"
        assert persisted_run.blocked_stage == "patch"
        assert persisted_run.error_stage == "commit"


async def test_reject_propagates_run_branch_restore_failure(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure to restore the run branch cannot be reported as a rejected success."""
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
    service = EvolutionCandidateService(repository, manager)
    current = await service.publish(run, rounds[0], _trace(clusters[1]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == current.id)
            .values(eval_status="completed"),
        )
    fresh = await repository.get_round(current.id)
    assert fresh is not None

    async def fail_switch(*_args: object, **_kwargs: object) -> str:
        raise GitOperationError("cannot switch", stage="workspace")

    monkeypatch.setattr(manager, "reject_candidate", fail_switch)
    with pytest.raises(GitOperationError, match="cannot switch"):
        await service.reject(run, fresh, reason="reject")
    persisted = await repository.get_round(current.id)
    assert persisted is not None
    assert persisted.status != "rejected"


async def test_advance_service_publishes_real_candidate_and_lifecycle_queues_it(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """A completed prepare is reachable from the production candidate stage boundary."""
    database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    prepare_job = _job("run-m5-09-prepare")
    await prepare.handle(prepare_job)

    class Jobs:
        def __init__(self) -> None:
            self.submitted: list[dict[str, object]] = []

        async def submit(
            self,
            *,
            kind: str,
            payload: object,
            ref_id: str | None,
            created_by: str | None,
        ) -> object:
            self.submitted.append(
                {
                    "kind": kind,
                    "payload": payload,
                    "refId": ref_id,
                    "createdBy": created_by,
                },
            )
            return object()

    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    jobs = Jobs()
    lifecycle = EvolutionJobLifecycle(repository, jobs, manager)
    await lifecycle.on_terminal(
        replace(prepare_job, status="completed", finished_at=NOW),
    )
    assert jobs.submitted == [
        {
            "kind": "evolution_advance",
            "payload": {"runId": "run-m5-09-prepare"},
            "refId": "run-m5-09-prepare",
            "createdBy": None,
        },
    ]

    candidate_service = EvolutionCandidateService(repository, manager)
    advance = EvolutionAdvanceService(
        repository,
        candidate_service,
        ProbeQueryRepository(database),
    )
    advance_job = replace(
        _job("run-m5-09-prepare"),
        id="job-advance",
        kind="evolution_advance",
        payload={"runId": "run-m5-09-prepare"},
    )

    result = await advance.handle(advance_job)

    assert result["published"] is True
    rounds = await repository.list_rounds("run-m5-09-prepare")
    assert rounds[0].status == "evaluating"
    assert rounds[0].candidate_ref is not None
    assert _remote_tag(repo_url, rounds[0].candidate_ref) == rounds[0].candidate_commit

    jobs.submitted.clear()
    await lifecycle.on_terminal(
        replace(
            prepare_job,
            status="completed",
            finished_at=NOW,
        ),
    )

    assert jobs.submitted == []


async def test_advance_waits_for_an_earlier_round_to_finish(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """A later pending round must not overtake the round already under evaluation."""
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
    candidates = EvolutionCandidateService(repository, manager)
    first = await candidates.publish(run, rounds[0], _trace(clusters[1]))
    assert first.status == "evaluating"
    advance = EvolutionAdvanceService(
        repository,
        candidates,
        ProbeQueryRepository(_database),
    )

    result = await advance.handle(
        replace(
            _job("run-m5-09-prepare"),
            id="job-advance",
            kind="evolution_advance",
            payload={"runId": run.id},
        ),
    )

    assert result["published"] is False
    refreshed = await repository.list_rounds(run.id)
    assert [round_.status for round_ in refreshed] == ["evaluating", "pending"]
    assert refreshed[1].candidate_ref is None


async def test_duplicate_advance_calls_publish_only_the_first_round(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """Sequential duplicate jobs consume one round and leave the next pending."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    await prepare.handle(_job("run-m5-09-prepare"))
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    candidates = EvolutionCandidateService(repository, manager)
    advance = EvolutionAdvanceService(
        repository,
        candidates,
        ProbeQueryRepository(_database),
    )
    job = replace(
        _job("run-m5-09-prepare"),
        id="job-advance",
        kind="evolution_advance",
        payload={"runId": "run-m5-09-prepare"},
    )

    first = await advance.handle(job)
    duplicate = await advance.handle(job)

    assert first["published"] is True
    assert duplicate["published"] is False
    rounds = await repository.list_rounds("run-m5-09-prepare")
    assert [round_.status for round_ in rounds] == ["evaluating", "pending"]
    assert rounds[1].candidate_ref is None


async def test_concurrent_advance_claims_only_one_pending_round(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """Atomic round claiming prevents duplicate publication under concurrent jobs."""
    _database, repository, prepare, repo_url, base_commit = prepare_state
    await repository.create_run(_run_values(repo_url, base_commit))
    await prepare.handle(_job("run-m5-09-prepare"))
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
    )
    candidates = EvolutionCandidateService(repository, manager)
    advance = EvolutionAdvanceService(
        repository,
        candidates,
        ProbeQueryRepository(_database),
    )
    job = replace(
        _job("run-m5-09-prepare"),
        id="job-advance",
        kind="evolution_advance",
        payload={"runId": "run-m5-09-prepare"},
    )

    results = await asyncio.gather(advance.handle(job), advance.handle(job))

    assert sum(bool(result["published"]) for result in results) == 1
    rounds = await repository.list_rounds("run-m5-09-prepare")
    assert [round_.status for round_ in rounds] == ["evaluating", "pending"]
    assert rounds[1].candidate_ref is None


@pytest.mark.parametrize("decision", ["accept", "reject"])
async def test_advance_publishes_next_round_after_prior_round_is_terminal(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
    decision: str,
) -> None:
    """Accepted and rejected rounds both unlock the next sequential round."""
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
    candidates = EvolutionCandidateService(repository, manager)
    first = await candidates.publish(run, rounds[0], _trace(clusters[1]))
    async with database.transaction() as session:
        await session.execute(
            sql_update(evolution_rounds)
            .where(evolution_rounds.c.id == first.id)
            .values(eval_status="completed"),
        )
    fresh = await repository.get_round(first.id)
    assert fresh is not None
    if decision == "accept":
        terminal = await candidates.accept(
            run,
            fresh,
            _trace(clusters[1]),
            current_score=80.0,
            candidate_score=85.0,
            reason="candidate wins",
        )
    else:
        terminal = await candidates.reject(run, fresh, reason="candidate loses")
    assert terminal.status == decision + "ed"
    advance = EvolutionAdvanceService(
        repository,
        candidates,
        ProbeQueryRepository(database),
    )

    result = await advance.handle(
        replace(
            _job("run-m5-09-prepare"),
            id="job-advance",
            kind="evolution_advance",
            payload={"runId": run.id},
        ),
    )

    assert result["published"] is True
    refreshed = await repository.list_rounds(run.id)
    assert [round_.status for round_ in refreshed] == [terminal.status, "evaluating"]


async def test_composition_root_registers_candidate_advance_handler(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """The real app, rather than tests alone, owns the advance job handler."""
    database, _repository, _prepare, _repo_url, _base_commit = prepare_state
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "composition",
            jwt_secret=SecretStr("m5-09-composition-test-secret"),
        ),
        database=database,
    )

    assert app.state.evolution_advance is not None
    assert "evolution_advance" in app.state.jobs._handlers


async def test_prepare_only_workspace_injection_cannot_fall_back_to_real_candidate_manager(
    prepare_state: tuple[Database, EvolutionRepository, EvolutionPrepareService, str, str],
    tmp_path: Path,
) -> None:
    """One injected prepare-only manager keeps candidate/lifecycle in explicit safe mode."""
    database, _repository, _prepare, _repo_url, _base_commit = prepare_state

    class PrepareOnlyWorkspace:
        def __init__(self) -> None:
            self.cleaned: list[set[str]] = []

        async def prepare(self, run: EvolutionRunRecord) -> PreparedWorkspace:
            root = tmp_path / "prepare-only" / run.id
            root.mkdir(parents=True, exist_ok=True)
            return PreparedWorkspace(
                repo_path=root / "repo",
                path=root / "workspace",
                ref=run.target_version,
                base_commit="a" * 40,
                branch=f"evo/{run.created_at:%Y%m%d}-{run.id}",
            )

        def cleanup_workspaces(
            self,
            *,
            active_run_ids: set[str],
            keep: int = 20,
        ) -> tuple[Path, ...]:
            del keep
            self.cleaned.append(set(active_run_ids))
            return ()

    workspace = PrepareOnlyWorkspace()
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "injected-composition",
            jwt_secret=SecretStr("m5-09-injected-workspace-secret"),
        ),
        database=database,
        git_workspaces=workspace,
    )

    assert app.state.evolution_candidates._workspaces is workspace
    assert app.state.evolution_lifecycle._workspaces is workspace
    assert app.state.evolution_lifecycle._schedule_candidate_advance is False


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
