"""Permission matrix for the reusable workspace role dependency."""

import httpx
import pytest
from fastapi import FastAPI

from app.service.workspaces.roles import WorkspaceMemberRole, role_at_least
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)

Minimum = WorkspaceMemberRole
PROBE_PATH: dict[str, str] = {
    "viewer": "viewer",
    "member": "member",
    "space_admin": "space-admin",
}


@pytest.mark.parametrize(
    ("identity_role", "minimum", "expected_status", "expected_role"),
    [
        ("space_admin", "viewer", 200, "space_admin"),
        ("space_admin", "member", 200, "space_admin"),
        ("space_admin", "space_admin", 200, "space_admin"),
        ("member", "viewer", 200, "member"),
        ("member", "member", 200, "member"),
        ("member", "space_admin", 403, None),
        ("viewer", "viewer", 200, "viewer"),
        ("viewer", "member", 403, None),
        ("viewer", "space_admin", 403, None),
    ],
)
async def test_membership_role_matrix(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
    identity_role: str,
    minimum: Minimum,
    expected_status: int,
    expected_role: str | None,
) -> None:
    """Every stored role either meets the minimum or answers the same 403."""
    app, client = workspace_client
    database = app.state.database
    user_id = await create_user(
        database,
        username=f"{identity_role}-{minimum}",
        role="member",
    )
    workspace_id = await insert_workspace(database, name=f"ws-{identity_role}-{minimum}")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=user_id,
        role=identity_role,
    )
    token = access_token(app, user_id=user_id)

    response = await client.get(
        f"/api/test/workspaces/{workspace_id}/{PROBE_PATH[minimum]}",
        headers=bearer(token),
    )

    assert response.status_code == expected_status
    if expected_role is None:
        assert response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    else:
        assert response.json() == {"role": expected_role}


@pytest.mark.parametrize("minimum", ["viewer", "member", "space_admin"])
async def test_non_members_cannot_see_a_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
    minimum: Minimum,
) -> None:
    """A visible-but-unjoined workspace answers 404, not 403, at every level."""
    app, client = workspace_client
    database = app.state.database
    user_id = await create_user(database, username=f"outsider-{minimum}")
    workspace_id = await insert_workspace(database, name=f"hidden-from-{minimum}")
    token = access_token(app, user_id=user_id)

    response = await client.get(
        f"/api/test/workspaces/{workspace_id}/{PROBE_PATH[minimum]}",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_missing_workspace_and_unknown_stored_role_fail_closed(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A missing workspace is 404 and an out-of-contract role cannot pass."""
    app, client = workspace_client
    database = app.state.database
    user_id = await create_user(database, username="role-probe")
    workspace_id = await insert_workspace(database, name="ws-unknown-role")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=user_id,
        role="owner",
    )
    token = access_token(app, user_id=user_id)

    unknown_role = await client.get(
        f"/api/test/workspaces/{workspace_id}/viewer",
        headers=bearer(token),
    )
    missing = await client.get(
        "/api/test/workspaces/ws-does-not-exist/viewer",
        headers=bearer(token),
    )
    unauthenticated = await client.get(
        f"/api/test/workspaces/{workspace_id}/viewer",
    )

    assert unknown_role.status_code == 403
    assert unknown_role.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert unauthenticated.status_code == 401


@pytest.mark.parametrize("minimum", ["viewer", "member", "space_admin"])
async def test_global_admin_passes_through_without_a_membership_row(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
    minimum: Minimum,
) -> None:
    """The global administrator reaches every existing workspace at any level."""
    app, client = workspace_client
    database = app.state.database
    admin_id = await create_user(database, username=f"admin-{minimum}", role="admin")
    workspace_id = await insert_workspace(database, name=f"admin-space-{minimum}")
    token = access_token(app, user_id=admin_id, role="admin")

    response = await client.get(
        f"/api/test/workspaces/{workspace_id}/{PROBE_PATH[minimum]}",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.json() == {"role": "global_admin"}


async def test_global_admin_still_gets_404_for_a_missing_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Pass-through does not invent workspaces that were never created."""
    app, client = workspace_client
    admin_id = await create_user(app.state.database, username="admin-missing", role="admin")
    token = access_token(app, user_id=admin_id, role="admin")

    response = await client.get(
        "/api/test/workspaces/ws-missing/viewer",
        headers=bearer(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_role_rank_is_a_closed_ordered_set() -> None:
    """The comparison helper orders viewer below member below space admin."""
    assert role_at_least("viewer", "viewer")
    assert not role_at_least("viewer", "member")
    assert role_at_least("member", "viewer")
    assert not role_at_least("member", "space_admin")
    assert role_at_least("space_admin", "space_admin")
    assert not role_at_least("global_admin", "viewer")
    assert not role_at_least("owner", "viewer")
