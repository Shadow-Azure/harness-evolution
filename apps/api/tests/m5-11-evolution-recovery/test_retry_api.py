"""Manual retry endpoint contract for blocked evolution runs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.models.evolution import evolution_runs
from app.db.models.jobs import JobRunRecord, job_runs
from app.main import create_app

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
ADMIN_TEMP_PASSWORD = "m5-11-admin-temp-password"
ADMIN_PASSWORD = "m5-11-admin-password"
MEMBER_TEMP_PASSWORD = "m5-11-member-temp-password"


def _run_values(run_id: str, status: str = "blocked") -> dict[str, object]:
    """Build one complete run row for retry API scenarios."""
    return {
        "id": run_id,
        "title": "retry api fixture",
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
        "branch_name": f"evo/20261028-{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "failed",
        "pushed_at": None,
        "push_error": "push failed",
        "window_from": None,
        "window_to": None,
        "models": [],
        "status": status,
        "blocked_stage": "push" if status == "blocked" else None,
        "retry_attempts": 2,
        "next_retry_at": NOW - timedelta(minutes=1) if status == "blocked" else None,
        "eval_status": "pending",
        "error_stage": "push" if status == "blocked" else None,
        "error_message": "push failed" if status == "blocked" else None,
        "error_at": NOW if status == "blocked" else None,
        "progress_unit": 4,
        "stats": {},
        "created_by": None,
        "created_at": NOW,
        "finished_at": None,
    }


async def _login(client: httpx.AsyncClient, password: str = ADMIN_TEMP_PASSWORD) -> str:
    """Log in and install a bearer token, returning the access token."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": password},
    )
    assert login.status_code == 200
    return str(login.json()["accessToken"])


async def _complete_password_change(client: httpx.AsyncClient, token: str) -> None:
    """Replace the seeded temporary password and install a durable token."""
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"oldPassword": ADMIN_TEMP_PASSWORD, "newPassword": ADMIN_PASSWORD},
    )
    assert changed.status_code == 204
    client.headers["Authorization"] = f"Bearer {await _login(client, ADMIN_PASSWORD)}"


@pytest_asyncio.fixture
async def retry_api(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    """Provide one authenticated client over a migrated SQLite app."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("m5-11-retry-api-signing-secret"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
            blocked_sweep_seconds=3600,
        ),
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            await _complete_password_change(client, await _login(client))
            yield client, app
    finally:
        await client.aclose()


async def _insert_run(app: FastAPI, run_id: str, status: str = "blocked") -> None:
    """Insert one run row directly so the endpoint contract is isolated from git."""
    async with app.state.database.transaction() as session:
        await session.execute(insert(evolution_runs).values(**_run_values(run_id, status)))


async def _jobs_for(app: FastAPI, run_id: str) -> list[Mapping[str, Any]]:
    """Return retry jobs persisted for one run in creation order."""
    async with app.state.database.session() as session:
        rows = (
            (
                await session.execute(
                    select(job_runs)
                    .where(job_runs.c.kind == "evolution_retry", job_runs.c.ref_id == run_id)
                    .order_by(job_runs.c.created_at),
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


async def test_retry_requires_authentication(
    retry_api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """The retry route stays fail-closed without a bearer token."""
    client, app = retry_api
    await _insert_run(app, "run-blocked")
    client.headers.pop("Authorization", None)

    response = await client.post("/api/evolution/runs/run-blocked/retry")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_retry_accepts_a_blocked_run_and_is_idempotent(
    retry_api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """A blocked run returns 202, resets backoff, then reuses the active job."""
    client, app = retry_api
    await _insert_run(app, "run-blocked")
    release = asyncio.Event()

    async def blocking_handler(_job: JobRunRecord) -> Mapping[str, Any]:
        """Keep the first retry active so the duplicate path can be exercised."""
        await release.wait()
        return {"ok": True}

    app.state.jobs._handlers["evolution_retry"] = blocking_handler

    first = await client.post("/api/evolution/runs/run-blocked/retry")
    assert first.status_code == 202
    assert first.json() == {"jobId": first.json()["jobId"], "reused": False}
    job_id = str(first.json()["jobId"])

    async with app.state.database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_runs).where(evolution_runs.c.id == "run-blocked"),
                )
            )
            .mappings()
            .one()
        )
    assert row["retry_attempts"] == 0
    assert row["next_retry_at"] is None

    second = await client.post("/api/evolution/runs/run-blocked/retry")
    assert second.status_code == 202
    assert second.json() == {"jobId": job_id, "reused": True}

    jobs = await _jobs_for(app, "run-blocked")
    assert len(jobs) == 1
    assert jobs[0]["payload"] == {"runId": "run-blocked", "automatic": False}

    release.set()
    await app.state.jobs.wait(job_id)


async def test_retry_rejects_runs_that_are_not_blocked(
    retry_api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Only blocked runs are retryable."""
    client, app = retry_api
    await _insert_run(app, "run-running", status="running")

    response = await client.post("/api/evolution/runs/run-running/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_NOT_RETRYABLE"
    assert response.json()["error"]["details"] == {"status": "running"}


async def test_retry_rejects_unknown_runs(
    retry_api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Unknown run ids keep the stable 404 envelope."""
    client, _app = retry_api

    response = await client.post("/api/evolution/runs/run-unknown/retry")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


async def test_retry_rejects_password_change_required_members(
    retry_api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """A member who must rotate their password receives 403 before any job."""
    client, app = retry_api
    await _insert_run(app, "run-blocked")
    created = await client.post(
        "/api/users",
        json={
            "username": "retry-member",
            "displayName": "Retry Member",
            "password": MEMBER_TEMP_PASSWORD,
            "role": "member",
        },
    )
    assert created.status_code == 201

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as member:
        login = await member.post(
            "/api/auth/login",
            json={"username": "retry-member", "password": MEMBER_TEMP_PASSWORD},
        )
        assert login.status_code == 200
        member.headers["Authorization"] = f"Bearer {login.json()['accessToken']}"
        response = await member.post("/api/evolution/runs/run-blocked/retry")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert await _jobs_for(app, "run-blocked") == []
