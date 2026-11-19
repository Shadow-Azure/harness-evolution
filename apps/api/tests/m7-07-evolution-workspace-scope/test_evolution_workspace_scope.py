"""Cross-workspace isolation for targets, runs, events, tickets, and catalogs."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.models.domain import evolution_targets
from app.db.models.evolution import evolution_runs
from app.db.models.run_events import evolution_run_events
from app.main import create_app
from tests.target_content_support import FakeTargetVersionResolver
from tests.workspaces.helpers import create_user, insert_member, insert_workspace

NOW = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)
SECRET = SecretStr("m7-07-workspace-scope-signing-secret")


class FakeGitRemote:
    """Accept remote validation without touching the network."""

    def __init__(self) -> None:
        """Start with no recorded calls."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Accept every well-formed test remote."""

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Return a stable version list."""
        return ("v2.0.0",)


@dataclass(frozen=True, slots=True)
class ScopeEnvironment:
    """One migrated application with two spaces and role-specific callers."""

    app: Any
    database: Database
    client: httpx.AsyncClient
    admin_token: str
    space_admin_token: str
    viewer_token: str
    outsider_token: str
    workspace_a: str
    workspace_b: str


def _run_values(run_id: str, workspace_id: str, *, status: str = "completed") -> dict[str, Any]:
    """Build one complete run row owned by a workspace."""
    return {
        "id": run_id,
        "workspace_id": workspace_id,
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
        "models": [],
        "status": status,
        "blocked_stage": "push" if status == "blocked" else None,
        "retry_attempts": 0,
        "eval_status": "pending",
        "progress_unit": 4,
        "stats": {},
        "created_by": None,
        "created_at": NOW,
    }


def _target_values(
    target_id: str,
    workspace_id: str,
    *,
    object_name: str = "deep-research",
) -> dict[str, Any]:
    """Build one enabled target row owned by a workspace."""
    return {
        "id": target_id,
        "workspace_id": workspace_id,
        "object_type": "skill",
        "object_name": object_name,
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "default_ref": "main",
        "validation_project_id": "val-set",
        "test_project_id": "test-set",
        "enabled": True,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _bearer(token: str) -> dict[str, str]:
    """Return the authorization header for one minted token."""
    return {"Authorization": f"Bearer {token}"}


def _token(app: Any, user_id: str, role: str = "member") -> str:
    """Mint a bearer token directly without a password round trip."""
    token: str = app.state.identity.tokens.create_access_token(
        user_id=user_id,
        role=role,
        must_change_password=False,
    )
    return token


@pytest_asyncio.fixture
async def scope(tmp_path: Path) -> AsyncIterator[ScopeEnvironment]:
    """Provide two workspaces, a global admin, and three workspace callers."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SECRET,
            admin_username="admin",
            admin_password=SecretStr("m7-07-admin-temp-password"),
        ),
        git_remote=FakeGitRemote(),
        target_version_resolver=FakeTargetVersionResolver(),
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            database = app.state.database
            admin = next(
                user for user in await app.state.identity.list_users() if user.role == "admin"
            )
            workspace_a = await insert_workspace(database, name="space-a")
            workspace_b = await insert_workspace(database, name="space-b")
            space_admin = await create_user(database, username="space-admin-a")
            viewer = await create_user(database, username="viewer-a")
            outsider = await create_user(database, username="outsider")
            await insert_member(
                database,
                workspace_id=workspace_a,
                user_id=space_admin,
                role="space_admin",
            )
            await insert_member(
                database,
                workspace_id=workspace_a,
                user_id=viewer,
                role="viewer",
            )
            yield ScopeEnvironment(
                app=app,
                database=database,
                client=client,
                admin_token=_token(app, admin.id, "admin"),
                space_admin_token=_token(app, space_admin),
                viewer_token=_token(app, viewer),
                outsider_token=_token(app, outsider),
                workspace_a=workspace_a,
                workspace_b=workspace_b,
            )
    finally:
        await client.aclose()


