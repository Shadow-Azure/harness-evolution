"""Placeholder evaluation gateway and durable poller contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import (
    evolution_rounds,
    evolution_runs,
    probe_clusters,
)
from app.errors import AppError, ErrorCode
from app.service.evolution.engine.contracts import (
    EvalGateway,
    EvalGatewayConfig,
    EvalRequest,
    EvalResult,
    EvalStatus,
    EvalSubmission,
    FakeEvalGateway,
)
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.eval_poller import EvolutionEvalPoller
from app.service.evolution.stages import EvolutionStageService

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@dataclass
class SubmittedJob:
    """One job captured from the poller without starting a worker."""

    kind: str
    payload: Mapping[str, Any]
    ref_id: str | None
    created_by: str | None


@dataclass
class JobCapture:
    """Minimal JobRunner seam used to assert exact follow-up scheduling."""

    jobs: list[SubmittedJob] = field(default_factory=list)
    failures_remaining: int = 0

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> SubmittedJob:
        """Capture one durable job submission."""
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("simulated follow-up submission failure")
        if any(job.kind == kind and job.ref_id == ref_id for job in self.jobs):
            raise AppError(
                status_code=409,
                code=ErrorCode.RUN_BUSY,
                message="another stage job is already active for this run",
            )
        job = SubmittedJob(
            kind=kind,
            payload=dict(payload),
            ref_id=ref_id,
            created_by=created_by,
        )
        self.jobs.append(job)
        return job


@pytest_asyncio.fixture
async def eval_state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository]]:
    """Provide migrated SQLite state for one full evaluation run."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-10-eval-test-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    await repository.create_run(
        {
            "id": "run-eval",
            "title": "placeholder eval",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": str(tmp_path / "example.git"),
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261028-run-eval",
            "repo_path": str(tmp_path / "repos" / "run-eval"),
            "workspace_path": str(tmp_path / "workspaces" / "run-eval"),
            "status": "running",
            "progress_unit": 4,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-eval",
                run_id="run-eval",
                seq=1,
                probe_cluster_description="placeholder issue",
                probe_cluster_type="error",
                confidence=0.9,
                impact=0.8,
                severity=0.8,
                rank=1,
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id="round-eval",
                run_id="run-eval",
                probe_cluster_id="cluster-eval",
                seq=1,
                status="evaluating",
                candidate_ref="evo/20261028-run-eval/candidate/r1",
                candidate_commit="b" * 40,
                candidate_message="candidate",
                push_status="succeeded",
                eval_external_id="fake:run-eval:round-eval:" + "b" * 40,
                eval_status="evaluating",
                eval_attempts=1,
                eval_next_poll_at=NOW - timedelta(seconds=1),
                eval_started_at=NOW - timedelta(minutes=1),
            ),
        )
    try:
        yield database, repository
    finally:
        await database.dispose()


def _request() -> EvalRequest:
    """Build one fully populated internal evaluation request."""
    return EvalRequest(
        run_id="run-eval",
        evolution_round_id="round-eval",
        repo_url="https://example.invalid/repo.git",
        ref="evo/20261028-run-eval/candidate/r1",
        commit="b" * 40,
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        cluster_id="cluster-eval",
        idempotency_key="run-eval:1:bbbb",
    )


async def test_fake_gateway_implements_submit_status_result_contract() -> None:
    """The placeholder gateway is deterministic and restart-safe from its eval id."""
    gateway = FakeEvalGateway(
        EvalGatewayConfig.from_mapping(
            {
                "currentScore": 81.5,
                "candidateScore": 87.0,
                "verdict": "accept",
            },
        ),
    )

    submission = await gateway.submit(_request())
    status = await gateway.get_status(submission.eval_id)
    result = await gateway.get_result(submission.eval_id)

    assert isinstance(submission, EvalSubmission)
    assert submission.eval_id == "fake:run-eval:round-eval:" + "b" * 40
    assert status == EvalStatus(status="completed")
    assert result.current_score == 81.5
    assert result.candidate_score == 87.0
    assert result.external_verdict == "accept"


def test_eval_result_rejects_malformed_metrics() -> None:
    """Malformed external result shapes cannot silently become trusted scores."""
    with pytest.raises(ValueError, match="objects"):
        EvalResult.from_payload(
            {
                "currentScore": 80,
                "candidateScore": 90,
                "externalVerdict": "accept",
                "metrics": ["not-an-object"],
            },
        )


