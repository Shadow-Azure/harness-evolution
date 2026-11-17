"""Attribution Skill registry, precedence, and immutable revision contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import inspect

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.main import create_app

ADMIN_TEMP_PASSWORD = "attribution-skill-temporary-password"  # noqa: S105
ADMIN_PASSWORD = "attribution-skill-replacement-password"  # noqa: S105


@dataclass(frozen=True, slots=True)
class SkillApiEnvironment:
    """Authenticated client, database, and one workspace target."""

    client: httpx.AsyncClient
    database: Database
    target_id: str


async def _login(client: httpx.AsyncClient) -> None:
    """Complete the required first-login password rotation."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEMP_PASSWORD},
    )
    assert login.status_code == 200
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={"oldPassword": ADMIN_TEMP_PASSWORD, "newPassword": ADMIN_PASSWORD},
    )
    assert changed.status_code == 204
    relogin = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert relogin.status_code == 200
    client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"


@pytest_asyncio.fixture
async def skill_api(tmp_path: Path) -> AsyncIterator[SkillApiEnvironment]:
    """Provide a migrated SQLite app with one configured target."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("attribution-skill-signing-secret-with-length"),
        admin_username="admin",
        admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
    )
    app = create_app(settings)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    try:
        async with app.router.lifespan_context(app):
            await _login(client)
            target = await EvolutionTargetRepository(app.state.database).insert(
                {
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "object_type": "skill",
                    "object_name": "deep-research",
                    "repo_url": "https://git.example.com/deep-research.git",
                    "sub_dir": "skills/deep-research",
                    "default_ref": "main",
                    "validation_project_id": "validation",
                    "test_project_id": "test",
                    "enabled": True,
                    "created_by": None,
                },
            )
            yield SkillApiEnvironment(client, app.state.database, target.id)
    finally:
        await client.aclose()


def _base(path: str) -> str:
    """Return a workspace-scoped evolution API path."""
    return f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/evolution/{path}"


async def _create_skill(
    environment: SkillApiEnvironment,
    key: str,
) -> dict[str, object]:
    """Create one workspace Skill through the public API."""
    response = await environment.client.post(
        _base("attribution-skills"),
        json={
            "skillKey": key,
            "displayName": key,
            "description": f"Instructions for {key}",
            "content": {"instructions": f"Run {key}", "tools": ["trace.read"]},
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


@pytest.mark.asyncio
async def test_resolution_precedence_and_unbind_fallbacks(
    skill_api: SkillApiEnvironment,
) -> None:
    """Target override wins, then workspace default, then protected platform default."""
    listed = await skill_api.client.get(_base("attribution-skills"))
    assert listed.status_code == 200
    assert listed.json()["items"][0]["skillKey"] == "platform-default"

    workspace_skill = await _create_skill(skill_api, "workspace-analysis")
    target_skill = await _create_skill(skill_api, "target-analysis")
    default_binding = await skill_api.client.put(
        _base("attribution-skill-bindings/default"),
        json={"skillRevisionId": workspace_skill["id"]},
    )
    assert default_binding.status_code == 200
    assert default_binding.json()["source"] == "workspace"

    target_path = _base(f"targets/{skill_api.target_id}/attribution-skill")
    target_binding = await skill_api.client.put(
        target_path,
        json={"skillRevisionId": target_skill["id"]},
    )
    assert target_binding.status_code == 200
    assert target_binding.json()["skillKey"] == "target-analysis"
    assert target_binding.json()["source"] == "target"

    assert (await skill_api.client.delete(target_path)).status_code == 204
    workspace_fallback = await skill_api.client.get(target_path)
    assert workspace_fallback.json()["skillKey"] == "workspace-analysis"
    assert workspace_fallback.json()["source"] == "workspace"

    assert (
        await skill_api.client.delete(_base("attribution-skill-bindings/default"))
    ).status_code == 204
    platform_fallback = await skill_api.client.get(target_path)
    assert platform_fallback.json()["skillKey"] == "platform-default"
    assert platform_fallback.json()["source"] == "platform"


@pytest.mark.asyncio
async def test_revisions_are_append_only_and_schema_compatible(
    skill_api: SkillApiEnvironment,
) -> None:
    """Publishing appends revisions and rejects duplicate content or schemas."""
    first = await _create_skill(skill_api, "versioned-analysis")
    published = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": {"instructions": "Run revision two", "tools": []},
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert published.status_code == 201
    assert published.json()["revision"] == 2
    assert published.json()["contentHash"] != first["contentHash"]

    duplicate = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": first["content"],
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v2",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ATTRIBUTION_SKILL_EXISTS"

    incompatible = await skill_api.client.post(
        _base(f"attribution-skills/{first['skillId']}/revisions"),
        json={
            "content": {"instructions": "Unsupported"},
            "executorType": "agent_stub",
            "outputSchemaVersion": "probe-report/v1",
        },
    )
    assert incompatible.status_code == 422
    assert incompatible.json()["error"]["code"] == "ATTRIBUTION_SKILL_INVALID"


@pytest.mark.asyncio
async def test_platform_skill_cannot_be_disabled(skill_api: SkillApiEnvironment) -> None:
    """The built-in platform definition is referenceable but not workspace-owned."""
    response = await skill_api.client.patch(
        _base("attribution-skills/attribution-skill-platform-default"),
        json={"enabled": False},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTRIBUTION_SKILL_NOT_FOUND"


@pytest.mark.asyncio
async def test_migration_installs_registry_and_run_snapshot_columns(
    skill_api: SkillApiEnvironment,
) -> None:
    """The migration head exposes all registry tables and immutable run fields."""
    async with skill_api.database.engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        run_columns = await connection.run_sync(
            lambda sync: {
                str(column["name"]) for column in inspect(sync).get_columns("evolution_runs")
            },
        )
    assert {
        "attribution_skills",
        "attribution_skill_revisions",
        "attribution_skill_bindings",
    } <= tables
    assert {
        "attribution_skill_key",
        "attribution_skill_revision",
        "attribution_skill_content_hash",
    } <= run_columns