async def test_targets_are_workspace_scoped_and_write_is_space_admin(
    scope: ScopeEnvironment,
) -> None:
    """The same object pair is independent per space and only admins can write."""
    body = {
        "objectType": "skill",
        "objectName": "deep-research",
        "repoUrl": "https://example.invalid/skills.git",
        "subDir": "skills/deep-research",
        "defaultRef": "main",
        "validationProjectId": "val-set",
        "testProjectId": "test-set",
        "enabled": True,
    }

    created_a = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/targets",
        json=body,
        headers=_bearer(scope.space_admin_token),
    )
    created_b = await scope.client.post(
        f"/api/workspaces/{scope.workspace_b}/evolution/targets",
        json=body,
        headers=_bearer(scope.admin_token),
    )
    viewer_write = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/targets",
        json={**body, "objectName": "viewer-write"},
        headers=_bearer(scope.viewer_token),
    )

    assert created_a.status_code == 201
    assert created_b.status_code == 201
    assert created_a.json()["id"] != created_b.json()["id"]
    assert viewer_write.status_code == 403
    assert viewer_write.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"

    visible_a = await scope.client.get(
        f"/api/workspaces/{scope.workspace_a}/evolution/targets",
        headers=_bearer(scope.viewer_token),
    )
    foreign = await scope.client.get(
        f"/api/workspaces/{scope.workspace_b}/evolution/targets",
        headers=_bearer(scope.viewer_token),
    )
    legacy = await scope.client.get(
        "/api/evolution/targets",
        headers=_bearer(scope.viewer_token),
    )

    assert [item["id"] for item in visible_a.json()["items"]] == [created_a.json()["id"]]
    assert foreign.status_code == 404
    assert [item["id"] for item in legacy.json()["items"]] == [created_a.json()["id"]]

    cross_space_update = await scope.client.put(
        f"/api/workspaces/{scope.workspace_a}/evolution/targets/{created_b.json()['id']}",
        json=body,
        headers=_bearer(scope.space_admin_token),
    )
    assert cross_space_update.status_code == 404
    assert cross_space_update.json()["error"]["code"] == "TARGET_NOT_FOUND"


async def test_runs_steps_events_and_retry_cannot_cross_workspaces(
    scope: ScopeEnvironment,
) -> None:
    """Every run read path and retry stays inside the path workspace."""
    async with scope.database.transaction() as session:
        await session.execute(
            insert(evolution_runs),
            [
                _run_values("run-a", scope.workspace_a),
                _run_values("run-b", scope.workspace_b),
                _run_values("run-a-blocked", scope.workspace_a, status="blocked"),
                _run_values("run-b-blocked", scope.workspace_b, status="blocked"),
            ],
        )
    await scope.app.state.evolution_events.record(
        "run-a",
        "run_created",
        level="info",
        stage="prepare",
        message="created",
    )
    await scope.app.state.evolution_events.record(
        "run-b",
        "run_created",
        level="info",
        stage="prepare",
        message="created",
    )

    listing = await scope.client.get(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs",
        headers=_bearer(scope.viewer_token),
    )
    legacy_listing = await scope.client.get(
        "/api/evolution/runs",
        headers=_bearer(scope.viewer_token),
    )
    foreign_run = await scope.client.get(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs/run-b",
        headers=_bearer(scope.viewer_token),
    )
    foreign_events = await scope.client.get(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs/run-b/events",
        headers=_bearer(scope.viewer_token),
    )
    legacy_foreign_detail = await scope.client.get(
        "/api/evolution/runs/run-b",
        headers=_bearer(scope.viewer_token),
    )
    foreign_step = await scope.client.get(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs/run-b/steps/range",
        headers=_bearer(scope.viewer_token),
    )
    viewer_retry = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs/run-a-blocked/retry",
        headers=_bearer(scope.viewer_token),
    )
    cross_space_retry = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs/run-b-blocked/retry",
        headers=_bearer(scope.space_admin_token),
    )
    admin_retry = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs/run-a-blocked/retry",
        headers=_bearer(scope.space_admin_token),
    )

    run_ids = {item["runId"] for group in ("running", "history") for item in listing.json()[group]}
    assert run_ids == {"run-a", "run-a-blocked"}
    assert {
        item["runId"] for group in ("running", "history") for item in legacy_listing.json()[group]
    } == {"run-a", "run-a-blocked"}
    assert foreign_run.status_code == 404
    assert foreign_run.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert foreign_events.status_code == 404
    assert legacy_foreign_detail.status_code == 404
    assert foreign_step.status_code == 404
    assert viewer_retry.status_code == 403
    assert cross_space_retry.status_code == 404
    assert admin_retry.status_code == 202

    async with scope.database.session() as session:
        rows = (
            await session.execute(
                select(evolution_run_events.c.run_id, evolution_run_events.c.workspace_id),
            )
        ).all()
    assert {run_id: workspace_id for run_id, workspace_id in rows} == {
        "run-a": scope.workspace_a,
        "run-b": scope.workspace_b,
    }


