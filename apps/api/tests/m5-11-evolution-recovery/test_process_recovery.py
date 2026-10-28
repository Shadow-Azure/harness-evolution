"""Process-restart recovery plus blocked/resumed event and SSE linkage."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.jobs import JobRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.service.events import EventBus
from app.service.evolution.blocked_sweeper import EvolutionBlockedSweeper
from app.service.evolution.events import EvolutionRunEventService
from app.service.jobs import JobRunner

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
NEXT_RETRY = NOW + timedelta(minutes=1)


@dataclass
class SubmittedJob:
    """One captured durable retry submission."""

    kind: str
    payload: Mapping[str, Any]
    ref_id: str | None
    created_by: str | None
    reused: bool = False


@dataclass
class JobCapture:
    """Idempotent retry queue double used by the blocked sweeper."""

    items: list[SubmittedJob] = field(default_factory=list)

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> SubmittedJob:
        """Capture one submission or report the same active stage as reused."""
        for item in self.items:
            if item.kind == kind and item.ref_id == ref_id:
                return SubmittedJob(
                    kind=kind,
                    payload=dict(payload),
                    ref_id=ref_id,
                    created_by=created_by,
                    reused=True,
                )
        job = SubmittedJob(
            kind=kind,
            payload=dict(payload),
            ref_id=ref_id,
            created_by=created_by,
        )
        self.items.append(job)
        return job


@dataclass(frozen=True)
class State:
    """Migrated SQLite state shared by recovery scenarios."""

    database: Database
    repository: EvolutionRepository
    events: EvolutionRunEventService
    bus: EventBus


@pytest_asyncio.fixture
async def state(tmp_path: Path) -> AsyncIterator[State]:
    """Provide migrated SQLite state with a real durable event service."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-11-process-recovery-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    bus = EventBus(queue_capacity=16)
    events = EvolutionRunEventService(SqlRunEventStore(database), repository, bus)
    try:
        yield State(database=database, repository=repository, events=events, bus=bus)
    finally:
        await database.dispose()


async def _create_run(
    repository: EvolutionRepository,
    run_id: str,
    *,
    status: str = "running",
    blocked_stage: str | None = None,
    retry_attempts: int = 0,
    next_retry_at_value: datetime | None = None,
) -> None:
    """Insert one run with the exact recovery facts under test."""
    await repository.create_run(
        {
            "id": run_id,
            "title": f"recovery {run_id}",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/skills.git",
            "sub_dir": "skills/deep-research",
            "branch_name": f"evo/20261028-{run_id}",
            "status": status,
            "blocked_stage": blocked_stage,
            "retry_attempts": retry_attempts,
            "next_retry_at": next_retry_at_value,
            "progress_unit": 4,
            "created_by": None,
            "created_at": NOW,
        },
    )


async def test_recover_interrupts_running_job_and_publishes_sse(state: State) -> None:
    """Restart marks the running job and run interrupted and publishes one SSE event."""
    jobs = JobRepository(state.database)
    job = await jobs.insert(
        kind="evolution_advance",
        payload={"runId": "run-recover"},
        ref_id="run-recover",
        created_by=None,
    )
    await jobs.claim(job.id)
    await _create_run(state.repository, "run-recover")
    runner = JobRunner(jobs, state.bus, run_events=state.events)
    subscription = await state.bus.subscribe(("run:run-recover",))

    try:
        await runner.recover()
        notifications = [subscription.queue.get_nowait() for _ in range(2)]
    finally:
        await subscription.close()
        await runner.close()

    recovered = await jobs.get(job.id)
    run = await state.repository.get_run("run-recover")
    page = await state.events.list("run-recover", after_seq=0, limit=100, level=None)
    queued = await jobs.list_queued()

    assert recovered is not None
    assert recovered.status == "interrupted"
    assert recovered.error == "process restarted"
    assert run is not None
    assert run.status == "interrupted"
    assert run.error_stage == "step"
    assert run.error_message == "job interrupted by process restart"
    assert [item.event_type for item in page.items] == ["run_interrupted"]
    assert page.items[0].stage == "step"
    assert page.items[0].job_id == job.id
    assert page.items[0].level == "error"
    assert [item.event for item in notifications] == ["run.event", "run.interrupted"]
    assert notifications[1].data["runId"] == "run-recover"
    assert notifications[1].data["stage"] == "step"
    assert notifications[1].data["message"] == "job interrupted by process restart"
    assert notifications[1].data["eventSeq"] == page.items[0].seq
    assert queued == []