def test_eval_result_rejects_boolean_scores() -> None:
    """Booleans are JSON scalars but never valid numeric evaluation scores."""
    with pytest.raises(ValueError, match="scores"):
        EvalResult.from_payload(
            {
                "currentScore": True,
                "candidateScore": 90,
                "externalVerdict": "accept",
                "metrics": [],
            },
        )


async def test_poller_skips_not_due_and_restarts_queued_poll(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """Persisted next_poll_at is the only restart timer for waiting evaluations."""
    database, repository = eval_state
    await repository.mark_eval_waiting("round-eval", next_poll_at=NOW + timedelta(minutes=5))
    gateway = FakeEvalGateway(EvalGatewayConfig.from_mapping({"status": "running"}))
    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 0

    async with database.transaction() as session:
        await session.execute(
            update(evolution_rounds)
            .where(evolution_rounds.c.id == "round-eval")
            .values(eval_next_poll_at=NOW - timedelta(seconds=1)),
        )
    assert await poller.run_once() == 1
    round_ = await repository.get_round("round-eval")
    assert round_ is not None
    assert round_.eval_status == "evaluating"
    assert round_.eval_next_poll_at == NOW + timedelta(minutes=5)
    assert jobs.jobs == []


async def test_poller_completed_saves_result_once_and_submits_apply(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """A completed evaluation persists normalized scores and schedules one apply."""
    _database, repository = eval_state
    gateway = FakeEvalGateway(
        EvalGatewayConfig.from_mapping(
            {
                "status": "completed",
                "currentScore": 80,
                "candidateScore": 90,
                "verdict": "accept",
                "metrics": [{"apiKey": "s3cr3t", "score": 1}],
            },
        ),
    )
    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 1
    round_ = await repository.get_round("round-eval")
    assert round_ is not None
    assert round_.status == "evaluating"
    assert round_.eval_status == "completed"
    assert round_.eval_current == 80.0
    assert round_.eval_candidate == 90.0
    assert round_.eval_result == {
        "currentScore": 80.0,
        "candidateScore": 90.0,
        "externalVerdict": "accept",
        "metrics": [{"apiKey": "<redacted>", "score": 1}],
    }
    assert "s3cr3t" not in str(round_.eval_result)
    assert [job.kind for job in jobs.jobs] == ["evolution_apply"]
    assert jobs.jobs[0].ref_id == "run-eval"
    assert jobs.jobs[0].payload["evolutionRoundId"] == "round-eval"

    class EmptyProbes:
        async def list_rows_by_ids(self, probe_ids: tuple[str, ...]) -> tuple[object, ...]:
            del probe_ids
            return ()

    run = await repository.get_run("run-eval")
    clusters = await repository.list_clusters("run-eval")
    assert run is not None
    step = await EvolutionStageService(
        repository,
        cast(Any, EmptyProbes()),
    ).build_step_payload(run, clusters, "iteration")
    assert step.key == "iteration"
    assert step.payload.rounds[0].eval.current == 80.0
    assert step.payload.rounds[0].eval.candidate == 90.0

    assert await poller.run_once() == 0
    assert [job.kind for job in jobs.jobs] == ["evolution_apply"]


async def test_completed_eval_followup_recovers_after_submit_failure(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """A completed result remains a durable apply marker until a job exists."""
    database, repository = eval_state
    gateway = FakeEvalGateway(
        EvalGatewayConfig.from_mapping(
            {
                "status": "completed",
                "currentScore": 80,
                "candidateScore": 90,
                "verdict": "accept",
            },
        ),
    )
    jobs = JobCapture(failures_remaining=1)
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 1
    round_ = await repository.get_round("round-eval")
    assert round_ is not None
    assert round_.eval_status == "completed"
    assert jobs.jobs == []

    await database.dispose()
    await database.start()
    assert await poller.run_once() == 1
    assert [job.kind for job in jobs.jobs] == ["evolution_apply"]


async def _persist_completed_eval(
    database: Database,
    *,
    run_status: str,
) -> None:
    """Persist one completed result while placing its run in the requested state."""
    async with database.transaction() as session:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == "run-eval")
            .values(status=run_status),
        )
        await session.execute(
            update(evolution_rounds)
            .where(evolution_rounds.c.id == "round-eval")
            .values(
                eval_status="completed",
                eval_next_poll_at=None,
                eval_finished_at=NOW,
                eval_result={
                    "currentScore": 80.0,
                    "candidateScore": 90.0,
                    "externalVerdict": "accept",
                    "metrics": [],
                },
                eval_current=80.0,
                eval_candidate=90.0,
            ),
        )


@pytest.mark.parametrize("run_status", ["failed", "blocked", "completed"])
async def test_completed_eval_on_inactive_run_never_schedules_apply(
    eval_state: tuple[Database, EvolutionRepository],
    run_status: str,
) -> None:
    """Only a running full run may turn a completed evaluation into apply work."""
    database, repository = eval_state
    await _persist_completed_eval(database, run_status=run_status)
    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: FakeEvalGateway(EvalGatewayConfig.from_mapping({})),
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 0
    assert await poller.run_once() == 0
    assert jobs.jobs == []


async def test_resumed_blocked_eval_schedules_apply_exactly_once(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """An explicit resume makes a durable completed evaluation schedulable once."""
    database, repository = eval_state
    await _persist_completed_eval(database, run_status="blocked")
    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: FakeEvalGateway(EvalGatewayConfig.from_mapping({})),
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 0
    await repository.mark_resumed("run-eval")
    assert await poller.run_once() == 1
    assert [job.kind for job in jobs.jobs] == ["evolution_apply"]
    assert await poller.run_once() == 0
    assert [job.kind for job in jobs.jobs] == ["evolution_apply"]


async def test_malformed_gateway_status_blocks_instead_of_poisoning_scan(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """An unknown external status becomes one blocked eval, not a hot error loop."""
    _database, repository = eval_state

    class UnknownStatusGateway:
        config = EvalGatewayConfig.from_mapping({})

        async def get_status(self, eval_id: str) -> EvalStatus:
            del eval_id
            return EvalStatus(status=cast(Any, "mystery"))

    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        cast(Any, lambda _run: UnknownStatusGateway()),
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 1
    round_ = await repository.get_round("round-eval")
    run = await repository.get_run("run-eval")
    assert round_ is not None and run is not None
    assert round_.eval_status == "failed"
    assert run.status == "blocked"
    assert await poller.run_once() == 0


async def test_malformed_evaluation_does_not_starve_later_due_run(
    eval_state: tuple[Database, EvolutionRepository],
    tmp_path: Path,
) -> None:
    """One malformed external status does not abort a batch with a healthy later run."""
    database, repository = eval_state
    await repository.create_run(
        {
            "id": "run-healthy",
            "title": "healthy eval",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/healthy.git",
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "d" * 40,
            "branch_name": "evo/20261028-run-healthy",
            "repo_path": str(tmp_path / "repo-healthy"),
            "workspace_path": str(tmp_path / "workspace-healthy"),
            "status": "running",
            "progress_unit": 4,
            "stats": {},
            "created_by": None,
            "created_at": NOW + timedelta(seconds=1),
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-healthy",
                run_id="run-healthy",
                seq=1,
                probe_cluster_description="healthy issue",
                probe_cluster_type="error",
                confidence=0.8,
                impact=0.8,
                severity=0.8,
                rank=1,
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id="round-healthy",
                run_id="run-healthy",
                probe_cluster_id="cluster-healthy",
                seq=1,
                status="evaluating",
                candidate_ref="evo/20261028-run-healthy/candidate/r1",
                candidate_commit="e" * 40,
                candidate_message="candidate",
                push_status="succeeded",
                eval_external_id="fake:run-healthy:round-healthy:" + "e" * 40,
                eval_status="evaluating",
                eval_attempts=1,
                eval_next_poll_at=NOW,
                eval_started_at=NOW - timedelta(minutes=1),
            ),
        )

    class MixedStatusGateway:
        config = EvalGatewayConfig.from_mapping({})

        def __init__(self, run_id: str) -> None:
            self._run_id = run_id

        async def get_status(self, eval_id: str) -> EvalStatus:
            del eval_id
            if self._run_id == "run-eval":
                return EvalStatus(status=cast(Any, "mystery"))
            return EvalStatus(status="completed")

        async def get_result(self, eval_id: str) -> EvalResult:
            del eval_id
            return EvalResult(
                current_score=70.0,
                candidate_score=75.0,
                external_verdict="accept",
            )

    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda run: cast(Any, MixedStatusGateway(run.id)),
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 2
    bad = await repository.get_round("round-eval")
    healthy = await repository.get_round("round-healthy")
    assert bad is not None and healthy is not None
    assert bad.eval_status == "failed"
    assert healthy.eval_status == "completed"
    assert [job.payload["evolutionRoundId"] for job in jobs.jobs] == ["round-healthy"]


async def test_poller_timeout_wins_even_when_gateway_still_reports_running(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """Timeout fallback blocks an overdue round without auto-resubmission."""
    database, repository = eval_state
    async with database.transaction() as session:
        await session.execute(
            update(evolution_rounds)
            .where(evolution_rounds.c.id == "round-eval")
            .values(eval_started_at=NOW - timedelta(hours=3)),
        )
    gateway = FakeEvalGateway(EvalGatewayConfig.from_mapping({"status": "running"}))
    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 1
    run = await repository.get_run("run-eval")
    round_ = await repository.get_round("round-eval")
    assert run is not None
    assert round_ is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "eval"
    assert run.eval_status == "failed"
    assert round_.eval_status == "timeout"
    assert round_.eval_next_poll_at is None
    assert jobs.jobs == []


async def test_poller_gateway_error_blocks_without_apply_or_resubmit(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """Transport failures become a safe blocked eval state, never an apply job."""
    _database, repository = eval_state

    class FailingGateway:
        config = EvalGatewayConfig.from_mapping({})

        async def get_status(self, eval_id: str) -> EvalStatus:
            del eval_id
            raise RuntimeError("provider token=s3cr3t")

    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        cast(Any, lambda _run: FailingGateway()),
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 1
    run = await repository.get_run("run-eval")
    round_ = await repository.get_round("round-eval")
    assert run is not None and round_ is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "eval"
    assert round_.eval_status == "failed"
    assert "s3cr3t" not in (round_.eval_error or "")
    assert jobs.jobs == []


async def test_cluster_only_and_push_skipped_rounds_are_not_polled(
    eval_state: tuple[Database, EvolutionRepository],
) -> None:
    """Rounds without a real published candidate never enter external evaluation."""
    database, repository = eval_state
    async with database.transaction() as session:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == "run-eval")
            .values(mode="cluster_only"),
        )
    jobs = JobCapture()
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: FakeEvalGateway(EvalGatewayConfig.from_mapping({})),
        jobs,
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )

    assert await poller.run_once() == 0
    async with database.session() as session:
        status: str = (
            await session.execute(
                select(evolution_rounds.c.eval_status).where(
                    evolution_rounds.c.id == "round-eval",
                ),
            )
        ).scalar_one()
    assert status == "evaluating"
    assert jobs.jobs == []


async def test_engine_gateway_uses_run_configuration_for_poller(tmp_path: Path) -> None:
    """The poller resolves gateways through the run's frozen config and engine."""
    run = await _run_for_gateway(tmp_path)
    seen: list[EvalGatewayConfig] = []

    def factory(config: EvalGatewayConfig) -> EvalGateway:
        seen.append(config)
        return FakeEvalGateway(config)

    from app.service.evolution.engine.contracts import EngineDeps

    engine = EngineFactory.for_run(
        run,
        EngineDeps(
            reads=_UnusedProbeReader(), writes=_UnusedEvolutionWrites(), gateway_factory=factory
        ),
    )
    gateway = engine.gateway()

    assert isinstance(gateway, FakeEvalGateway)
    assert dict(seen[0]) == {"mode": "fake"}


async def _run_for_gateway(tmp_path: Path) -> Any:
    """Load the seeded run through a disposable repository after fixture setup."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "gateway-db",
            jwt_secret=SecretStr("m5-10-gateway-test-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    run = await repository.create_run(
        {
            "id": "gateway-run",
            "title": "gateway",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {"mode": "fake"},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": str(tmp_path / "repo.git"),
            "sub_dir": ".",
            "status": "running",
            "created_at": NOW,
        },
    )
    await database.dispose()
    return run


class _UnusedProbeReader:
    async def list_matching(self, query: Mapping[str, Any]) -> tuple[object, ...]:
        del query
        return ()


class _UnusedEvolutionWrites:
    async def advance_unit(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("gateway construction must not write")

    async def replace_clusters(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("gateway construction must not write")

    async def insert_rounds(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("gateway construction must not write")

    async def write_final(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("gateway construction must not write")
