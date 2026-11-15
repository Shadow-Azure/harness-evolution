"""auth/session aggregation, visibility, and truncation behavior."""

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.db.crud.workspaces import WorkspaceRepository
from app.utils.time import now_shanghai
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_bad_case,
    insert_member,
    insert_workspace,
    insert_workspaces_for_user,
)


async def test_session_returns_visible_workspaces_with_live_aggregates(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A member sees only joined spaces with their role and batched counters."""
    app, client = workspace_client
    database = app.state.database
    member_id = await create_user(database, username="alice")
    colleague_id = await create_user(database, username="bob")
    start = now_shanghai() - timedelta(minutes=5)
    harness = await insert_workspace(database, name="Harness", quota=60, created_at=start)
    research = await insert_workspace(
        database,
        name="Research",
        quota=10,
        created_at=start + timedelta(minutes=1),
    )
    hidden = await insert_workspace(
        database,
        name="Hidden",
        created_at=start + timedelta(minutes=2),
    )
    await insert_member(
        database,
        workspace_id=harness,
        user_id=member_id,
        role="space_admin",
    )
    await insert_member(
        database,
        workspace_id=harness,
        user_id=colleague_id,
        role="viewer",
    )
    await insert_bad_case(database, workspace_id=harness, bad_case_id="bc-1")
    await insert_bad_case(database, workspace_id=harness, bad_case_id="bc-2")
    await insert_member(
        database,
        workspace_id=research,
        user_id=member_id,
        role="member",
    )
    await insert_bad_case(database, workspace_id=research, bad_case_id="bc-3")
    await insert_bad_case(database, workspace_id=hidden, bad_case_id="bc-4")
    token = access_token(app, user_id=member_id)

    response = await client.get("/api/auth/session", headers=bearer(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"] == {
        "id": member_id,
        "username": "alice",
        "displayName": "alice",
        "role": "member",
        "mustChangePassword": False,
    }
    assert payload["truncated"] is False
    assert [item["id"] for item in payload["workspaces"]] == [research, harness]
    by_id = {item["id"]: item for item in payload["workspaces"]}
    assert by_id[harness] == {
        "id": harness,
        "name": "Harness",
        "mark": "Harness",
        "role": "space_admin",
        "quota": 60,
        "used": 2,
        "memberCount": 2,
        "spaceAdminCount": 1,
    }
    assert by_id[research] == {
        "id": research,
        "name": "Research",
        "mark": "Research",
        "role": "member",
        "quota": 10,
        "used": 1,
        "memberCount": 1,
        "spaceAdminCount": 0,
    }
    assert hidden not in by_id


async def test_session_for_a_member_without_workspaces_is_empty(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A user with no membership rows still gets a complete, empty payload."""
    app, client = workspace_client
    user_id = await create_user(app.state.database, username="lonely")
    token = access_token(app, user_id=user_id)

    response = await client.get("/api/auth/session", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["workspaces"] == []
    assert response.json()["truncated"] is False


async def test_global_admin_session_lists_every_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The global administrator sees all spaces as ``global_admin``."""
    app, client = workspace_client
    database = app.state.database
    admin_id = await create_user(database, username="root", role="admin")
    start = now_shanghai() - timedelta(minutes=3)
    first = await insert_workspace(database, name="First", created_at=start)
    second = await insert_workspace(
        database,
        name="Second",
        quota=7,
        created_at=start + timedelta(minutes=1),
    )
    member_id = await create_user(database, username="carol")
    await insert_member(database, workspace_id=second, user_id=member_id, role="space_admin")
    await insert_bad_case(database, workspace_id=second, bad_case_id="bc-admin")
    token = access_token(app, user_id=admin_id, role="admin")

    response = await client.get("/api/auth/session", headers=bearer(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["truncated"] is False
    by_id = {item["id"]: item for item in payload["workspaces"]}
    assert {first, second, "ws-default"} <= set(by_id)
    assert by_id[first]["role"] == "global_admin"
    assert by_id[second]["role"] == "global_admin"
    assert by_id[second]["used"] == 1
    assert by_id[second]["memberCount"] == 1
    assert by_id[second]["spaceAdminCount"] == 1
    assert by_id["ws-default"]["role"] == "global_admin"


@pytest.mark.parametrize(
    ("workspace_count", "expected_count", "expected_truncated"),
    [(200, 200, False), (201, 200, True)],
)
async def test_session_truncates_at_two_hundred_workspaces(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
    workspace_count: int,
    expected_count: int,
    expected_truncated: bool,
) -> None:
    """More than 200 visible spaces keep the newest 200 and flag truncation."""
    app, client = workspace_client
    database = app.state.database
    user_id = await create_user(database, username=f"bulk-{workspace_count}")
    await insert_workspaces_for_user(
        database,
        user_id=user_id,
        count=workspace_count,
    )
    token = access_token(app, user_id=user_id)

    response = await client.get("/api/auth/session", headers=bearer(token))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["workspaces"]) == expected_count
    assert payload["truncated"] is expected_truncated


async def test_session_is_available_during_the_forced_password_change(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The forced-change state still allows auth/session, but not other business APIs."""
    app, client = workspace_client
    user_id = await create_user(
        app.state.database,
        username="forced",
        must_change_password=True,
    )
    token = access_token(app, user_id=user_id, must_change_password=True)

    session = await client.get("/api/auth/session", headers=bearer(token))
    blocked = await client.get("/api/users", headers=bearer(token))

    assert session.status_code == 200
    assert session.json()["user"]["mustChangePassword"] is True
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"


async def test_session_rejects_missing_or_anonymous_users(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Unauthenticated calls and tokens for vanished users both fail with 401."""
    app, client = workspace_client
    anonymous = await client.get("/api/auth/session")
    ghost_token = access_token(app, user_id="ghost-user")
    ghost = await client.get("/api/auth/session", headers=bearer(ghost_token))

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "AUTH_REQUIRED"
    assert ghost.status_code == 401
    assert ghost.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_repository_rejects_a_non_positive_limit_and_empty_aggregates(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Repository guards stay explicit for the workspace slice."""
    app, _ = workspace_client
    repository = WorkspaceRepository(app.state.database)

    with pytest.raises(ValueError):
        await repository.list_visible(user_id="any", include_all=False, limit=0)
    assert await repository.used_counts([]) == {}
    assert await repository.member_counts([]) == {}
