"""Startup recovery for rows written interrupted by a graceful shutdown."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_control import EvolutionControlRepository
from app.db.crud.jobs import JobRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_runs
from app.db.models.jobs import job_runs
from app.service.events import EventBus
from app.service.evolution.control import EvolutionControlService
from app.service.evolution.events import EvolutionRunEventService
from app.service.jobs import JobRunner

NOW = datetime(2026, 11, 24, 14, 39, tzinfo=ZoneInfo("Asia/Shanghai"))


@dataclass(frozen=True)
class State:
    """Migrated SQLite state shared by shutdown-recovery scenarios."""

    database: Database
    runs: EvolutionRepository
    jobs: JobRepository
    control: EvolutionControlRepository
    events: EvolutionRunEventService
    bus: EventBus


@pytest_asyncio.fixture
async def state(tmp_path: Path) -> AsyncIterator[State]:
    """Provide one migrated database with durable event and control services."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("bugfix-49-shutdown-recovery-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    runs = EvolutionRepository(database)
    bus = EventBus(queue_capacity=16)
    events = EvolutionRunEventService(SqlRunEventStore(database), runs, bus)
    try:
        yield State(
            database=database,
            runs=runs,
            jobs=JobRepository(database),
            control=EvolutionControlRepository(database),
            events=events,
            bus=bus,
        )
    finally:
        await bus.close()
        await database.dispose()


async def _create_run(
    state: State,
    run_id: str,
    *,
    status: str = "preparing",
) -> None:
    """Insert one active run at the attribution checkpoint under test."""
    await state.runs.create_run(
        {
            "id": run_id,
            "title": f"shutdown {run_id}",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/skills.git",
            "sub_dir": "skills/deep-research",
            "branch_name": f"evo/20261124-{run_id}",
            "status": status,
            "progress_unit": 3,
            "created_by": None,
            "created_at": NOW,
        },
    )


async def _interrupt(
    state: State,
    *,
    run_id: str,
    kind: str,
    attempt: int | None = None,
) -> str:
    """Persist one job and terminal row exactly as graceful shutdown does."""
    job = await state.jobs.insert(
        kind=kind,
        payload={"runId": run_id, "source": "prepare"},
        ref_id=run_id,
        created_by=None,
    )
    assert await state.jobs.claim(job.id, owner="old-process") is not None
    if attempt is not None:
        async with state.database.transaction() as session:
            await session.execute(
                update(job_runs).where(job_runs.c.id == job.id).values(attempt=attempt),
            )
    assert await state.jobs.interrupt(
        job.id,
        "job cancelled during shutdown",
        owner="old-process",
    )
    return job.id


def _runner(state: State) -> JobRunner:
    """Build one runner with the same control fence as the application."""
    runner = JobRunner(state.jobs, state.bus, run_events=state.events)
    runner.set_evolution_control(
        EvolutionControlService(state.control, state.events, runner.schedule),
        state.runs,
    )
    return runner


async def test_shutdown_interrupted_evolution_job_is_requeued_once(state: State) -> None:
    """A row already written interrupted is requeued with one recovery event."""
    await _create_run(state, "run-shutdown")
    job_id = await _interrupt(state, run_id="run-shutdown", kind="evolution_prepare")
    await state.events.record_interrupted(
        run_id="run-shutdown",
        stage="prepare",
        message="job interrupted during shutdown",
        job_id=job_id,
    )
    runner = _runner(state)
    try:
        await runner.recover()
        queued = await state.jobs.list_queued()
        assert [row.kind for row in queued] == ["evolution_prepare"]
        assert queued[0].ref_id == "run-shutdown"
        assert queued[0].payload == {"runId": "run-shutdown", "source": "prepare"}
        interrupted = await state.jobs.get(job_id)
        assert interrupted is not None and interrupted.status == "interrupted"

        page = await state.events.list("run-shutdown", after_seq=0, limit=100, level=None)
        assert [item.event_type for item in page.items] == ["run_interrupted", "job_recovered"]
        assert page.items[1].payload == {
            "previousJobId": job_id,
            "source": "process-restart",
        }

        await runner.recover()
        assert [row.id for row in await state.jobs.list_queued()] == [queued[0].id]
    finally:
        await runner.close()


async def test_completed_replacement_is_not_requeued_again(state: State) -> None:
    """A newer completed replacement keeps the older interrupted row stale."""
    await _create_run(state, "run-completed")
    await _interrupt(state, run_id="run-completed", kind="evolution_prepare")
    runner = _runner(state)
    try:
        await runner.recover()
        replacement = (await state.jobs.list_queued())[0]
        assert await state.jobs.claim(replacement.id, owner="worker") is not None
        assert await state.jobs.complete(replacement.id, {"runId": "run-completed"}, owner="worker")

        await runner.recover()
        assert await state.jobs.list_queued() == []
    finally:
        await runner.close()


