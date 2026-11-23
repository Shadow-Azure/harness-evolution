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
        notifications = [subscription.queue.get_nowait() for _ in range(3)]
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
    assert run.finished_at is not None
    assert [item.event_type for item in page.items] == ["run_interrupted", "job_recovered"]
    assert page.items[0].stage == "step"
    assert page.items[0].job_id == job.id
    assert page.items[0].level == "error"
    assert [item.event for item in notifications] == [
        "run.event",
        "run.interrupted",
        "run.event",
    ]
    assert notifications[1].data["runId"] == "run-recover"
    assert notifications[1].data["stage"] == "step"
    assert notifications[1].data["message"] == "job interrupted by process restart"
    assert notifications[1].data["eventSeq"] == page.items[0].seq
    assert len(queued) == 1
    assert queued[0].kind == "evolution_advance"
    assert queued[0].ref_id == "run-recover"
    assert queued[0].payload == {"runId": "run-recover"}
    assert page.items[1].payload == {
        "previousJobId": job.id,
        "source": "process-restart",
    }


async def test_restart_acknowledges_pause_after_worker_recorded_its_checkpoint(
    state: State,
) -> None:
    """A crash between job completion and its terminal hook cannot strand the request."""
    from app.db.crud.evolution_control import EvolutionControlRepository
    from app.service.evolution.control import EvolutionControlService

    await _create_run(state.repository, "run-pause")
    run = await state.repository.get_run("run-pause")
    assert run is not None
    jobs = JobRepository(state.database)
    job = await jobs.insert(kind="evolution_advance", payload={}, ref_id=run.id, created_by=None)
    await jobs.claim(job.id)
    runner = JobRunner(jobs, state.bus, run_events=state.events)
    control = EvolutionControlService(
        EvolutionControlRepository(state.database), state.events, runner.schedule
    )
    runner.set_evolution_control(control, state.repository)
    requested = await control.pause(run.id, run.workspace_id, "operator")
    assert requested.control_state == "pause_requested"
    await jobs.complete(job.id, {"yielded": True})
    await runner.recover()
    paused = await state.repository.get_run(run.id)
    assert paused and paused.status == "running" and paused.control_state == "paused"
    assert await jobs.list_queued() == []


async def test_committed_pause_has_audited_actor_without_process_notification(state: State) -> None:
    """A crash after the control commit cannot lose either event or its actor."""
    from app.db.crud.evolution_control import EvolutionControlRepository

    await _create_run(state.repository, "run-pause")
    run = await state.repository.get_run("run-pause")
    assert run is not None
    await EvolutionControlRepository(state.database).pause(run.id, run.workspace_id, "operator")
    page = await state.events.list(run.id, after_seq=0, limit=10, level=None)
    assert [event.event_type for event in page.items] == ["run_pause_requested", "run_paused"]
    assert all(event.payload and event.payload["actor"] == "operator" for event in page.items)


async def test_restart_requeues_running_work_only_after_user_resumes(state: State) -> None:
    from app.db.crud.evolution_control import EvolutionControlRepository
    from app.service.evolution.control import EvolutionControlService
    from tests.workspaces.helpers import create_user

    actor = await create_user(state.database, username="held-restart")
    await _create_run(state.repository, "held-restart", status="preparing")
    run = await state.repository.get_run("held-restart")
    assert run
    jobs = JobRepository(state.database)
    job = await jobs.insert(kind="evolution_prepare", ref_id=run.id, payload={}, created_by=None)
    await jobs.claim(job.id)
    runner = JobRunner(jobs, state.bus, run_events=state.events)
    control = EvolutionControlRepository(state.database)
    runner.set_evolution_control(
        EvolutionControlService(control, state.events, runner.schedule), state.repository
    )
    assert (
        await control.pause(run.id, run.workspace_id, actor)
    ).run.control_state == "pause_requested"
    await runner.recover()
    held = await state.repository.get_run(run.id)
    assert held and held.control_state == "paused" and held.status == "preparing"
    assert not await jobs.list_queued()
    resumed = await control.resume(run.id, run.workspace_id, actor)
    assert [row.id for row in await jobs.list_queued()] == [resumed.job_id]
    await runner.close()


