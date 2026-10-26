"""Member-readable catalogs backed by target configuration and Agent rows."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.models.domain import agents, session_families, source_records
from app.main import create_app
from app.third_party_api.git.remote import RepoInvalid

CATALOG_ADMIN_TEMP_PASSWORD = "catalog-admin-temp-password"
CATALOG_ADMIN_PASSWORD = "catalog-admin-password"
CATALOG_MEMBER_TEMP_PASSWORD = "catalog-member-temp-password"
CATALOG_MEMBER_PASSWORD = "catalog-member-password"


class CatalogGitRemote:
    """Return deterministic tags for enabled target repositories."""

    def __init__(self) -> None:
        """Configure tag data keyed by repository URL."""
        self.tags = {
            "https://git.example.com/deep-research.git": ("v2.0.0", "v1.9.0"),
            "https://git.example.com/general-purpose.git": ("v3.0.0",),
            "https://git.example.com/failing.git": (),
        }
        self.listed: list[str] = []
        self.fail = False

    async def validate(self, _repo_url: str, _ref: str) -> None:
        """Catalog tests do not save targets through this adapter."""

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Return sorted tags for one repository."""
        self.listed.append(repo_url)
        if self.fail:
            raise RepoInvalid("credential=should-not-leak")
        return tuple(sorted(self.tags.get(repo_url, ())))


@dataclass(frozen=True, slots=True)
class CatalogApiEnvironment:
    """Authenticated member/admin clients and related application state."""

    admin: httpx.AsyncClient
    member: httpx.AsyncClient
    app: FastAPI
    database: Database
    remote: CatalogGitRemote


