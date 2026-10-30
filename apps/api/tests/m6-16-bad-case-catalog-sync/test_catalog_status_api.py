"""Acquisition status exposes catalog sync counters and attribution progress."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis
from app.main import create_app
from app.third_party_api.bad_case_query.models import BadCaseItem, BadCasePage


class FakeCatalogSource:
    """Deterministic paginated catalog source for the status API."""

    def __init__(self, items: tuple[BadCaseItem, ...]) -> None:
        self.items = sorted(items, key=lambda item: item.bad_case_id)

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        remaining = [item for item in self.items if item.bad_case_id > after_id]
        return BadCasePage(
            total=len(remaining),
            offset=offset,
            limit=limit,
            items=tuple(remaining[offset : offset + limit]),
        )

    async def close(self) -> None:
        return None


def _item(case_id: int) -> BadCaseItem:
    return BadCaseItem(
        bad_case_id=case_id,
        bad_case_session_id=f"session-{case_id}",
        bad_case_type="self",
        object_name="deep-research",
        object_type="skill",
        object_version="v1",
        bad_case_agent_id=None,
        bad_case_title=f"case {case_id}",
        bad_case_description="description",
        meta_data=None,
        source="test",
        created_at=datetime.fromisoformat("2026-10-30T10:00:00+08:00"),
        updated_at=datetime.fromisoformat("2026-10-30T10:00:00+08:00"),
    )


def _settings(tmp_path: Path, *, configured: bool) -> Settings:
    extra: dict[str, Any] = (
        {
            "bad_case_query_base_url": "http://query.test",
            "bad_case_query_token": SecretStr("token"),
        }
        if configured
        else {}
    )
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("status-api-test-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        bad_case_catalog_sync_interval_seconds=0,
        **extra,
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


async def _wait_for_status(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    predicate: Callable[[Any], bool],
    *,
    max_wait_seconds: float = 20.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        response = await client.get("/api/acquisition/status", headers=headers)
        assert response.status_code == 200
        payload: dict[str, Any] = response.json()
        if predicate(payload):
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError("acquisition status did not reach the expected state")


@pytest_asyncio.fixture
async def configured_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str], FastAPI]]:
    settings = _settings(tmp_path, configured=True)
    database = create_database(settings)
    await database.start()
    await upgrade_database(database, bootstrap_external_tables=True)
    app = create_app(
        settings,
        database=database,
        bad_case_catalog_source=FakeCatalogSource((_item(1), _item(2))),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client, await _authenticate_admin(client), app


@pytest.mark.asyncio
async def test_status_reports_catalog_and_analysis_progress(
    configured_client: tuple[httpx.AsyncClient, dict[str, str], FastAPI],
) -> None:
    """Catalog counters converge and attribution counts follow the analysis table."""
    client, headers, app = configured_client

    payload = await _wait_for_status(
        client,
        headers,
        lambda data: (
            data["badCaseCatalogSync"]["synced"] == 2
            and data["badCaseCatalogSync"]["status"] == "idle"
        ),
    )

    catalog = payload["badCaseCatalogSync"]
    assert catalog["synced"] == 2
    assert catalog["unsynced"] == 0
    assert catalog["lastBadCaseId"] == 2
    assert catalog["status"] == "idle"
    assert catalog["lastError"] is None
    assert payload["badCaseAnalysis"] == {
        "total": 2,
        "analyzed": 0,
        "pending": 2,
        "issue": 0,
        "nonIssue": 0,
    }

    async with app.state.database.transaction() as session:
        await session.execute(
            bad_case_analysis.insert().values(
                bad_case_id="1",
                analysis_status="analyzed_issue",
                probe_id=None,
                analysis_result=None,
                updated_at=datetime.fromisoformat("2026-10-30T11:00:00+08:00"),
            ),
        )

    refreshed = await client.get("/api/acquisition/status", headers=headers)
    analysis = refreshed.json()["badCaseAnalysis"]
    assert analysis["total"] == 2
    assert analysis["analyzed"] == 1
    assert analysis["pending"] == 1
    assert analysis["issue"] == 1
    assert analysis["nonIssue"] == 0


@pytest.mark.asyncio
async def test_status_reports_unavailable_without_catalog_source(
    tmp_path: Path,
) -> None:
    """An unconfigured catalog endpoint still returns zeroed, readable counters."""
    settings = _settings(tmp_path, configured=False)
    database = create_database(settings)
    await database.start()
    await upgrade_database(database, bootstrap_external_tables=True)
    app = create_app(settings, database=database)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await _authenticate_admin(client)
        response = await client.get("/api/acquisition/status", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["badCaseCatalogSync"] == {
        "synced": 0,
        "unsynced": 0,
        "lastBadCaseId": 0,
        "status": "unavailable",
        "lastRunAt": None,
        "lastError": None,
    }
    assert payload["badCaseAnalysis"] == {
        "total": 0,
        "analyzed": 0,
        "pending": 0,
        "issue": 0,
        "nonIssue": 0,
    }


@pytest.mark.asyncio
async def test_empty_catalog_finishes_without_error(tmp_path: Path) -> None:
    """An empty upstream finishes a run with zero counts and no failure."""
    settings = _settings(tmp_path, configured=True)
    database = create_database(settings)
    await database.start()
    await upgrade_database(database, bootstrap_external_tables=True)
    app = create_app(
        settings,
        database=database,
        bad_case_catalog_source=FakeCatalogSource(()),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await _authenticate_admin(client)
        payload = await _wait_for_status(
            client,
            headers,
            lambda data: (
                data["badCaseCatalogSync"]["lastRunAt"] is not None
                and data["badCaseCatalogSync"]["status"] == "idle"
            ),
        )

    catalog = payload["badCaseCatalogSync"]
    assert catalog["synced"] == 0
    assert catalog["unsynced"] == 0
    assert catalog["lastBadCaseId"] == 0
    assert catalog["lastError"] is None
    assert payload["badCaseAnalysis"]["total"] == 0
