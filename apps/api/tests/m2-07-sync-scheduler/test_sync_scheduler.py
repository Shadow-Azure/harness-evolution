"""Sync single-flight, scheduler lifecycle, status, and API behavior."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.models.domain import sync_runs, trajectory_payloads
from app.db.models.jobs import job_runs, sync_lock
from app.main import create_app
from app.service.acquisition.replay import ReplayResult
from app.service.acquisition.sync import SyncCoordinator, SyncTriggerResult
from app.utils.time import now_shanghai

ROOT = "77777777-7777-4777-8777-777777777777"


@dataclass(frozen=True, slots=True)
class SyncEnvironment:
    """Live app, authenticated administrator client, and database handles."""

    app: FastAPI
    client: httpx.AsyncClient
    database: Database
    sync: SyncCoordinator
    admin_headers: dict[str, str]


def settings_for(tmp_path: Path, *, interval: int = 0) -> Settings:
    """Return an isolated application configuration without automatic ticks."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("sync-scheduler-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=interval,
    )


async def authenticate_admin(client: httpx.AsyncClient) -> dict[str, str]:
    """Complete forced password change and return an admin bearer header."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "initial-password"},
    )
    initial = login.json()["accessToken"]
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {initial}"},
        json={
            "oldPassword": "initial-password",
            "newPassword": "replacement-password",
        },
    )
    assert changed.status_code == 204
    authenticated = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "replacement-password"},
    )
    return {"Authorization": f"Bearer {authenticated.json()['accessToken']}"}


@pytest_asyncio.fixture
async def sync_environment(tmp_path: Path) -> AsyncIterator[SyncEnvironment]:
    """Provide a live SQLite app with the automatic scheduler disabled."""
    settings = settings_for(tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await authenticate_admin(client)
        yield SyncEnvironment(
            app=app,
            client=client,
            database=app.state.database,
            sync=app.state.sync,
            admin_headers=headers,
        )


def main_payload() -> str:
    """Return one valid root transcript with a human turn and assistant reply."""
    records = [
        {
            "type": "user",
            "sessionId": ROOT,
            "timestamp": "2026-10-20T01:00:00Z",
            "cwd": "/workspace/repository",
            "gitBranch": "main",
            "message": {"content": "synthetic prompt"},
        },
        {
            "type": "assistant",
            "sessionId": ROOT,
            "timestamp": "2026-10-20T01:01:00Z",
            "message": {
                "id": "main-message",
                "model": "test-model",
                "content": [{"type": "text", "text": "synthetic reply"}],
                "usage": {"input_tokens": 2, "output_tokens": 1},
            },
        },
    ]
    return "\n".join(json.dumps(item) for item in records) + "\n"


async def insert_pending_payload(database: Database) -> None:
    """Insert one pending root without creating a processed source cursor."""
    content = main_payload()
    async with database.transaction() as session:
        await session.execute(
            trajectory_payloads.insert().values(
                root_session_id=ROOT,
                agent_id=ROOT,
                agent_kind="main",
                payload=content,
                agent_meta=None,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                line_count=content.count("\n"),
                source_type="script",
                updated_at=datetime(2026, 10, 20, 1, tzinfo=UTC),
            ),
        )


async def insert_sync_run(
    database: Database,
    *,
    sync_run_id: str,
    status: str = "running",
) -> None:
    """Insert one replay audit row for scheduler lifecycle tests."""
    async with database.transaction() as session:
        await session.execute(
            sync_runs.insert().values(
                id=sync_run_id,
                source_type="script",
                started_at=now_shanghai(),
                finished_at=None,
                status=status,
                records_total=1,
                records_done=0,
                imported=0,
                skipped=0,
                errors=[],
            ),
        )


async def job_count(database: Database) -> int:
    """Return the number of durable job rows."""
    async with database.session() as session:
        return int(
            (await session.execute(select(func.count()).select_from(job_runs))).scalar_one(),
        )


async def lock_count(database: Database) -> int:
    """Return the number of durable sync locks."""
    async with database.session() as session:
        return int(
            (await session.execute(select(func.count()).select_from(sync_lock))).scalar_one(),
        )


async def test_no_pending_creates_no_job_and_explicit_idle_contract(
    sync_environment: SyncEnvironment,
) -> None:
    """Scheduler and manual triggers skip work without fabricating a job id."""
    triggered = await sync_environment.sync.trigger("manual", None)
    status = await sync_environment.client.get(
        "/api/acquisition/status",
        headers=sync_environment.admin_headers,
    )
    manual = await sync_environment.client.post(
        "/api/acquisition/sync",
        headers=sync_environment.admin_headers,
    )

    assert triggered.status == "idle"
    assert await job_count(sync_environment.database) == 0
    assert status.status_code == 200
    assert status.json()["activeJobId"] is None
    assert status.json()["pending"] == 0
    assert manual.status_code == 200
    assert manual.json() == {"jobId": None, "status": "idle", "reused": False}


async def test_concurrent_triggers_create_exactly_one_job_and_lock(
    sync_environment: SyncEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler and manual callers converge on one queued sync job."""
    await insert_pending_payload(sync_environment.database)
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_replay(*_args: object, **_kwargs: object) -> ReplayResult:
        started.set()
        await release.wait()
        return ReplayResult(
            status="completed",
            sync_run_id="sync-test",
            root_sessions=1,
            payloads=1,
            imported=1,
            skipped=0,
            failed=0,
            errors=0,
        )

    monkeypatch.setattr(
        "app.service.acquisition.sync.replay_pending_payloads",
        blocked_replay,
    )
    manual, scheduled = await asyncio.gather(
        sync_environment.sync.trigger("manual", None),
        sync_environment.sync.trigger("scheduler", None),
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert {manual.status, scheduled.status} == {"queued", "reused"}
    assert manual.job_id == scheduled.job_id
    assert await job_count(sync_environment.database) == 1
    assert await lock_count(sync_environment.database) == 1
    active_status = await sync_environment.sync.status()
    assert active_status.active_job_id == manual.job_id
    assert active_status.status == "running"

    release.set()
    await sync_environment.sync.jobs.wait(manual.job_id or "")
    assert await lock_count(sync_environment.database) == 0


async def test_terminal_failure_releases_only_matching_lock(
    sync_environment: SyncEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed sync handler releases its lock and records a terminal job."""
    await insert_pending_payload(sync_environment.database)

    async def fail(*_args: object, **_kwargs: object) -> ReplayResult:
        raise RuntimeError("password=must-not-leak")

    monkeypatch.setattr("app.service.acquisition.sync.replay_pending_payloads", fail)
    triggered = await sync_environment.sync.trigger("manual", None)
    assert triggered.job_id is not None
    terminal = await sync_environment.sync.jobs.wait(triggered.job_id)

    assert terminal.status == "failed"
    assert terminal.error is not None
    assert "must-not-leak" not in terminal.error
    assert await lock_count(sync_environment.database) == 0


async def test_status_reports_counts_batch_and_next_run(
    sync_environment: SyncEnvironment,
) -> None:
    """Status derives active, pending, processed, and latest batch fields."""
    await insert_pending_payload(sync_environment.database)
    triggered = await sync_environment.sync.trigger("manual", None)
    assert triggered.job_id is not None
    terminal = await sync_environment.sync.jobs.wait(triggered.job_id)
    assert terminal.ref_id is not None
    async with sync_environment.database.transaction() as session:
        await session.execute(
            update(sync_runs)
            .where(sync_runs.c.id == terminal.ref_id)
            .values(
                errors=[
                    {
                        "sessionId": ROOT,
                        "agentId": ROOT,
                        "lineNo": 3,
                        "code": "INVALID_JSONL_LINE",
                        "message": "JSONL line could not be parsed",
                    },
                    {"message": "unstructured detail must not be exposed"},
                ],
            ),
        )

    status = await sync_environment.client.get(
        "/api/acquisition/status",
        headers=sync_environment.admin_headers,
    )

    assert status.status_code == 200
    body = status.json()
    assert body["activeJobId"] is None
    assert body["pending"] == 0
    assert body["processed"] == 1
    assert body["imported"] == 1
    assert body["errors"] == [
        {
            "sessionId": ROOT,
            "agentId": ROOT,
            "lineNo": 3,
            "code": "INVALID_JSONL_LINE",
            "message": "JSONL line could not be parsed",
        },
    ]
    assert "unstructured detail" not in status.text
    assert body["lastRunAt"] is not None
    assert body["nextRunAt"] is None


async def test_manual_endpoint_queues_one_job_with_sync_run_provenance(
    sync_environment: SyncEnvironment,
) -> None:
    """The admin endpoint returns a queued job whose ref is the replay batch."""
    await insert_pending_payload(sync_environment.database)

    response = await sync_environment.client.post(
        "/api/acquisition/sync",
        headers=sync_environment.admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["reused"] is False
    job = await sync_environment.sync.jobs.wait(body["jobId"])
    assert job.status == "completed"
    assert job.ref_id is not None
    assert job.ref_id == job.id
    assert job.result is not None
    assert job.result["syncRunId"] == job.ref_id
    assert await lock_count(sync_environment.database) == 0


async def test_manual_sync_requires_admin_and_authentication(
    sync_environment: SyncEnvironment,
) -> None:
    """Members cannot trigger sync and anonymous callers are rejected."""
    member_token = sync_environment.app.state.identity.tokens.create_access_token(
        user_id="member-1",
        role="member",
        must_change_password=False,
    )

    forbidden = await sync_environment.client.post(
        "/api/acquisition/sync",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    anonymous = await sync_environment.client.post("/api/acquisition/sync")

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    assert anonymous.status_code == 401


async def test_stale_terminal_lock_is_removed_before_next_trigger(
    sync_environment: SyncEnvironment,
) -> None:
    """A lock whose job is terminal is reclaimed instead of blocking future work."""
    await insert_pending_payload(sync_environment.database)
    first = await sync_environment.sync.trigger("manual", None)
    assert first.job_id is not None
    await sync_environment.sync.jobs.wait(first.job_id)

    async with sync_environment.database.transaction() as session:
        await session.execute(
            sync_lock.insert().values(
                name="sync",
                job_id=first.job_id,
                owner="crashed-process",
                acquired_at=now_shanghai(),
                expires_at=now_shanghai() + timedelta(minutes=30),
            ),
        )
        await session.execute(
            update(trajectory_payloads)
            .where(trajectory_payloads.c.root_session_id == ROOT)
            .values(content_hash="f" * 64),
        )

    second = await sync_environment.sync.trigger("manual", None)

    assert second.status == "queued"
    assert second.job_id not in {None, first.job_id}


async def test_scheduler_zero_disables_and_shutdown_is_clean(tmp_path: Path) -> None:
    """A zero interval starts no background task and stop remains idempotent."""
    settings = settings_for(tmp_path, interval=0)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.sync._scheduler_task is None
        assert (await app.state.sync.status()).next_run_at is None
    await app.state.sync.stop_scheduler()


async def test_positive_scheduler_interval_ticks_and_shutdown_cancels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A positive interval triggers the shared path and stops with its lifespan."""
    ticks = asyncio.Event()
    app = create_app(settings_for(tmp_path, interval=1))

    async def fake_trigger(
        _source: str,
        _created_by: str | None,
    ) -> SyncTriggerResult:
        ticks.set()
        return SyncTriggerResult("idle", None, False)

    monkeypatch.setattr(app.state.sync, "trigger", fake_trigger)
    async with app.router.lifespan_context(app):
        assert app.state.sync._scheduler_task is not None
        assert (await app.state.sync.status()).next_run_at is not None
        await asyncio.wait_for(ticks.wait(), timeout=2)

    assert app.state.sync._scheduler_task is None


async def test_shutdown_cancels_handler_and_releases_lock(
    sync_environment: SyncEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runner shutdown records interruption and releases the matching lock."""
    await insert_pending_payload(sync_environment.database)
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def wait_forever(*_args: object, **_kwargs: object) -> ReplayResult:
        started.set()
        await blocked.wait()
        raise AssertionError("cancelled handler must not return")

    monkeypatch.setattr(
        "app.service.acquisition.sync.replay_pending_payloads",
        wait_forever,
    )
    triggered = await sync_environment.sync.trigger("manual", None)
    assert triggered.job_id is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    await sync_environment.sync.jobs.close()

    interrupted = await sync_environment.sync.jobs.get(triggered.job_id)
    assert interrupted.status == "interrupted"
    assert await lock_count(sync_environment.database) == 0


async def test_restart_requeues_sync_with_fresh_run_and_finalizes_old_audit(
    sync_environment: SyncEnvironment,
) -> None:
    """Restart recovery preserves the old audit and retries under a fresh batch id."""
    original_ref = "sync-restart-original"
    await insert_pending_payload(sync_environment.database)
    original = await sync_environment.sync.job_repository.insert(
        kind="sync",
        payload={"source": "restart-test"},
        ref_id=original_ref,
        created_by=None,
    )
    await sync_environment.sync.job_repository.claim(original.id)
    await insert_sync_run(sync_environment.database, sync_run_id=original_ref)
    async with sync_environment.database.transaction() as session:
        await session.execute(
            sync_lock.insert().values(
                name="sync",
                job_id=original.id,
                owner="crashed-process",
                acquired_at=now_shanghai(),
                expires_at=now_shanghai() + timedelta(minutes=30),
            ),
        )

    await sync_environment.sync.jobs.start()
    replacement = await sync_environment.sync.job_repository.find_active_kind("sync")
    assert replacement is not None
    terminal = await sync_environment.sync.jobs.wait(replacement.id)

    old = await sync_environment.sync.jobs.get(original.id)
    assert old.status == "interrupted"
    assert replacement.id != original.id
    assert replacement.ref_id not in {None, original_ref}
    assert terminal.status == "completed"
    async with sync_environment.database.session() as session:
        old_audit = (
            (await session.execute(select(sync_runs).where(sync_runs.c.id == original_ref)))
            .mappings()
            .one()
        )
    assert old_audit["status"] == "interrupted"
    assert old_audit["finished_at"] is not None


async def test_sync_run_is_finalized_when_handler_fails(
    sync_environment: SyncEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler failure terminalizes the replay audit before releasing its lock."""
    await insert_pending_payload(sync_environment.database)
    observed_sync_run_id: str | None = None

    async def fail_after_audit(
        database: Database,
        *,
        sync_run_id: str,
        **_kwargs: object,
    ) -> ReplayResult:
        nonlocal observed_sync_run_id
        observed_sync_run_id = sync_run_id
        await insert_sync_run(database, sync_run_id=sync_run_id)
        raise RuntimeError("sanitized later")

    monkeypatch.setattr(
        "app.service.acquisition.sync.replay_pending_payloads",
        fail_after_audit,
    )
    triggered = await sync_environment.sync.trigger("manual", None)
    assert triggered.job_id is not None
    terminal = await sync_environment.sync.jobs.wait(triggered.job_id)

    assert terminal.status == "failed"
    assert observed_sync_run_id is not None
    async with sync_environment.database.session() as session:
        audit = (
            (
                await session.execute(
                    select(sync_runs).where(sync_runs.c.id == observed_sync_run_id),
                )
            )
            .mappings()
            .one()
        )
    assert audit["status"] == "failed"
    assert audit["finished_at"] is not None
    assert await lock_count(sync_environment.database) == 0


async def test_sync_run_is_finalized_when_handler_is_cancelled(
    sync_environment: SyncEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown cancellation terminalizes the replay audit as interrupted."""
    await insert_pending_payload(sync_environment.database)
    observed_sync_run_id: str | None = None
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def wait_after_audit(
        database: Database,
        *,
        sync_run_id: str,
        **_kwargs: object,
    ) -> ReplayResult:
        nonlocal observed_sync_run_id
        observed_sync_run_id = sync_run_id
        await insert_sync_run(database, sync_run_id=sync_run_id)
        started.set()
        await blocked.wait()
        raise AssertionError("cancelled handler must not return")

    monkeypatch.setattr(
        "app.service.acquisition.sync.replay_pending_payloads",
        wait_after_audit,
    )
    triggered = await sync_environment.sync.trigger("manual", None)
    assert triggered.job_id is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    await sync_environment.sync.jobs.close()

    terminal = await sync_environment.sync.jobs.get(triggered.job_id)
    assert terminal.status == "interrupted"
    assert observed_sync_run_id is not None
    async with sync_environment.database.session() as session:
        audit = (
            (
                await session.execute(
                    select(sync_runs).where(sync_runs.c.id == observed_sync_run_id),
                )
            )
            .mappings()
            .one()
        )
    assert audit["status"] == "interrupted"
    assert audit["finished_at"] is not None
    assert await lock_count(sync_environment.database) == 0
