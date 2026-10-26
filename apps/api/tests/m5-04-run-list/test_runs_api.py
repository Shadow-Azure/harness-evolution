"""Authenticated run-list API contract."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.models.evolution import evolution_runs, probe_clusters
from app.main import create_app

ADMIN_TEMP_PASSWORD = "run-list-admin-temp-password"
ADMIN_PASSWORD = "run-list-admin-password"
MEMBER_TEMP_PASSWORD = "run-list-member-temp-password"
MEMBER_PASSWORD = "run-list-member-password"
NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)


def _run_values(run_id: str, status: str, *, created_at: datetime = NOW) -> dict[str, Any]:
    """Build one valid run row with stable snapshots."""
    return {
        "id": run_id,
        "title": f"{run_id} title",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "remote_name": "origin",
        "push_status": "succeeded",
        "models": ["glm-5.3"],
        "status": status,
        "retry_attempts": 0,
        "eval_status": "pending",
        "progress_unit": 4,
        "stats": {
            "sessions": 4,
            "probes": 3,
            "usedProbes": 2,
            "byAttributeType": {"model": 1, "prompt": 1, "error": 0, "nonIssue": 1},
        },
        "created_by": None,
        "created_at": created_at,
    }


async def _login(
    client: httpx.AsyncClient,
    username: str,
    old_password: str,
    new_password: str,
) -> None:
    """Complete the forced password flow and install a bearer token."""
    login = await client.post(
        "/api/auth/login",
        json={"username": username, "password": old_password},
    )
    assert login.status_code == 200
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={"oldPassword": old_password, "newPassword": new_password},
    )
    assert changed.status_code == 204
    relogin = await client.post(
        "/api/auth/login",
        json={"username": username, "password": new_password},
    )
    assert relogin.status_code == 200
    client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"


@pytest_asyncio.fixture
async def run_api(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    """Provide authenticated admin and member clients over a migrated app."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("run-list-api-signing-secret-with-sufficient-length"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    admin = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    member = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            await app.state.identity.create_user(
                username="member",
                display_name="Member",
                password=MEMBER_TEMP_PASSWORD,
                role="member",
            )
            await _login(admin, "admin", ADMIN_TEMP_PASSWORD, ADMIN_PASSWORD)
            await _login(member, "member", MEMBER_TEMP_PASSWORD, MEMBER_PASSWORD)
            async with app.state.database.transaction() as session:
                await session.execute(
                    insert(evolution_runs),
                    [
                        _run_values("run-running", "running"),
                        _run_values("run-completed", "completed"),
                    ],
                )
                await session.execute(
                    insert(probe_clusters),
                    [
                        {
                            "probe_cluster_id": f"cluster-{seq}",
                            "run_id": "run-running",
                            "seq": seq,
                            "probe_cluster_description": f"cluster {seq}",
                            "probe_cluster_type": "error",
                            "confidence": 0.8,
                            "impact": 9,
                            "severity": 7.2,
                            "rank": seq,
                            "created_at": NOW,
                        }
                        for seq in (1, 2)
                    ],
                )
            yield admin, member
    finally:
        await member.aclose()
        await admin.aclose()


async def test_run_list_requires_authentication(
    run_api: tuple[httpx.AsyncClient, httpx.AsyncClient],
) -> None:
    """Run history is visible only to authenticated users."""
    _, member = run_api
    member.headers.pop("Authorization", None)

    response = await member.get("/api/evolution/runs")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_admin_and_member_read_the_same_grouped_camel_case_payload(
    run_api: tuple[httpx.AsyncClient, httpx.AsyncClient],
) -> None:
    """Both roles receive backend ordering, copy, progress, and stats."""
    admin, member = run_api

    admin_response = await admin.get("/api/evolution/runs")
    member_response = await member.get("/api/evolution/runs")

    assert admin_response.status_code == 200
    assert member_response.json() == admin_response.json()
    body = admin_response.json()
    assert [item["runId"] for item in body["running"]] == ["run-running"]
    assert [item["runId"] for item in body["history"]] == ["run-completed"]
    card = body["running"][0]
    assert card["target"] == {
        "type": "skill",
        "name": "deep-research",
        "version": "v2.0.0",
    }
    assert card["progress"] == {
        "unit": 4,
        "total": 7,
        "percent": 57,
        "stageLabel": "第 5/6 步 · 迭代优化 · 第 1/2 轮",
        "doneRounds": 0,
        "accepted": 0,
    }
    assert card["stats"]["usedProbes"] == 2
    assert card["stats"]["clusters"] == 2
    assert card["createdBy"] is None


async def test_run_list_returns_both_empty_groups_for_an_empty_database(
    tmp_path: Path,
) -> None:
    """The page can render its required empty state before any run exists."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("run-list-empty-api-signing-secret"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    admin = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            await _login(admin, "admin", ADMIN_TEMP_PASSWORD, ADMIN_PASSWORD)
            response = await admin.get("/api/evolution/runs")

        assert response.status_code == 200
        assert response.json() == {"running": [], "history": []}
    finally:
        await admin.aclose()