async def test_checkpoint_releases_worker_for_another_run_and_resumes_once(state: State) -> None:
    import asyncio

    from app.db.crud.evolution_control import EvolutionControlRepository
    from app.db.models.jobs import JobRunRecord
    from app.service.evolution.control import EvolutionControlService, checkpoint
    from tests.workspaces.helpers import create_user

    actor = await create_user(state.database, username="pause-operator")
    await _create_run(state.repository, "run-first", status="preparing")
    await _create_run(state.repository, "run-second", status="preparing")
    first = await state.repository.get_run("run-first")
    assert first
    store = JobRepository(state.database)
    runner = JobRunner(store, state.bus, run_events=state.events)
    control = EvolutionControlService(
        EvolutionControlRepository(state.database), state.events, runner.schedule
    )
    runner.set_evolution_control(control, state.repository)
    entered, finish_unit = asyncio.Event(), asyncio.Event()
    executed: list[str] = []

    async def prepare(job: JobRunRecord) -> Mapping[str, Any]:
        assert job.ref_id
        if job.ref_id == first.id and not job.payload.get("continuation"):
            entered.set()
            await finish_unit.wait()
            await checkpoint(state.repository, first.id)
        executed.append(job.ref_id)
        return {}

    runner.register_handler("evolution_prepare", prepare)
    try:
        job = await runner.submit(
            kind="evolution_prepare", ref_id=first.id, payload={}, created_by=None
        )
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert (
            await control.pause(first.id, first.workspace_id, actor)
        ).control_state == "pause_requested"
        second = await runner.submit(
            kind="evolution_prepare", ref_id="run-second", payload={}, created_by=None
        )
        finish_unit.set()
        await runner.wait(job.id)
        await runner.wait(second.id)
        assert executed == ["run-second"]
        paused = await state.repository.get_run(first.id)
        assert paused and paused.control_state == "paused"
        await asyncio.gather(
            *(control.resume(first.id, first.workspace_id, actor) for _ in range(2))
        )
        resumed = [
            row for row in await store.list_recent() if row.ref_id == first.id and row.id != job.id
        ]
        assert len(resumed) == 1
        await runner.wait(resumed[0].id)
        assert executed == ["run-second", first.id]
    finally:
        await runner.close()


async def test_duplicate_worker_cannot_claim_a_started_job(state: State) -> None:
    jobs = JobRepository(state.database)
    job = await jobs.insert(kind="evolution_advance", payload={}, ref_id="claim", created_by=None)
    assert await jobs.claim(job.id) is not None
    assert await jobs.claim(job.id) is None


async def test_queued_pause_behind_busy_worker_retires_old_claim(state: State) -> None:
    import asyncio

    from app.db.crud.evolution_control import EvolutionControlRepository
    from app.db.models.jobs import JobRunRecord
    from app.service.evolution.control import EvolutionControlService
    from tests.workspaces.helpers import create_user

    actor = await create_user(state.database, username="queued-operator")
    await _create_run(state.repository, "held", status="preparing")
    await _create_run(state.repository, "queued", status="preparing")
    run = await state.repository.get_run("queued")
    assert run
    store = JobRepository(state.database)
    runner = JobRunner(store, state.bus)
    control = EvolutionControlService(
        EvolutionControlRepository(state.database), state.events, runner.schedule
    )
    runner.set_evolution_control(control, state.repository)
    entered, release = asyncio.Event(), asyncio.Event()
    executions: list[str] = []

    snapshot_read, continue_claim = asyncio.Event(), asyncio.Event()

    class CompetingWorker(JobRepository):
        async def get(self, job_id: str) -> JobRunRecord | None:
            snapshot = await super().get(job_id)
            if snapshot and snapshot.status == "queued":
                snapshot_read.set()
                await continue_claim.wait()
            return snapshot

    async def prepare(job: JobRunRecord) -> Mapping[str, Any]:
        if job.ref_id == "held":
            entered.set()
            await release.wait()
        else:
            executions.append(job.id)
        return {}

    runner.register_handler("evolution_prepare", prepare)
    try:
        await runner.submit(kind="evolution_prepare", ref_id="held", payload={}, created_by=None)
        await asyncio.wait_for(entered.wait(), timeout=5)
        old = await runner.submit(
            kind="evolution_prepare", ref_id=run.id, payload={}, created_by=None
        )
        stale_claim = asyncio.create_task(CompetingWorker(state.database).claim(old.id))
        await asyncio.wait_for(snapshot_read.wait(), timeout=5)
        assert (await control.pause(run.id, run.workspace_id, actor)).can_resume
        await asyncio.gather(*(control.resume(run.id, run.workspace_id, actor) for _ in range(2)))
        continue_claim.set()
        assert await asyncio.wait_for(stale_claim, timeout=5) is None
        pending = await store.list_queued()
        assert len(pending) == 1 and pending[0].id != old.id
        release.set()
        await runner.wait(pending[0].id)
        assert executions == [pending[0].id]
    finally:
        release.set()
        continue_claim.set()
        await runner.close()


