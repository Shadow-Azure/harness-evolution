"""Blocked-run retry dispatch against real SQLite state and doubles."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeHitRow
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import (
    evolution_finals,
    evolution_rounds,
    probe_clusters,
)
from app.db.models.jobs import JobRunRecord
from app.service.events import EventBus
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    FakeEvalGateway,
    RunBlocked,
)
from app.service.evolution.eval_poller import EvolutionEvalSubmitter
from app.service.evolution.events import EvolutionRunEventService
from app.service.evolution.git_candidate import (
    CandidateTrace,
    EvolutionCandidateService,
)
from app.service.evolution.retry import EvolutionRetryService
from app.third_party_api.git.workspace import (
    CandidateWorkspace,
    GitOperationError,
    Patch,
    PreparedWorkspace,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
RUN_ID = "run-retry"
ROUND_ID = "round-retry"
CANDIDATE_REF = "evo/20261028-run-retry/candidate/r1"
CANDIDATE_COMMIT = "b" * 40


@dataclass
class SubmittedJob:
    """One captured follow-up submission with the JobRunner view protocol."""

    kind: str
    payload: Mapping[str, Any]
    ref_id: str | None
    created_by: str | None
    id: str = "job-followup"
    reused: bool = False


@dataclass
class JobCapture:
    """Capture follow-up submissions without starting a worker."""

    items: list[SubmittedJob] = field(default_factory=list)

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> SubmittedJob:
        """Capture one scheduling call."""
        job = SubmittedJob(
            kind=kind,
            payload=dict(payload),
            ref_id=ref_id,
            created_by=created_by,
            id=f"job-{len(self.items) + 1}",
        )
        self.items.append(job)
        return job


@dataclass
class RecordingStage:
    """Record the job id a delegated stage received."""

    name: str
    calls: list[str] = field(default_factory=list)

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Record and return one deterministic stage result."""
        self.calls.append(job.ref_id or "")
        return {"stage": self.name}


class EmptyProbeReader:
    """Return no probe evidence for isolated candidate regeneration."""

    async def list_rows_by_ids(self, probe_ids: Sequence[str]) -> tuple[ProbeHitRow, ...]:
        """Return no rows for the given probes."""
        del probe_ids
        return ()


@dataclass
class WorkspaceDouble:
    """Commit and push candidates without touching git."""

    push_enabled: bool = True
    created: list[str] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)

    async def create_candidate(
        self,
        prepared: PreparedWorkspace,
        *,
        run_branch: str,
        candidate_ref: str,
        patch: Patch,
        message: str,
        expected_run_id: str | None = None,
    ) -> CandidateWorkspace:
        """Record and return one deterministic candidate."""
        del prepared, patch
        self.created.append(candidate_ref)
        return CandidateWorkspace(
            workspace_path=Path("workspace"),
            run_branch=run_branch,
            local_branch=f"{candidate_ref}-local",
            ref=candidate_ref,
            commit=CANDIDATE_COMMIT,
            message=message,
            run_id=expected_run_id or RUN_ID,
            base_commit="a" * 40,
        )

    async def push_candidate(
        self,
        candidate: CandidateWorkspace,
        *,
        expected_remote_commit: str | None,
    ) -> None:
        """Record one successful candidate publication."""
        del expected_remote_commit
        self.pushed.append(candidate.ref)


class FailingPushWorkspace(WorkspaceDouble):
    """Raise one classified git failure on candidate push."""

    def __init__(self, *, retryable: bool) -> None:
        super().__init__()
        self.retryable = retryable

    async def push_candidate(
        self,
        candidate: CandidateWorkspace,
        *,
        expected_remote_commit: str | None,
    ) -> None:
        """Fail the push with the requested transient classification."""
        del candidate, expected_remote_commit
        raise GitOperationError(
            "remote transport failed",
            stage="push",
            retryable=self.retryable,
        )


@dataclass
class State:
    """Assembled recovery state for one dispatch scenario."""

    database: Database
    repository: EvolutionRepository
    workspace: WorkspaceDouble
    events: EvolutionRunEventService
    jobs: JobCapture


