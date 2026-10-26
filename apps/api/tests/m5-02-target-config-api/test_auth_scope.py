"""Authorization and persistence contracts for evolution target configuration."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution_targets import (
    EvolutionTargetConflict,
    EvolutionTargetRepository,
    ModelUsageRecord,
)
from app.db.models.domain import agents, session_families, source_records
from app.db.models.evolution import evolution_runs
from app.main import create_app

ADMIN_TEMP_PASSWORD = "admin-temporary-password"
ADMIN_PASSWORD = "admin-replacement-password"
MEMBER_TEMP_PASSWORD = "member-temporary-password"
MEMBER_PASSWORD = "member-replacement-password"


@dataclass(frozen=True, slots=True)
class TargetApiEnvironment:
    """Two authenticated roles sharing one migrated application."""

    admin: httpx.AsyncClient
    member: httpx.AsyncClient
    database: Database


async def _complete_login(
    client: httpx.AsyncClient,
    *,
    username: str,
    old_password: str,
    new_password: str,
) -> None:
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
async def target_api(tmp_path: Path) -> AsyncIterator[TargetApiEnvironment]:
    """Provide member/admin clients over one seeded real SQLite application."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("target-config-signing-secret-with-sufficient-length"),
        admin_username="admin",
        admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
    )
    app = create_app(settings)
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
            await _complete_login(
                admin,
                username="admin",
                old_password=ADMIN_TEMP_PASSWORD,
                new_password=ADMIN_PASSWORD,
            )
            await _complete_login(
                member,
                username="member",
                old_password=MEMBER_TEMP_PASSWORD,
                new_password=MEMBER_PASSWORD,
            )
            yield TargetApiEnvironment(
                admin=admin,
                member=member,
                database=app.state.database,
            )
    finally:
        await member.aclose()
        await admin.aclose()


def _target_values(
    object_type: str,
    object_name: str,
    *,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "object_type": object_type,
        "object_name": object_name,
        "repo_url": f"https://git.example.com/{object_name}.git",
        "sub_dir": f"skills/{object_name}",
        "default_ref": "main",
        "enabled": enabled,
        "created_by": None,
    }


async def test_target_reads_allow_members_but_writes_require_admin(
    target_api: TargetApiEnvironment,
) -> None:
    """Only target mutations require the administrator role."""
    assert (await target_api.member.get("/api/evolution/targets")).status_code == 404
    assert (await target_api.admin.get("/api/evolution/targets")).status_code == 404

    denied = await target_api.member.post("/api/evolution/targets", json={})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    allowed_by_middleware = await target_api.admin.post(
        "/api/evolution/targets",
        json={},
    )
    assert allowed_by_middleware.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "role", "expected"),
    [
        ("GET", "/api/users", "member", 403),
        ("POST", "/api/users", "member", 403),
        ("GET", "/api/acquisition/status", "member", 200),
        ("POST", "/api/acquisition/sync", "member", 403),
        ("POST", "/api/acquisition/pull", "member", 403),
        ("GET", "/api/evolution/targets/any/versions", "member", 404),
        ("PUT", "/api/evolution/targets/any", "member", 403),
        ("DELETE", "/api/evolution/targets/any", "member", 403),
    ],
)
async def test_admin_scope_is_method_and_path_specific(
    target_api: TargetApiEnvironment,
    method: str,
    path: str,
    role: str,
    expected: int,
) -> None:
    """Existing admin scopes and mixed target scopes remain method-specific."""
    client = target_api.member if role == "member" else target_api.admin
    response = await client.request(method, path)
    assert response.status_code == expected


async def test_repository_crud_ordering_and_conflicts(
    target_api: TargetApiEnvironment,
) -> None:
    """Targets round-trip, sort deterministically, and reject duplicate objects."""
    repository = EvolutionTargetRepository(target_api.database)

    disabled = await repository.insert(_target_values("skill", "z-disabled", enabled=False))
    agent = await repository.insert(_target_values("agent", "b-agent"))
    skill = await repository.insert(_target_values("skill", "a-skill"))

    assert [item.id for item in await repository.list()] == [
        agent.id,
        skill.id,
        disabled.id,
    ]
    assert [item.id for item in await repository.list(enabled_only=True)] == [
        agent.id,
        skill.id,
    ]
    assert await repository.get(skill.id) == skill
    assert await repository.find("skill", "a-skill") == skill

    with pytest.raises(EvolutionTargetConflict):
        await repository.insert(_target_values("skill", "a-skill"))

    updated = await repository.update(
        skill.id,
        {
            "object_type": "skill",
            "object_name": "renamed-skill",
            "repo_url": "ssh://git@git.example.com/renamed-skill.git",
            "sub_dir": "skills/renamed-skill",
            "default_ref": "v2",
            "enabled": False,
        },
    )
    assert updated.object_name == "renamed-skill"
    assert updated.enabled is False
    with pytest.raises(EvolutionTargetConflict):
        await repository.update(
            updated.id,
            {
                "object_type": "skill",
                "object_name": "z-disabled",
                "repo_url": "https://git.example.com/renamed-skill.git",
                "sub_dir": "skills/renamed-skill",
                "default_ref": "v2",
                "enabled": True,
            },
        )
    with pytest.raises(LookupError):
        await repository.update(
            "missing-target",
            {
                "object_type": "skill",
                "object_name": "missing-target",
                "repo_url": "https://git.example.com/missing.git",
                "sub_dir": "skills/missing",
                "default_ref": "main",
                "enabled": True,
            },
        )
    assert await repository.delete(disabled.id) is True
    assert await repository.delete(disabled.id) is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("preparing", True),
        ("running", True),
        ("blocked", True),
        ("completed", False),
        ("failed", False),
        ("interrupted", False),
    ],
)
async def test_active_run_detection_uses_only_open_states(
    target_api: TargetApiEnvironment,
    status: str,
    expected: bool,
) -> None:
    """Deletion protection ignores terminal evolution runs."""
    repository = EvolutionTargetRepository(target_api.database)
    target = await repository.insert(_target_values("skill", f"run-{status}"))
    now = datetime.now(UTC)
    async with target_api.database.transaction() as session:
        await session.execute(
            insert(evolution_runs).values(
                id=f"run-{status}",
                title="target-in-use",
                mode="full",
                engine_key="full",
                eval_config={},
                target_config_id=target.id,
                target_type="skill",
                target_name=target.object_name,
                target_version="v1",
                repo_url=target.repo_url,
                sub_dir=target.sub_dir,
                remote_name="origin",
                push_status="pending",
                models=[],
                status=status,
                retry_attempts=0,
                eval_status="pending",
                progress_unit=0,
                stats={},
                created_at=now,
            ),
        )

    assert await repository.has_active_runs(target.id) is expected


async def test_model_aggregation_uses_agents_table(
    target_api: TargetApiEnvironment,
) -> None:
    """Model usage counts distinct sessions and every main/subagent row."""
    now = datetime.now(UTC)
    async with target_api.database.transaction() as session:
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
                    agents_count=0,
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
                ("s1", None),
                ("s2", "   "),
            ],
            start=1,
        ):
            await session.execute(
                insert(agents).values(
                    id=f"a{index}",
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

    repository = EvolutionTargetRepository(target_api.database)
    assert await repository.list_models() == (
        ModelUsageRecord(model="glm-5.3", session_count=2, agent_count=3),
        ModelUsageRecord(model="glm-5.3-flash", session_count=1, agent_count=1),
    )