async def test_pending_pause_keeps_push_blocked_for_manual_retry(state: State) -> None:
    from app.db.crud.evolution_control import EvolutionControlRepository

    await _create_run(state.repository, "pushing")
    run = await state.repository.get_run("pushing")
    assert run
    store = JobRepository(state.database)
    control = EvolutionControlRepository(state.database)
    job = await store.insert(kind="evolution_retry", ref_id=run.id, payload={}, created_by=None)
    await store.claim(job.id)
    assert (await control.pause(run.id, run.workspace_id, "operator")).run.control_state == (
        "pause_requested"
    )
    await state.repository.mark_blocked(
        run.id, stage="push", message="remote unavailable", next_retry_at=NOW
    )
    await state.events.record_blocked(
        run.id, stage="push", message="remote unavailable", next_retry_at=NOW
    )
    blocked = await state.repository.get_run(run.id)
    assert blocked and blocked.status == "blocked" and blocked.blocked_stage == "push"
    assert blocked.error_message == "remote unavailable" and blocked.next_retry_at is None
    # A restart between the durable push failure and its job terminal write
    # cannot quietly replay a retry that the operator already put on hold.
    await store.interrupt(job.id, "process restarted")
    interrupted = await store.get(job.id)
    assert interrupted and await control.requeue_interrupted(interrupted) is None
    assert (
        await EvolutionBlockedSweeper(state.repository, JobCapture(), now=lambda: NOW).run_once()
        == 0
    )
    _, reused = await control.admit(run.id, "evolution_retry", {"automatic": False}, None)
    assert not reused


async def test_pause_during_blocked_recording_waits_for_the_actual_failure(state: State) -> None:
    import asyncio

    from app.db.crud.evolution_control import EvolutionControlRepository
    from app.db.models.jobs import JobRunRecord
    from app.service.evolution.control import EvolutionControlService
    from app.service.evolution.engine.contracts import RunBlocked

    await _create_run(state.repository, "classifying")
    run = await state.repository.get_run("classifying")
    assert run
    entered, release = asyncio.Event(), asyncio.Event()

    class RecordingEvents(EvolutionRunEventService):
        async def record_blocked(self, run_id: str, **kwargs: Any) -> int:
            entered.set()
            await release.wait()
            return await super().record_blocked(run_id, **kwargs)

    events = RecordingEvents(SqlRunEventStore(state.database), state.repository, state.bus)
    runner = JobRunner(JobRepository(state.database), state.bus, run_events=events)
    control = EvolutionControlService(
        EvolutionControlRepository(state.database), events, runner.schedule
    )
    runner.set_evolution_control(control, state.repository)

    async def push(_job: JobRunRecord) -> Mapping[str, Any]:
        raise RunBlocked("unavailable", stage="push", retryable=True, next_retry_at=NOW)

    runner.register_handler("evolution_advance", push)
    try:
        job = await runner.submit(
            kind="evolution_advance", ref_id=run.id, created_by=None, payload={}
        )
        await asyncio.wait_for(entered.wait(), timeout=5)
        pause = await control.pause(run.id, run.workspace_id, "operator")
        assert pause.control_state == "pause_requested"
        release.set()
        await runner.wait(job.id)
        blocked = await state.repository.get_run(run.id)
        assert blocked and blocked.status == "blocked" and blocked.next_retry_at is None
    finally:
        release.set()
        await runner.close()


async def test_stale_sweeper_snapshot_cannot_admit_a_manual_only_retry(state: State) -> None:
    from app.db.crud.evolution_control import EvolutionControlRepository
    from app.service.evolution.control import EvolutionControlService

    await _create_run(
        state.repository, "stale", status="blocked", blocked_stage="push", next_retry_at_value=NOW
    )
    due = await state.repository.list_blocked_due(NOW, max_attempts=3, limit=10)
    assert [run.id for run in due] == ["stale"]
    await state.repository.mark_resumed("stale")
    await state.repository.mark_blocked("stale", stage="push", message="manual action required")
    store = JobRepository(state.database)
    runner = JobRunner(store, state.bus)
    runner.set_evolution_control(
        EvolutionControlService(
            EvolutionControlRepository(state.database), state.events, runner.schedule
        ),
        state.repository,
    )
    try:
        sweeper = EvolutionBlockedSweeper(state.repository, runner, now=lambda: NOW)
        assert not await sweeper._schedule_retry(due[0].id, None)
        assert not await store.list_recent()
    finally:
        await runner.close()


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
