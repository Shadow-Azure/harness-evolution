"""Durable attribution lanes, idempotency, restart recovery, and retry tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.db.crud.jobs import JobRepository
from app.db.models.evolution import evolution_runs
from app.db.models.jobs import JobRunRecord
from app.service.events import EventBus
from app.service.jobs import JobRunner
from tests.m10_02_potential_support import seed_workspace
from tests.v2_acceptance_support import (
    AcceptanceApi,
    migrated_database,
    seed_identity,
    seed_run,
)
from tests.v2_acceptance_support import acceptance_api as acceptance_api

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def scheduler(tmp_path: Path) -> AsyncIterator[tuple[JobRepository, JobRunner]]:
    """Provide one migrated durable queue without application schedulers."""
    database = await migrated_database(tmp_path, "attribution-jobs.db")
    repository = JobRepository(database)
    bus = EventBus()
    runner = JobRunner(repository, bus)
    try:
        yield repository, runner
    finally:
        await runner.close()
        await bus.close()
        await database.dispose()


async def test_attribution_lane_does_not_hold_the_serial_worker(
    scheduler: tuple[JobRepository, JobRunner],
) -> None:
    """A slow attribution executor leaves sync and other serial work runnable."""
    _, runner = scheduler
    started = asyncio.Event()
    release = asyncio.Event()
    sync_completed = asyncio.Event()

    async def attribution(_job: JobRunRecord) -> dict[str, int]:
        started.set()
        await release.wait()
        return {"processed": 1}

    async def sync(_job: JobRunRecord) -> dict[str, int]:
        sync_completed.set()
        return {"processed": 1}

    runner.register_handler("attribution_batch", attribution, concurrency_limit=2)
    runner.register_handler("sync", sync)
    attribution_job = await runner.submit(
        kind="attribution_batch",
        payload={"runId": "run-lane"},
        ref_id="run-lane",
        created_by=None,
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    sync_job = await runner.submit(
        kind="sync",
        payload={"source": "manual"},
        ref_id="sync-lane",
        created_by=None,
    )

    await asyncio.wait_for(sync_completed.wait(), timeout=1)
    assert (await runner.wait(sync_job.id)).status == "completed"
    assert (await runner.get(attribution_job.id)).status == "running"
    release.set()
    assert (await runner.wait(attribution_job.id)).status == "completed"


async def test_wait_observes_attribution_child_owned_by_another_runner(
    scheduler: tuple[JobRepository, JobRunner],
) -> None:
    """Prepare joins a reused foreign claim until its persisted result is available."""
    repository, runner = scheduler

    async def unexpected(_job: JobRunRecord) -> None:
        pytest.fail("the foreign lease was still valid")

    runner.register_handler("attribution_batch", unexpected, concurrency_limit=1)
    child = await repository.insert(
        kind="attribution_batch", payload={}, ref_id="run-shared", created_by=None
    )
    assert await repository.claim(child.id, owner="other-process") is not None
    joining = asyncio.create_task(runner.wait(child.id))
    await asyncio.sleep(0.01)
    assert not joining.done()
    assert await repository.complete(child.id, {"processed": 3}, owner="other-process")
    completed = await asyncio.wait_for(joining, timeout=2)
    assert completed.status == "completed" and completed.result == {"processed": 3}


async def test_duplicate_trigger_reuses_one_active_attribution_job(
    scheduler: tuple[JobRepository, JobRunner],
) -> None:
    """Prepare, manual, and scheduler races converge on the active run claim."""
    repository, runner = scheduler
    release = asyncio.Event()

    async def attribution(_job: JobRunRecord) -> dict[str, int]:
        await release.wait()
        return {"processed": 0}

    runner.register_handler("attribution_batch", attribution, concurrency_limit=1)
    first = await runner.submit(
        kind="attribution_batch",
        payload={"runId": "run-idempotent", "source": "prepare"},
        ref_id="run-idempotent",
        created_by=None,
    )
    second = await runner.submit(
        kind="attribution_batch",
        payload={"runId": "run-idempotent", "source": "manual"},
        ref_id="run-idempotent",
        created_by=None,
    )

    assert second.reused is True
    assert second.id == first.id
    assert len(await repository.list_for_ref("attribution_batch", "run-idempotent")) == 1
    release.set()
    await runner.wait(first.id)


async def test_cancellation_stops_inflight_attribution_work(
    scheduler: tuple[JobRepository, JobRunner],
) -> None:
    """Cancelling a running batch propagates to its handler before returning."""
    _, runner = scheduler
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def attribution(_job: JobRunRecord) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    runner.register_handler("attribution_batch", attribution, concurrency_limit=1)
    submission = await runner.submit(
        kind="attribution_batch",
        payload={"runId": "run-cancel", "source": "manual"},
        ref_id="run-cancel",
        created_by=None,
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    cancelled = await runner.cancel(submission.id)

    assert cancelled.status == "cancelled"
    assert cancelled.cancel_requested is True
    assert stopped.is_set()


async def test_cancelled_claim_rejects_stale_worker_completion(
    scheduler: tuple[JobRepository, JobRunner],
) -> None:
    """A worker cannot overwrite cancellation after losing its live claim."""
    repository, _ = scheduler
    job = await repository.insert(
        kind="attribution_batch",
        payload={"runId": "run-fenced", "source": "manual"},
        ref_id="run-fenced",
        created_by=None,
    )
    await repository.claim(job.id, owner="stale-worker")
    cancelled = await repository.request_cancel(job.id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert (
        await repository.complete(
            job.id,
            {"processed": 1},
            owner="stale-worker",
        )
        is False
    )
    assert (await repository.get(job.id)).status == "cancelled"  # type: ignore[union-attr]


async def test_restart_requeues_claim_and_retry_keeps_audit_identity(
    scheduler: tuple[JobRepository, JobRunner],
) -> None:
    """Restart recovery releases attribution leases and bounded retry reuses the row."""
    repository, runner = scheduler
    job = await repository.insert(
        kind="attribution_batch",
        payload={"runId": "run-recovery", "source": "schedule"},
        ref_id="run-recovery",
        created_by=None,
    )
    claimed = await repository.claim(job.id, owner="dead-worker")
    assert claimed is not None and claimed.lease_expires_at is not None

    await runner.recover()
    recovered = await runner.get(job.id)
    assert recovered.status == "queued"
    assert recovered.lease_owner is None

    attempts = 0

    async def flaky(_job: JobRunRecord) -> dict[str, int]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("rate limited")
        return {"processed": 1}

    runner.register_handler("attribution_batch", flaky, concurrency_limit=1)
    runner.schedule(job.id)
    failed = await runner.wait(job.id)
    assert failed.status == "failed"
    retried = await runner.retry(
        job.id,
        payload={**failed.payload, "source": "retry"},
    )
    assert retried.id == job.id
    assert retried.payload["source"] == "retry"
    completed = await runner.wait(job.id)
    assert completed.status == "completed"
    assert completed.attempt == 3


async def test_workspace_api_exposes_redacted_job_state_and_role_gate(
    acceptance_api: AcceptanceApi,
) -> None:
    """Viewers can inspect observations while only admins may admit work."""
    workspace_id = "ws-attribution-jobs"
    run_id = "run-attribution-jobs"
    await seed_workspace(acceptance_api.database, workspace_id)
    viewer = await seed_identity(
        acceptance_api.app,
        acceptance_api.database,
        username="attribution-job-viewer",
        workspace_id=workspace_id,
        workspace_role="viewer",
    )
    admin = await seed_identity(
        acceptance_api.app,
        acceptance_api.database,
        username="attribution-job-admin",
        workspace_id=workspace_id,
        workspace_role="space_admin",
    )
    await seed_run(
        acceptance_api.database,
        run_id=run_id,
        workspace_id=workspace_id,
    )
    async with acceptance_api.database.transaction() as session:
        await session.execute(
            update(evolution_runs).where(evolution_runs.c.id == run_id).values(progress_unit=3),
        )
    path = f"/api/workspaces/{workspace_id}/evolution/runs/{run_id}/attribution-jobs"

    forbidden = await acceptance_api.client.post(path, headers=viewer.headers)
    assert forbidden.status_code == 403
    accepted = await acceptance_api.client.post(path, headers=admin.headers)
    assert accepted.status_code == 202
    assert accepted.json()["status"] in {"queued", "running"}
    history = await acceptance_api.client.get(path, headers=viewer.headers)
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    assert "payload" not in history.json()["items"][0]


async def test_live_history_preserves_usage_and_reads_previously_redacted_counts(
    acceptance_api: AcceptanceApi,
) -> None:
    workspace_id, run_id = "ws-live-progress", "run-live-progress"
    await seed_workspace(acceptance_api.database, workspace_id)
    await seed_run(acceptance_api.database, run_id=run_id, workspace_id=workspace_id)
    viewer = await seed_identity(
        acceptance_api.app, acceptance_api.database, username="observer", workspace_id=workspace_id
    )
    jobs: JobRunner = acceptance_api.app.state.jobs
    job = await jobs.repository.insert(
        kind="attribution_batch", payload={"source": "prepare"}, ref_id=run_id, created_by=None
    )
    await jobs.repository.claim(job.id, owner="worker")
    path = f"/api/workspaces/{workspace_id}/evolution/runs/{run_id}/attribution-jobs"
    for value, expected in [("private-value", None), (0, 0), (3241, 3241)]:
        updated = await jobs.update_progress(
            job.id,
            0.5,
            observation={
                "tokenCount": value,
                "accessToken": "private-value",
                "total": 8,
                "completed": 4,
            },
        )
        assert updated.result and "private-value" not in str(updated.result)
        response = await acceptance_api.client.get(path, headers=viewer.headers)
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["status"] == "running"
        assert item["observation"]["tokenCount"] == expected
        assert item["observation"]["completed"] == 4
        assert item["observation"]["total"] == 8