async def test_sweeper_enqueues_only_due_automatic_push_backoff(state: State) -> None:
    """Only a due, under-limit, push-blocked run becomes an automatic retry job."""
    await _create_run(
        state.repository,
        "run-due",
        status="blocked",
        blocked_stage="push",
        next_retry_at_value=NOW - timedelta(seconds=1),
    )
    await _create_run(
        state.repository,
        "run-future",
        status="blocked",
        blocked_stage="push",
        next_retry_at_value=NOW + timedelta(minutes=5),
    )
    await _create_run(
        state.repository,
        "run-capped",
        status="blocked",
        blocked_stage="push",
        retry_attempts=3,
        next_retry_at_value=NOW - timedelta(minutes=1),
    )
    await _create_run(
        state.repository,
        "run-eval",
        status="blocked",
        blocked_stage="eval",
        next_retry_at_value=NOW - timedelta(minutes=1),
    )
    await _create_run(
        state.repository,
        "run-manual",
        status="blocked",
        blocked_stage="push",
        next_retry_at_value=None,
    )
    jobs = JobCapture()
    sweeper = EvolutionBlockedSweeper(state.repository, jobs, now=lambda: NOW)

    assert await sweeper.run_once() == 1
    assert [(item.kind, item.ref_id) for item in jobs.items] == [
        ("evolution_retry", "run-due"),
    ]
    assert jobs.items[0].payload == {"runId": "run-due", "automatic": True}
    assert jobs.items[0].reused is False
    due = await state.repository.get_run("run-due")
    assert due is not None
    assert due.status == "blocked"
    assert due.next_retry_at is not None

    assert await sweeper.run_once() == 0
    assert len(jobs.items) == 1


async def test_blocked_and_resumed_events_replay_after_restart(state: State) -> None:
    """Blocked/resumed events keep payload fields and replay from a fresh service."""
    await _create_run(state.repository, "run-signal")
    subscription = await state.bus.subscribe(("run:run-signal",))
    try:
        blocked_seq = await state.events.record_blocked(
            "run-signal",
            stage="push",
            blocked_stage="push",
            message="candidate push failed",
            job_id="job-blocked",
            next_retry_at=NEXT_RETRY,
            retry_attempts=1,
            error=RuntimeError("remote rejected the push"),
        )
        blocked_notifications = [subscription.queue.get_nowait() for _ in range(2)]
    finally:
        await subscription.close()

    assert blocked_seq == 1
    blocked = await state.repository.get_run("run-signal")
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.blocked_stage == "push"
    assert blocked.retry_attempts == 1
    assert blocked.next_retry_at == NEXT_RETRY
    assert blocked.error_stage == "push"
    assert blocked.push_status == "failed"
    assert [item.event for item in blocked_notifications] == ["run.event", "run.blocked"]
    assert blocked_notifications[1].data == {
        "runId": "run-signal",
        "stage": "push",
        "blockedStage": "push",
        "retryAttempts": 1,
        "nextRetryAt": NEXT_RETRY.isoformat(),
        "message": "candidate push failed",
    }

    restarted = EvolutionRunEventService(
        SqlRunEventStore(state.database),
        state.repository,
        EventBus(queue_capacity=8),
    )
    first_page = await restarted.list("run-signal", after_seq=0, limit=100, level=None)
    assert [item.event_type for item in first_page.items] == ["run_blocked"]
    blocked_event = first_page.items[0]
    assert blocked_event.level == "warn"
    assert blocked_event.stage == "push"
    assert blocked_event.message == "candidate push failed"
    assert blocked_event.job_id == "job-blocked"
    assert blocked_event.payload is None
    assert blocked_event.error is not None
    assert blocked_event.error.type == "RuntimeError"
    assert blocked_event.error.message == "remote rejected the push"

    resumed_bus = EventBus(queue_capacity=8)
    resumed_service = EvolutionRunEventService(
        SqlRunEventStore(state.database),
        state.repository,
        resumed_bus,
    )
    subscription = await resumed_bus.subscribe(("run:run-signal",))
    try:
        resumed_seq = await resumed_service.record_resumed(
            "run-signal",
            stage="push",
            job_id="job-resumed",
        )
        resumed_notifications = [subscription.queue.get_nowait() for _ in range(2)]
    finally:
        await subscription.close()

    resumed = await state.repository.get_run("run-signal")
    assert resumed_seq == 2
    assert resumed is not None
    assert resumed.status == "running"
    assert resumed.blocked_stage is None
    assert resumed.retry_attempts == 1
    assert resumed.error_stage is None
    assert [item.event for item in resumed_notifications] == ["run.event", "run.resumed"]
    assert resumed_notifications[1].data == {
        "runId": "run-signal",
        "stage": "push",
        "retryAttempts": 1,
    }

    replay = await resumed_service.list("run-signal", after_seq=0, limit=100, level=None)
    assert [item.event_type for item in replay.items] == ["run_blocked", "run_resumed"]
    assert [item.seq for item in replay.items] == [1, 2]
    assert replay.items[1].message == "运行已恢复"