@pytest_asyncio.fixture
async def state(tmp_path: Path) -> AsyncIterator[State]:
    """Provide migrated SQLite state and a real durable event service."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-11-dispatch-signing-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    events = EvolutionRunEventService(
        SqlRunEventStore(database),
        repository,
        EventBus(queue_capacity=8),
    )
    try:
        yield State(
            database=database,
            repository=repository,
            workspace=WorkspaceDouble(),
            events=events,
            jobs=JobCapture(),
        )
    finally:
        await database.dispose()


async def _create_run(
    repository: EvolutionRepository,
    *,
    status: str = "blocked",
    blocked_stage: str | None = "push",
    retry_attempts: int = 0,
    next_retry_at_value: datetime | None = None,
    push_status: str = "failed",
    progress_unit: int = 4,
) -> None:
    """Create one run with a complete persisted workspace snapshot."""
    await repository.create_run(
        {
            "id": RUN_ID,
            "title": "retry dispatch",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/skills.git",
            "sub_dir": "skills/deep-research",
            "repo_path": str(Path("repo")),
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261028-run-retry",
            "workspace_path": str(Path("workspace")),
            "status": status,
            "blocked_stage": blocked_stage,
            "retry_attempts": retry_attempts,
            "next_retry_at": next_retry_at_value,
            "push_status": push_status,
            "progress_unit": progress_unit,
            "created_by": None,
            "created_at": NOW,
        },
    )


async def _seed_cluster_and_round(
    state: State,
    *,
    round_status: str = "pushing",
    push_status: str = "failed",
    eval_status: str = "pending",
    eval_external_id: str | None = None,
    eval_result: Mapping[str, Any] | None = None,
    candidate: bool = True,
) -> None:
    """Insert one cluster and its round with the exact stage facts under test."""
    async with state.database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-retry",
                run_id=RUN_ID,
                seq=1,
                probe_cluster_description="placeholder issue",
                probe_cluster_type="error",
                confidence=0.8,
                impact=0.8,
                severity=0.8,
                rank=1,
                created_at=NOW,
            ),
        )
        values: dict[str, Any] = {
            "id": ROUND_ID,
            "run_id": RUN_ID,
            "probe_cluster_id": "cluster-retry",
            "seq": 1,
            "status": round_status,
            "push_status": push_status,
            "push_attempts": 3,
            "eval_status": eval_status,
            "eval_external_id": eval_external_id,
            "eval_error": "evaluation failed" if eval_status == "failed" else None,
            "eval_finished_at": NOW if eval_status == "failed" else None,
            "eval_result": dict(eval_result) if eval_result is not None else None,
        }
        if candidate:
            values.update(
                {
                    "candidate_ref": CANDIDATE_REF,
                    "candidate_commit": CANDIDATE_COMMIT,
                    "candidate_message": "candidate message",
                },
            )
        await session.execute(insert(evolution_rounds).values(**values))


async def _no_sleep(seconds: float) -> None:
    """Remove the five-second production delay from immediate push retries."""
    del seconds


def _retry_job(*, automatic: bool, job_id: str = "job-retry") -> JobRunRecord:
    """Build one durable retry job row."""
    return JobRunRecord(
        id=job_id,
        kind="evolution_retry",
        ref_id=RUN_ID,
        status="running",
        progress=0,
        executor="local",
        external_job_id=None,
        attempt=1,
        payload={"runId": RUN_ID, "automatic": automatic},
        result=None,
        error=None,
        created_by="user-1",
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


def _submitter(state: State) -> EvolutionEvalSubmitter:
    """Build the real submitter over the deterministic placeholder gateway."""
    gateway = FakeEvalGateway(config=EvalGatewayConfig.from_mapping({}))
    return EvolutionEvalSubmitter(
        state.repository,
        lambda _run: gateway,
        events=state.events,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
    )


def _service(
    state: State,
    *,
    candidates: Any = None,
    apply: Any = None,
    finalize: Any = None,
    submitter: EvolutionEvalSubmitter | None = None,
    probes: Any = None,
) -> EvolutionRetryService:
    """Assemble one retry service over the shared state."""
    return EvolutionRetryService(
        state.repository,
        candidates or EvolutionCandidateService(state.repository, state.workspace),  # type: ignore[arg-type]
        state.jobs,
        apply=apply,
        finalize=finalize,
        eval_submitter=submitter or _submitter(state),
        probes=probes,
        events=state.events,
        now=lambda: NOW,
    )


async def _persist_blocked(state: State, exc: RunBlocked) -> None:
    """Simulate the JobRunner boundary that persists a raised block."""
    await state.repository.mark_blocked(
        RUN_ID,
        stage=exc.stage,
        message=str(exc),
        next_retry_at=exc.next_retry_at,
        retry_attempts=exc.retry_attempts,
    )


async def test_final_blocked_push_continues_finalize(state: State) -> None:
    """A persisted final resumes finalization instead of re-running iterations."""
    await _create_run(state.repository)
    async with state.database.transaction() as session:
        await session.execute(
            insert(evolution_finals).values(
                run_id=RUN_ID,
                best_version="v2.0.0",
                verdict=True,
                best_score=88.0,
                init_score=80.0,
                metrics=[],
            ),
        )
    finalize = RecordingStage("finalize")
    service = _service(state, finalize=finalize)

    result = await service.handle(_retry_job(automatic=False))

    assert result["resumed"] is True
    assert finalize.calls == [RUN_ID]


async def test_push_blocked_with_eval_result_continues_apply(state: State) -> None:
    """A completed evaluation resumes through apply, not a second evaluation."""
    await _create_run(state.repository)
    await _seed_cluster_and_round(
        state,
        round_status="evaluating",
        push_status="succeeded",
        eval_status="completed",
        eval_result={
            "currentScore": 80.0,
            "candidateScore": 90.0,
            "externalVerdict": "accept",
            "metrics": [],
        },
    )
    apply = RecordingStage("apply")
    service = _service(state, apply=apply)

    result = await service.handle(_retry_job(automatic=False))

    assert result["resumed"] is True
    assert apply.calls == [RUN_ID]


async def test_pushing_round_resume_pushes_once_and_submits_eval(state: State) -> None:
    """A push-blocked candidate is repushed once and re-enters evaluation."""
    await _create_run(state.repository)
    await _seed_cluster_and_round(state)

    result = await _service(state).handle(_retry_job(automatic=False))

    assert result["resumed"] is True
    assert state.workspace.created == []
    assert state.workspace.pushed == [CANDIDATE_REF]
    round_ = await state.repository.get_round(ROUND_ID)
    assert round_ is not None
    assert round_.status == "evaluating"
    assert round_.eval_external_id == f"fake:{RUN_ID}:{ROUND_ID}:{CANDIDATE_COMMIT}"
    events = await state.events.list(RUN_ID, after_seq=0, limit=100, level=None)
    assert [item.event_type for item in events.items].count("run_resumed") == 1


async def test_eval_blocked_resubmits_with_new_external_id(state: State) -> None:
    """Evaluation retry clears the failed id and keeps it in the event payload."""
    await _create_run(
        state.repository,
        blocked_stage="eval",
        push_status="succeeded",
    )
    await _seed_cluster_and_round(
        state,
        round_status="evaluating",
        push_status="succeeded",
        eval_status="failed",
        eval_external_id="legacy-eval-id",
    )

    result = await _service(state).handle(_retry_job(automatic=False))

    assert result["previousEvalExternalId"] == "legacy-eval-id"
    round_ = await state.repository.get_round(ROUND_ID)
    assert round_ is not None
    assert round_.eval_status == "evaluating"
    assert round_.eval_external_id == f"fake:{RUN_ID}:{ROUND_ID}:{CANDIDATE_COMMIT}"
    events = await state.events.list(RUN_ID, after_seq=0, limit=100, level=None)
    submitted = next(item for item in events.items if item.event_type == "eval_submitted")
    assert submitted.payload is not None
    assert submitted.payload["previousExternalId"] == "legacy-eval-id"


async def test_patching_round_regenerates_the_candidate(state: State) -> None:
    """A patch-blocked round is regenerated through publication, not skipped."""
    await _create_run(
        state.repository,
        blocked_stage="patch",
        push_status="pending",
    )
    await _seed_cluster_and_round(
        state,
        round_status="patching",
        push_status="pending",
        candidate=False,
    )

    result = await _service(state, probes=EmptyProbeReader()).handle(
        _retry_job(automatic=False),
    )

    assert result["resumed"] is True
    assert state.workspace.created == [CANDIDATE_REF]
    assert state.workspace.pushed == [CANDIDATE_REF]
    round_ = await state.repository.get_round(ROUND_ID)
    assert round_ is not None
    assert round_.status == "evaluating"


async def test_automatic_ladder_advances_five_fifteen_then_stops(state: State) -> None:
    """Automatic attempts count up and schedule 5/15/None after each failure."""
    await _create_run(state.repository)
    await _seed_cluster_and_round(state)

    class FailingCandidate:
        async def repush_existing(self, *args: object, **kwargs: object) -> Any:
            del args, kwargs
            raise RunBlocked("transient push failure", stage="push", retryable=True)

    service = _service(state, candidates=FailingCandidate())
    expected = [(1, NOW + timedelta(minutes=5)), (2, NOW + timedelta(minutes=15)), (3, None)]
    for attempt, (expected_attempts, deadline) in enumerate(expected, start=1):
        with pytest.raises(RunBlocked) as raised:
            await service.handle(_retry_job(automatic=True, job_id=f"job-auto-{attempt}"))
        exc = raised.value
        assert exc.retry_attempts == expected_attempts
        assert exc.next_retry_at == deadline
        await _persist_blocked(state, exc)
        run = await state.repository.get_run(RUN_ID)
        assert run is not None
        assert run.status == "blocked"
        assert run.retry_attempts == expected_attempts
        assert run.next_retry_at == deadline


async def test_permanent_push_error_never_schedules_automatic_retry(state: State) -> None:
    """A permanent push failure keeps the run blocked without a deadline."""
    await _create_run(state.repository)
    await _seed_cluster_and_round(state)

    class PermanentCandidate:
        async def repush_existing(self, *args: object, **kwargs: object) -> Any:
            del args, kwargs
            raise RunBlocked("branch protection", stage="push", retryable=False)

    service = _service(state, candidates=PermanentCandidate())
    with pytest.raises(RunBlocked) as raised:
        await service.handle(_retry_job(automatic=True))

    assert raised.value.next_retry_at is None
    assert raised.value.retry_attempts == 1


async def test_initial_transient_push_failure_carries_one_minute_backoff(
    state: State,
) -> None:
    """The first blocked push persists attempts=0 and now+1minute."""
    await _create_run(
        state.repository,
        status="running",
        blocked_stage=None,
        push_status="pending",
        progress_unit=4,
    )
    candidates = EvolutionCandidateService(
        state.repository,
        FailingPushWorkspace(retryable=True),  # type: ignore[arg-type]
        now=lambda: NOW,
        sleep=_no_sleep,
        push_interval_seconds=0,
    )
    async with state.database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-retry",
                run_id=RUN_ID,
                seq=1,
                probe_cluster_description="placeholder issue",
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
                id=ROUND_ID,
                run_id=RUN_ID,
                probe_cluster_id="cluster-retry",
                seq=1,
                status="pending",
                push_status="pending",
                eval_status="pending",
            ),
        )

    with pytest.raises(RunBlocked) as raised:
        await candidates.publish(
            await state.repository.get_run(RUN_ID),  # type: ignore[arg-type]
            await state.repository.get_round(ROUND_ID),  # type: ignore[arg-type]
            CandidateTrace("cluster-retry", "placeholder issue", (), (), "analysis"),
            job_id="job-publish",
        )

    assert raised.value.stage == "push"
    assert raised.value.retry_attempts == 0
    assert raised.value.next_retry_at == NOW + timedelta(minutes=1)
    run = await state.repository.get_run(RUN_ID)
    assert run is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "push"
    assert run.retry_attempts == 0
    assert run.next_retry_at == NOW + timedelta(minutes=1)


async def test_permanent_publish_failure_has_no_backoff(state: State) -> None:
    """Authentication or branch-protection failures stay manual-only."""
    await _create_run(
        state.repository,
        status="running",
        blocked_stage=None,
        push_status="pending",
    )
    async with state.database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-retry",
                run_id=RUN_ID,
                seq=1,
                probe_cluster_description="placeholder issue",
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
                id=ROUND_ID,
                run_id=RUN_ID,
                probe_cluster_id="cluster-retry",
                seq=1,
                status="pending",
                push_status="pending",
                eval_status="pending",
            ),
        )
    candidates = EvolutionCandidateService(
        state.repository,
        FailingPushWorkspace(retryable=False),  # type: ignore[arg-type]
        now=lambda: NOW,
    )

    with pytest.raises(RunBlocked) as raised:
        await candidates.publish(
            await state.repository.get_run(RUN_ID),  # type: ignore[arg-type]
            await state.repository.get_round(ROUND_ID),  # type: ignore[arg-type]
            CandidateTrace("cluster-retry", "placeholder issue", (), (), "analysis"),
        )

    assert raised.value.next_retry_at is None
    assert raised.value.retryable is False
    run = await state.repository.get_run(RUN_ID)
    assert run is not None
    assert run.next_retry_at is None


async def test_manual_request_resets_backoff_and_queues_once(state: State) -> None:
    """Manual retry resets attempts and reuses one already-active retry job."""
    await _create_run(
        state.repository,
        retry_attempts=2,
        next_retry_at_value=NOW - timedelta(minutes=1),
    )
    service = _service(state)

    accepted = await service.request_retry(RUN_ID, created_by="user-1")

    assert accepted.reused is False
    run = await state.repository.get_run(RUN_ID)
    assert run is not None
    assert run.retry_attempts == 0
    assert run.next_retry_at is None
    assert state.jobs.items[0].payload == {"runId": RUN_ID, "automatic": False}