async def test_paused_blocked_and_completed_runs_stay_held(state: State) -> None:
    """Only an active, running run admits an interrupted replacement."""
    for run_id in ("run-paused", "run-blocked", "run-done"):
        await _create_run(
            state,
            run_id,
            status="completed" if run_id == "run-done" else "preparing",
        )
        await _interrupt(state, run_id=run_id, kind="evolution_prepare")
    await state.control.pause("run-paused", "ws-default", "operator")
    await state.runs.mark_blocked(
        "run-blocked",
        stage="push",
        message="remote unavailable",
    )
    runner = _runner(state)
    try:
        await runner.recover()
        assert await state.jobs.list_queued() == []
    finally:
        await runner.close()


async def test_interrupted_attribution_batch_keeps_progress_and_identity(state: State) -> None:
    """A 9/22 batch returns to queued with its progress, attempt, and result intact."""
    await _create_run(state, "run-batch")
    await state.runs.mark_interrupted(
        "run-batch",
        stage="prepare",
        message="job interrupted during shutdown",
    )
    job_id = await _interrupt(state, run_id="run-batch", kind="attribution_batch")
    await state.jobs.update_progress(
        job_id,
        9 / 22,
        result={"processed": 9, "total": 22},
    )
    runner = _runner(state)
    try:
        await runner.recover()
        submission = await runner.submit(
            kind="attribution_batch",
            payload={"runId": "run-batch", "source": "prepare"},
            ref_id="run-batch",
            created_by=None,
        )
        assert submission.id == job_id and submission.reused

        recovered = await state.jobs.get(job_id)
        assert recovered is not None
        assert recovered.status == "queued"
        assert recovered.attempt == 1
        assert recovered.error is None
        assert recovered.started_at is None
        assert recovered.result == {"processed": 9, "total": 22}
        assert recovered.progress == 9 / 22
        assert [row.id for row in await state.jobs.list_queued()] == [job_id]

        await runner.recover()
        assert [row.id for row in await state.jobs.list_queued()] == [job_id]
    finally:
        await runner.close()


async def test_attribution_batch_at_attempt_limit_stays_interrupted(state: State) -> None:
    """An attempt-limited lease interruption is terminal, not restart recovery."""
    await _create_run(state, "run-exhausted")
    job_id = await _interrupt(state, run_id="run-exhausted", kind="attribution_batch")
    async with state.database.transaction() as session:
        await session.execute(
            update(job_runs).where(job_runs.c.id == job_id).values(attempt=1, max_attempts=1),
        )
    runner = _runner(state)
    try:
        await runner.recover()
        exhausted = await state.jobs.get(job_id)
        assert exhausted is not None and exhausted.status == "interrupted"
        assert await state.jobs.list_queued() == []
    finally:
        await runner.close()


async def test_attribution_batch_of_completed_run_is_not_recovered(state: State) -> None:
    """A batch whose run already finished must not restart attribution work."""
    await _create_run(state, "run-finished", status="completed")
    job_id = await _interrupt(state, run_id="run-finished", kind="attribution_batch")
    runner = _runner(state)
    try:
        await runner.recover()
        finished = await state.jobs.get(job_id)
        assert finished is not None and finished.status == "interrupted"
        assert await state.jobs.list_queued() == []
    finally:
        await runner.close()


async def test_interrupted_batch_is_held_without_run_repository(state: State) -> None:
    """Without the run repository the batch fence fails closed instead of guessing."""
    await _create_run(state, "run-unwired")
    job_id = await _interrupt(state, run_id="run-unwired", kind="attribution_batch")
    runner = JobRunner(state.jobs, state.bus, run_events=state.events)
    try:
        await runner.recover()
        held = await state.jobs.get(job_id)
        assert held is not None and held.status == "interrupted"
        assert await state.jobs.list_queued() == []
    finally:
        await runner.close()


async def test_latest_interrupted_without_kinds_returns_nothing(state: State) -> None:
    """An empty selection is a cheap no-op for callers that disable recovery."""
    assert await state.jobs.latest_interrupted(()) == []


async def test_attribution_batch_past_the_attribution_stage_is_not_recovered(state: State) -> None:
    """A batch left behind after the run advanced is stale recovery work."""
    await _create_run(state, "run-advanced")
    async with state.database.transaction() as session:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == "run-advanced")
            .values(progress_unit=4),
        )
    job_id = await _interrupt(state, run_id="run-advanced", kind="attribution_batch")
    runner = _runner(state)
    try:
        await runner.recover()
        stale = await state.jobs.get(job_id)
        assert stale is not None and stale.status == "interrupted"
        assert await state.jobs.list_queued() == []
    finally:
        await runner.close()


async def test_only_the_newest_interrupted_stage_per_run_is_recovered(state: State) -> None:
    """Two interrupted stages of one run cannot race for the single active slot."""
    await _create_run(state, "run-two-stages")
    await state.runs.mark_interrupted(
        "run-two-stages",
        stage="prepare",
        message="job interrupted during shutdown",
    )
    await _interrupt(state, run_id="run-two-stages", kind="evolution_prepare")
    await _interrupt(state, run_id="run-two-stages", kind="evolution_advance")
    runner = _runner(state)
    try:
        await runner.recover()
        queued = await state.jobs.list_queued()
        assert [row.kind for row in queued] == ["evolution_advance"]
        assert queued[0].ref_id == "run-two-stages"
    finally:
        await runner.close()
