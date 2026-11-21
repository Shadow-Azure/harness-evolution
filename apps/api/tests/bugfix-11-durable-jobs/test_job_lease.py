"""Durable job lease, heartbeat, startup requeue, and bounded drain."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.jobs import JobRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.jobs import JobRunRecord, job_runs
from app.service.events import EventBus
from app.service.jobs import JobRunner
from app.utils.time import now_shanghai


class RecordingEvents:
    """Capture interruption and recovery events without a database."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.interrupted: list[tuple[str, str, str, str]] = []
        self.recovered: list[tuple[str, str, str, str, str]] = []

    async def record_interrupted(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        job_id: str,
    ) -> int:
        """Record one interruption and return a stable sequence."""
        self.interrupted.append((run_id, stage, message, job_id))
        return len(self.interrupted)

    async def record_recovered(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        job_id: str,
        previous_job_id: str,
    ) -> int:
        """Record one recovery and return a stable sequence."""
        self.recovered.append((run_id, stage, message, job_id, previous_job_id))
        return len(self.recovered)


@pytest_asyncio.fixture
async def environment(
    tmp_path: Path,
) -> AsyncGenerator[tuple[Database, JobRepository, EventBus], None]:
    """Provide one migrated SQLite database and an unclosed event bus."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("bugfix-11-durable-jobs-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    bus = EventBus(queue_capacity=100)
    try:
        yield database, JobRepository(database), bus
    finally:
        await bus.close()
        await database.dispose()


async def test_claim_sets_lease_and_renew_extends_it(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """Claiming writes owner, expiry, and heartbeat; renewal is owner-bound."""
    _, repository, _ = environment
    job = await repository.insert(
        kind="sync",
        payload={},
        ref_id="lease-1",
        created_by=None,
    )

    claimed = await repository.claim(job.id, owner="worker-a", lease_seconds=60)

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.lease_owner == "worker-a"
    assert claimed.lease_expires_at is not None
    assert claimed.heartbeat_at is not None
    first_expiry = claimed.lease_expires_at

    assert await repository.renew(job.id, owner="worker-a", lease_seconds=120)
    renewed = await repository.get(job.id)
    assert renewed is not None
    assert renewed.lease_expires_at is not None
    assert renewed.lease_expires_at >= first_expiry
    assert not await repository.renew(job.id, owner="worker-b", lease_seconds=120)


async def test_expired_running_lease_is_reclaimable(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """Only an expired lease lets another worker take the running row."""
    database, repository, _ = environment
    job = await repository.insert(
        kind="sync",
        payload={},
        ref_id="lease-2",
        created_by=None,
    )
    await repository.claim(job.id, owner="worker-a", lease_seconds=60)

    assert await repository.claim(job.id, owner="worker-b", lease_seconds=60) is None

    async with database.transaction() as session:
        await session.execute(
            update(job_runs)
            .where(job_runs.c.id == job.id)
            .values(lease_expires_at=now_shanghai() - timedelta(seconds=1)),
        )
    reclaimed = await repository.claim(job.id, owner="worker-b", lease_seconds=60)
    assert reclaimed is not None
    assert reclaimed.attempt == 2
    assert reclaimed.lease_owner == "worker-b"


async def test_release_clears_lease_without_changing_status(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """A drain release leaves the row recoverable for the next startup."""
    _, repository, _ = environment
    job = await repository.insert(
        kind="sync",
        payload={},
        ref_id="lease-3",
        created_by=None,
    )
    await repository.claim(job.id, owner="worker-a", lease_seconds=60)

    await repository.release(job.id, owner="worker-a")

    released = await repository.get(job.id)
    assert released is not None
    assert released.status == "running"
    assert released.lease_owner is None
    assert released.lease_expires_at is None
    assert released.heartbeat_at is None


async def test_runner_heartbeat_renews_and_completion_clears_lease(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """The handler heartbeat keeps the lease fresh until the terminal write."""
    _, repository, bus = environment
    started = asyncio.Event()
    release = asyncio.Event()

    async def hold(_job: JobRunRecord) -> dict[str, Any]:
        started.set()
        await release.wait()
        return {"ok": True}

    runner = JobRunner(
        repository,
        bus,
        lease_seconds=30,
        heartbeat_seconds=0.05,
        owner="heartbeat-worker",
    )
    runner.register_handler("sync", hold)
    await runner.start()
    submitted = await runner.submit(
        kind="sync",
        payload={},
        ref_id="heartbeat",
        created_by=None,
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    running = await repository.get(submitted.id)
    assert running is not None
    assert running.lease_owner == "heartbeat-worker"
    first_heartbeat = running.heartbeat_at
    assert first_heartbeat is not None

    await asyncio.sleep(0.12)
    renewed = await repository.get(submitted.id)
    assert renewed is not None
    assert renewed.heartbeat_at is not None
    assert renewed.heartbeat_at >= first_heartbeat

    release.set()
    completed = await asyncio.wait_for(runner.wait(submitted.id), timeout=1)
    assert completed.status == "completed"
    assert completed.lease_owner is None
    assert completed.lease_expires_at is None


async def test_recovery_requeues_resumable_evolution_job_once(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """A residual evolution job becomes the same stage job with a recovery event."""
    _, repository, bus = environment
    events = RecordingEvents()
    job = await repository.insert(
        kind="evolution_advance",
        payload={"runId": "run-recovered"},
        ref_id="run-recovered",
        created_by=None,
    )
    await repository.claim(job.id, owner="dead-process", lease_seconds=60)
    runner = JobRunner(repository, bus, run_events=events)

    await runner.recover()

    queued = await repository.list_queued()
    assert len(queued) == 1
    assert queued[0].kind == job.kind
    assert queued[0].payload == job.payload
    assert queued[0].ref_id == job.ref_id
    assert events.interrupted == [
        ("run-recovered", "step", "job interrupted by process restart", job.id),
    ]
    assert events.recovered == [
        (
            "run-recovered",
            "step",
            "进程重启后已自动重新排队",
            queued[0].id,
            job.id,
        ),
    ]


async def test_close_drains_a_completing_handler(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """Shutdown waits inside the drain window and keeps the completed result."""
    _, repository, bus = environment
    started = asyncio.Event()

    async def finish(_job: JobRunRecord) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(0.05)
        return {"drained": True}

    runner = JobRunner(repository, bus, drain_timeout_seconds=1.0)
    runner.register_handler("sync", finish)
    await runner.start()
    submitted = await runner.submit(
        kind="sync",
        payload={},
        ref_id="drain-ok",
        created_by=None,
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    await runner.close()

    completed = await repository.get(submitted.id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.result == {"drained": True}


async def test_close_times_out_and_interrupts_the_active_handler(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """A handler outside the drain window is cancelled and marked interrupted."""
    _, repository, bus = environment
    events = RecordingEvents()
    started = asyncio.Event()

    async def hold(_job: JobRunRecord) -> None:
        started.set()
        await asyncio.Event().wait()

    runner = JobRunner(
        repository,
        bus,
        run_events=events,
        drain_timeout_seconds=0.05,
    )
    runner.register_handler("evolution_advance", hold)
    await runner.start()
    submitted = await runner.submit(
        kind="evolution_advance",
        payload={"runId": "run-drain"},
        ref_id="run-drain",
        created_by=None,
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    await runner.close()

    interrupted = await repository.get(submitted.id)
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.error == "job cancelled during shutdown"
    assert events.interrupted[0][0:2] == ("run-drain", "step")


async def test_closed_runner_refuses_new_submissions(
    environment: tuple[Database, JobRepository, EventBus],
) -> None:
    """Submissions after shutdown cannot race the disposal path."""
    _, repository, bus = environment
    runner = JobRunner(repository, bus)
    await runner.close()

    with pytest.raises(RuntimeError, match="closed"):
        await runner.submit(
            kind="sync",
            payload={},
            ref_id="closed",
            created_by=None,
        )