async def test_launch_and_cluster_preview_only_use_workspace_targets(
    scope: ScopeEnvironment,
) -> None:
    """A space cannot launch a target configured in another space."""
    async with scope.database.transaction() as session:
        await session.execute(
            insert(evolution_targets).values(
                _target_values("target-b", scope.workspace_b),
            ),
        )
    body = {
        "targetType": "skill",
        "targetName": "deep-research",
        "targetVersion": "v2.0.0",
        "mode": "full",
    }

    viewer_launch = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs",
        json=body,
        headers=_bearer(scope.viewer_token),
    )
    cross_space_launch = await scope.client.post(
        f"/api/workspaces/{scope.workspace_a}/evolution/runs",
        json=body,
        headers=_bearer(scope.space_admin_token),
    )
    legacy_cross_space = await scope.client.post(
        "/api/evolution/runs",
        json=body,
        headers=_bearer(scope.space_admin_token),
    )

    assert viewer_launch.status_code == 403
    assert cross_space_launch.status_code == 409
    assert cross_space_launch.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"
    assert legacy_cross_space.status_code == 409
    assert legacy_cross_space.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"


async def test_sse_ticket_is_bound_to_workspace_membership(
    scope: ScopeEnvironment,
) -> None:
    """A ticket for another space or another space's run is rejected."""
    async with scope.database.transaction() as session:
        await session.execute(
            insert(evolution_runs),
            [
                _run_values("run-a", scope.workspace_a, status="running"),
                _run_values("run-b", scope.workspace_b, status="running"),
            ],
        )

    same_space = await scope.client.post(
        "/api/events/ticket",
        json={
            "topics": ["run:run-a"],
            "workspaceId": scope.workspace_a,
        },
        headers=_bearer(scope.viewer_token),
    )
    foreign_space = await scope.client.post(
        "/api/events/ticket",
        json={
            "topics": ["run:run-a"],
            "workspaceId": scope.workspace_b,
        },
        headers=_bearer(scope.viewer_token),
    )
    foreign_run = await scope.client.post(
        "/api/events/ticket",
        json={
            "topics": ["run:run-b"],
            "workspaceId": scope.workspace_a,
        },
        headers=_bearer(scope.viewer_token),
    )
    legacy_foreign_run = await scope.client.post(
        "/api/events/ticket",
        json={"topics": ["run:run-b"]},
        headers=_bearer(scope.viewer_token),
    )
    outsider = await scope.client.post(
        "/api/events/ticket",
        json={
            "topics": ["run:run-a"],
            "workspaceId": scope.workspace_a,
        },
        headers=_bearer(scope.outsider_token),
    )

    assert same_space.status_code == 200
    for response in (foreign_space, foreign_run, legacy_foreign_run, outsider):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "TICKET_INVALID"


async def test_catalogs_follow_visible_workspaces(
    scope: ScopeEnvironment,
) -> None:
    """Legacy and V2 catalogs never expose another workspace's targets."""
    async with scope.database.transaction() as session:
        await session.execute(
            insert(evolution_targets),
            [
                _target_values("target-a", scope.workspace_a, object_name="object-a"),
                _target_values("target-b", scope.workspace_b, object_name="object-b"),
            ],
        )

    v2 = await scope.client.get(
        f"/api/workspaces/{scope.workspace_a}/catalogs/targets",
        headers=_bearer(scope.viewer_token),
    )
    legacy = await scope.client.get(
        "/api/catalogs/targets",
        headers=_bearer(scope.viewer_token),
    )
    admin_legacy = await scope.client.get(
        "/api/catalogs/targets",
        headers=_bearer(scope.admin_token),
    )

    assert [item["name"] for item in v2.json()["skill"]] == ["object-a"]
    assert [item["name"] for item in legacy.json()["skill"]] == ["object-a"]
    assert {item["name"] for item in admin_legacy.json()["skill"]} == {
        "object-a",
        "object-b",
    }
