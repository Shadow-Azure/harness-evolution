"""Acquisition status includes the bad-case root-sync counters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.domain import bad_cases
from app.main import create_app
from app.third_party_api.session_query.models import SessionTrajectory
from app.utils.time import now_shanghai

ROOT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ROOT_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


class FakeSource:
    async def list_children(self, session_id: str) -> tuple[str, ...]:
        return ()

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        return SessionTrajectory(content='{"type":"assistant"}', line_count=1)

    async def close(self) -> None:
        return None


def _settings(tmp_path: Path, *, configured: bool = True) -> Settings:
    if configured:
        return Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("status-api-test-secret"),
            admin_username="admin",
            admin_password=SecretStr("initial-password"),
            bad_case_sync_interval_seconds=0,
            session_query_base_url="http://query.test",
            session_query_token=SecretStr("token"),
        )
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("status-api-test-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        bad_case_sync_interval_seconds=0,
    )


async def _authenticate_admin(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "initial-password"},
    )
    initial = login.json()["accessToken"]
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {initial}"},
        json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
    )
    assert changed.status_code == 204
    authenticated = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "replacement-password"},
    )
    return {"Authorization": f"Bearer {authenticated.json()['accessToken']}"}


@pytest_asyncio.fixture
async def app_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str], FastAPI]]:
    app = create_app(_settings(tmp_path), session_query_source=FakeSource())
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await ensure_fixture_external_tables(app.state.database)
        headers = await _authenticate_admin(client)
        yield client, headers, app


async def _insert_case(database: Database, root: str, suffix: str) -> None:
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=f"case-{suffix}",
                bad_case_session_id=root,
                bad_case_type="error",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title="case",
                bad_case_description="description",
                meta_data=None,
                source="test",
                created_at=now,
                updated_at=now,
            ),
        )


@pytest.mark.asyncio
async def test_status_reports_missing_status_rows_as_unsynced(
    app_client: tuple[httpx.AsyncClient, dict[str, str], FastAPI],
) -> None:
    client, headers, app = app_client
    await _insert_case(app.state.database, ROOT_A, "a")
    await _insert_case(app.state.database, ROOT_B, "b")

    response = await client.get("/api/acquisition/status", headers=headers)
    assert response.status_code == 200
    body = response.json()
    sync = body["badCaseSync"]
    assert sync["total"] == 2
    assert sync["synced"] == 0
    assert sync["unsynced"] == 2
    assert sync["syncing"] == 0
    assert sync["failed"] == 0
    assert sync["status"] == "idle"


@pytest.mark.asyncio
async def test_status_aggregates_synced_failed_and_orphan_rows(
    app_client: tuple[httpx.AsyncClient, dict[str, str], FastAPI],
) -> None:
    client, headers, app = app_client
    database = app.state.database
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    for root, suffix in ((ROOT_A, "a"), (ROOT_B, "b"), (ROOT_C, "c")):
        await _insert_case(database, root, suffix)

    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_synced(ROOT_A, agent_count=3, now=now)
    assert await repository.claim(ROOT_B, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_failed(
        ROOT_B,
        error="SESSION_QUERY_TIMEOUT",
        next_retry_at=now + timedelta(minutes=5),
        now=now,
    )
    # An orphan status row for a root no longer in bad_cases must not count.
    assert await repository.claim("orphan-root", owner="job-1", lease_seconds=60, now=now)
    await repository.mark_synced("orphan-root", agent_count=1, now=now)

    response = await client.get("/api/acquisition/status", headers=headers)
    assert response.status_code == 200
    sync = response.json()["badCaseSync"]
    assert sync["total"] == 3
    assert sync["synced"] == 1
    assert sync["unsynced"] == 2
    assert sync["syncing"] == 0
    assert sync["failed"] == 1
    assert sync["status"] == "failed"
    assert sync["lastError"] == "SESSION_QUERY_TIMEOUT"
    assert sync["lastRunAt"] is not None


@pytest.mark.asyncio
async def test_status_tolerates_missing_external_bad_cases_table(tmp_path: Path) -> None:
    """A deployment without the external table still returns acquisition status."""
    app = create_app(_settings(tmp_path), session_query_source=FakeSource())
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await _authenticate_admin(client)
        response = await client.get("/api/acquisition/status", headers=headers)
        assert response.status_code == 200
        sync = response.json()["badCaseSync"]
        assert sync["total"] == 0
        assert sync["synced"] == 0
        assert sync["unsynced"] == 0
        assert sync["status"] == "idle"


@pytest.mark.asyncio
async def test_status_is_unavailable_without_query_service(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, configured=False))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await ensure_fixture_external_tables(app.state.database)
        headers = await _authenticate_admin(client)
        await _insert_case(app.state.database, ROOT_A, "a")
        response = await client.get("/api/acquisition/status", headers=headers)
        sync = response.json()["badCaseSync"]
        assert sync["status"] == "unavailable"
        assert sync["total"] == 1
        assert sync["unsynced"] == 1
