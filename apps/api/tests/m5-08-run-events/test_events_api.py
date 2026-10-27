"""Authenticated run event REST and run-detail sequence integration."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.models.evolution import evolution_runs
from app.main import create_app

ADMIN_TEMP_PASSWORD = "events-admin-temp-password"
ADMIN_PASSWORD = "events-admin-password"
NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)


def _run_values(run_id: str = "run-events", status: str = "running") -> dict[str, object]:
    """Build a complete run row for event API scenarios."""
    return {
        "id": run_id,
        "title": "event api fixture",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": None,
        "base_ref": "v2.0.0",
        "base_commit": None,
        "branch_name": f"evo/{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "pending",
        "pushed_at": None,
        "push_error": None,
        "window_from": None,
        "window_to": None,
        "models": [],
        "status": status,
        "blocked_stage": None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": None,
        "error_message": None,
        "error_at": None,
        "progress_unit": 0,
        "stats": {},
        "created_by": None,
        "created_at": NOW,
        "finished_at": None,
    }


async def _login(client: httpx.AsyncClient) -> None:
    """Complete the forced password flow and install a bearer token."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEMP_PASSWORD},
    )
    assert login.status_code == 200
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={
            "oldPassword": ADMIN_TEMP_PASSWORD,
            "newPassword": ADMIN_PASSWORD,
        },
    )
    assert changed.status_code == 204
    relogin = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert relogin.status_code == 200
    client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"


@pytest_asyncio.fixture
async def events_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    """Provide one authenticated client over a migrated SQLite app."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("run-events-api-signing-secret-with-sufficient-length"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            await _login(client)
            async with app.state.database.transaction() as session:
                await session.execute(
                    insert(evolution_runs).values(**_run_values()),
                )
            yield client, app
    finally:
        await client.aclose()


async def test_events_api_pages_filters_and_backfills_last_event_seq(
    events_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """REST returns the stable page and run detail carries its high-water mark."""
    client, app = events_client
    for message in ("created", "started", "failed"):
        await app.state.evolution_events.record(
            "run-events",
            (
                "run_created"
                if message == "created"
                else "prepare_started"
                if message == "started"
                else "run_failed"
            ),
            level="error" if message == "failed" else "info",
            stage="prepare",
            message=message,
        )

    first = await client.get(
        "/api/evolution/runs/run-events/events?afterSeq=0&limit=1",
    )
    next_page = await client.get(
        "/api/evolution/runs/run-events/events?afterSeq=1&limit=100",
    )
    errors = await client.get(
        "/api/evolution/runs/run-events/events?level=error",
    )
    detail = await client.get("/api/evolution/runs/run-events")

    assert first.status_code == 200
    assert first.json() == {
        "items": [
            {
                "seq": 1,
                "eventType": "run_created",
                "level": "info",
                "stage": "prepare",
                "stepIndex": None,
                "clusterId": None,
                "roundId": None,
                "jobId": None,
                "message": "created",
                "createdAt": first.json()["items"][0]["createdAt"],
                "payload": None,
                "error": None,
            },
        ],
        "nextSeq": 1,
        "hasMore": True,
    }
    assert [item["seq"] for item in next_page.json()["items"]] == [2, 3]
    assert next_page.json()["hasMore"] is False
    assert [item["eventType"] for item in errors.json()["items"]] == ["run_failed"]
    assert detail.json()["lastEventSeq"] == 3


async def test_events_api_validates_auth_run_and_pagination(
    events_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Invalid paging is 422, unknown runs are 404, and auth stays fail-closed."""
    client, _ = events_client
    too_large = await client.get(
        "/api/evolution/runs/run-events/events?limit=501",
    )
    missing = await client.get("/api/evolution/runs/missing/events")
    client.headers.pop("Authorization", None)
    unauthenticated = await client.get(
        "/api/evolution/runs/run-events/events",
    )

    assert too_large.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_ticket_endpoint_uses_the_real_run_resource_authorizer(
    events_client: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """SSE tickets accept the active persisted run and reject an unknown run."""
    client, _ = events_client
    active = await client.post(
        "/api/events/ticket",
        json={"topics": ["run:run-events"], "lastEventId": 0},
    )
    missing = await client.post(
        "/api/events/ticket",
        json={"topics": ["run:missing"], "lastEventId": 0},
    )

    assert active.status_code == 200
    assert active.json()["topics"] == ["run:run-events"]
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "TICKET_INVALID"
