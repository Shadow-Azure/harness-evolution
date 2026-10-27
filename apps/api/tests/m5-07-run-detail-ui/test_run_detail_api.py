"""Authenticated run-detail API contract."""

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

ADMIN_TEMP_PASSWORD = "run-detail-admin-temp-password"
ADMIN_PASSWORD = "run-detail-admin-password"
NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)


def _run_values() -> dict[str, Any]:
    """Build one complete run snapshot for the detail shell."""
    return {
        "id": "run-detail",
        "title": "run-detail title",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": "data/repos/target",
        "base_ref": "v2.0.0",
        "base_commit": "9f3c2a1",
        "branch_name": "evo/run-detail",
        "workspace_path": "data/workspaces/run-detail",
        "remote_name": "origin",
        "push_status": "succeeded",
        "pushed_at": NOW,
        "push_error": None,
        "models": ["glm-5.3"],
        "status": "running",
        "blocked_stage": None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": None,
        "error_message": None,
        "error_at": None,
        "progress_unit": 4,
        "stats": {
            "sessions": 4,
            "probes": 3,
            "byAttributeType": {
                "model": 1,
                "prompt": 1,
                "error": 1,
                "nonIssue": 0,
            },
        },
        "created_by": None,
        "created_at": NOW,
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
async def detail_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Provide one authenticated client over a migrated SQLite app."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("run-detail-api-signing-secret-with-sufficient-length"),
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
                await session.execute(insert(evolution_runs).values(**_run_values()))
                await session.execute(
                    insert(probe_clusters),
                    [
                        {
                            "probe_cluster_id": f"cluster-{seq}",
                            "run_id": "run-detail",
                            "seq": seq,
                            "probe_cluster_description": f"cluster {seq}",
                            "probe_cluster_type": "error",
                            "confidence": 0.82,
                            "impact": 9,
                            "severity": 7.4,
                            "rank": seq,
                            "created_at": NOW,
                        }
                        for seq in (1, 2)
                    ],
                )
            yield client
    finally:
        await client.aclose()


async def test_run_detail_returns_workspace_and_six_backend_states(
    detail_client: httpx.AsyncClient,
) -> None:
    """The shell carries every field needed by the stepper without inference."""
    response = await detail_client.get("/api/evolution/runs/run-detail")

    assert response.status_code == 200
    body = response.json()
    assert body["runId"] == "run-detail"
    assert body["workspace"] == {
        "repoUrl": "https://example.invalid/skills.git",
        "subDir": "skills/deep-research",
        "repoPath": "data/repos/target",
        "baseRef": "v2.0.0",
        "baseCommit": "9f3c2a1",
        "branchName": "evo/run-detail",
        "workspacePath": "data/workspaces/run-detail",
        "remote": "origin",
        "pushStatus": "succeeded",
        "pushedAt": "2026-10-27T08:00:00+08:00",
        "pushError": None,
    }
    assert body["evalStatus"] == "pending"
    assert body["retryAttempts"] == 0
    assert body["lastEventSeq"] == 0
    assert [step["key"] for step in body["steps"]] == [
        "input",
        "clusters",
        "attribution",
        "severity",
        "iteration",
        "final",
    ]
    assert [step["status"] for step in body["steps"]] == [
        "done",
        "done",
        "done",
        "done",
        "active",
        "pending",
    ]
    assert body["steps"][4]["detail"] == "第 1/2 轮"
    assert body["steps"][5]["clickable"] is False


async def test_run_detail_requires_authentication(
    detail_client: httpx.AsyncClient,
) -> None:
    """Run workspace and stage state require a bearer token."""
    detail_client.headers.pop("Authorization", None)

    response = await detail_client.get("/api/evolution/runs/run-detail")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_run_detail_reports_unknown_run(
    detail_client: httpx.AsyncClient,
) -> None:
    """An unknown run returns the stable not-found code."""
    response = await detail_client.get("/api/evolution/runs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"