async def _complete_login(
    client: httpx.AsyncClient,
    *,
    username: str,
    old_password: str,
    new_password: str,
) -> None:
    """Complete forced password change and install an access token."""
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
async def catalog_api(tmp_path: Path) -> AsyncIterator[CatalogApiEnvironment]:
    """Provide a real app with member/admin clients and a fake git adapter."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("catalog-signing-secret-with-sufficient-length"),
        admin_username="admin",
        admin_password=SecretStr(CATALOG_ADMIN_TEMP_PASSWORD),
    )
    remote = CatalogGitRemote()
    app = create_app(settings, git_remote=remote)
    transport = httpx.ASGITransport(app=app)
    admin = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    member = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            await app.state.identity.create_user(
                username="member",
                display_name="Member",
                password=CATALOG_MEMBER_TEMP_PASSWORD,
                role="member",
            )
            await _complete_login(
                admin,
                username="admin",
                old_password=CATALOG_ADMIN_TEMP_PASSWORD,
                new_password=CATALOG_ADMIN_PASSWORD,
            )
            await _complete_login(
                member,
                username="member",
                old_password=CATALOG_MEMBER_TEMP_PASSWORD,
                new_password=CATALOG_MEMBER_PASSWORD,
            )
            yield CatalogApiEnvironment(
                admin=admin,
                member=member,
                app=app,
                database=app.state.database,
                remote=remote,
            )
    finally:
        await member.aclose()
        await admin.aclose()


def _target_values(
    object_type: str,
    object_name: str,
    *,
    enabled: bool = True,
    repo_url: str | None = None,
) -> dict[str, object]:
    """Build one repository row for catalog tests."""
    return {
        "object_type": object_type,
        "object_name": object_name,
        "repo_url": repo_url or f"https://git.example.com/{object_name}.git",
        "sub_dir": f"{object_type}s/{object_name}",
        "default_ref": "main",
        "enabled": enabled,
        "created_by": None,
    }


async def test_target_catalog_returns_only_enabled_targets_with_tags(
    catalog_api: CatalogApiEnvironment,
) -> None:
    """Target catalog groups enabled skills and agents and resolves remote tags."""
    repository = EvolutionTargetRepository(catalog_api.database)
    skill = await repository.insert(
        _target_values(
            "skill",
            "deep-research",
        ),
    )
    agent = await repository.insert(_target_values("agent", "general-purpose"))
    await repository.insert(
        _target_values(
            "skill",
            "disabled-research",
            enabled=False,
        ),
    )

    response = await catalog_api.member.get("/api/catalogs/targets")

    assert response.status_code == 200
    assert response.json() == {
        "skill": [
            {
                "id": skill.id,
                "name": "deep-research",
                "repoUrl": "https://git.example.com/deep-research.git",
                "subDir": "skills/deep-research",
                "defaultRef": "main",
                "versions": ["v1.9.0", "v2.0.0"],
            }
        ],
        "agent": [
            {
                "id": agent.id,
                "name": "general-purpose",
                "repoUrl": "https://git.example.com/general-purpose.git",
                "subDir": "agents/general-purpose",
                "defaultRef": "main",
                "versions": ["v3.0.0"],
            }
        ],
    }
    assert set(catalog_api.remote.listed) == {
        "https://git.example.com/general-purpose.git",
        "https://git.example.com/deep-research.git",
    }


async def test_catalog_requires_authentication(
    catalog_api: CatalogApiEnvironment,
) -> None:
    """Catalog reads require an authenticated user."""
    anonymous = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=catalog_api.app),
        base_url="http://testserver",
    )
    try:
        response = await anonymous.get("/api/catalogs/targets")
    finally:
        await anonymous.aclose()
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_model_catalog_uses_normalized_agents(
    catalog_api: CatalogApiEnvironment,
) -> None:
    """Model catalog aggregates every main/subagent row from normalized storage."""
    now = datetime.now(UTC)
    async with catalog_api.database.transaction() as session:
        for index, session_id in enumerate(("s1", "s2"), start=1):
            await session.execute(
                insert(source_records).values(
                    id=index,
                    root_session_id=session_id,
                    agent_id=f"{session_id}-main",
                    kind="main",
                    source_type="jsonl",
                    line_count=1,
                    received_at=now,
                ),
            )
            await session.execute(
                insert(session_families).values(
                    id=session_id,
                    short_title=session_id,
                    title=session_id,
                    search_text=session_id,
                    repo_name="repo",
                    project_path="/repo",
                    models=[],
                    started_at=now,
                    ended_at=now,
                    duration_seconds=0,
                    status="ok",
                    skill_names=[],
                    user_turns_count=0,
                    messages_count=1,
                    tools_count=0,
                    errors_count=0,
                    agents_count=1,
                    tokens_total=0,
                    source_type="jsonl",
                    main_record_id=index,
                    imported_at=now,
                    updated_at=now,
                ),
            )
        for index, (session_id, model) in enumerate(
            [
                ("s1", "glm-5.3"),
                ("s1", "glm-5.3"),
                ("s2", "glm-5.3"),
                ("s1", "glm-5.3-flash"),
                ("s2", None),
                ("s2", "   "),
            ],
            start=1,
        ):
            await session.execute(
                insert(agents).values(
                    id=f"catalog-agent-{index}",
                    root_session_id=session_id,
                    parent_agent_id=None,
                    kind="main" if index == 1 else "subagent",
                    model=model,
                    spawn_depth=0,
                    lines=1,
                    messages_count=1,
                    tokens_total=0,
                    tools_count=0,
                    errors_count=0,
                    sort_key=float(index),
                ),
            )

    response = await catalog_api.member.get("/api/catalogs/models")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"model": "glm-5.3", "sessionCount": 2, "agentCount": 3},
            {"model": "glm-5.3-flash", "sessionCount": 1, "agentCount": 1},
        ]
    }


async def test_catalog_sanitizes_remote_failure(
    catalog_api: CatalogApiEnvironment,
) -> None:
    """A broken configured remote returns the stable sanitized repository error."""
    repository = EvolutionTargetRepository(catalog_api.database)
    await repository.insert(_target_values("skill", "deep-research"))
    catalog_api.remote.fail = True

    response = await catalog_api.member.get("/api/catalogs/targets")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REPO_INVALID"
    assert "should-not-leak" not in response.text
