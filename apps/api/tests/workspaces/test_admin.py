"""Workspace CRUD, member management, and candidate search contracts."""

import httpx
import pytest
from fastapi import FastAPI

from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_bad_case,
    insert_member,
    insert_workspace,
)


async def _admin(app: FastAPI, username: str = "root") -> tuple[str, dict[str, str]]:
    """Create the global administrator and return its id and bearer header."""
    admin_id = await create_user(app.state.database, username=username, role="admin")
    return admin_id, bearer(access_token(app, user_id=admin_id, role="admin"))


def _workspace_payload(**overrides: object) -> dict[str, object]:
    """Return a minimal valid workspace create body."""
    payload: dict[str, object] = {
        "name": "Harness core",
        "mark": "HC",
        "quota": 60,
        "spaceAdminIds": [],
    }
    payload.update(overrides)
    return payload


async def test_create_workspace_is_admin_only_and_names_initial_admins(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Only the global administrator creates spaces and must name one admin."""
    app, client = workspace_client
    database = app.state.database
    member_id = await create_user(database, username="member-creator")
    initial_admin_id = await create_user(database, username="space-owner")
    member_header = bearer(access_token(app, user_id=member_id))
    _, admin_header = await _admin(app)

    denied = await client.post(
        "/api/workspaces",
        headers=member_header,
        json=_workspace_payload(spaceAdminIds=[initial_admin_id]),
    )
    created = await client.post(
        "/api/workspaces",
        headers=admin_header,
        json=_workspace_payload(spaceAdminIds=[initial_admin_id]),
    )

    assert denied.status_code == 403
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "Harness core"
    assert payload["mark"] == "HC"
    assert payload["quota"] == 60
    assert payload["used"] == 0
    assert payload["memberCount"] == 1
    assert payload["spaceAdmins"] == [
        {"id": initial_admin_id, "displayName": "space-owner"},
    ]
    assert payload["createdAt"].endswith("+08:00")

    listed = await client.get("/api/workspaces", headers=admin_header)
    assert listed.status_code == 200
    assert payload in listed.json()["items"]


async def test_create_workspace_validates_quota_admin_list_and_unique_name(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Invalid quota, empty or unknown admins, and duplicate names keep stable codes."""
    app, client = workspace_client
    database = app.state.database
    initial_admin_id = await create_user(database, username="initial-admin")
    _, admin_header = await _admin(app)

    negative_quota = await client.post(
        "/api/workspaces",
        headers=admin_header,
        json=_workspace_payload(quota=-1, spaceAdminIds=[initial_admin_id]),
    )
    no_admin = await client.post(
        "/api/workspaces",
        headers=admin_header,
        json=_workspace_payload(spaceAdminIds=[]),
    )
    unknown_admin = await client.post(
        "/api/workspaces",
        headers=admin_header,
        json=_workspace_payload(spaceAdminIds=["ghost-user"]),
    )
    first = await client.post(
        "/api/workspaces",
        headers=admin_header,
        json=_workspace_payload(spaceAdminIds=[initial_admin_id]),
    )
    duplicate = await client.post(
        "/api/workspaces",
        headers=admin_header,
        json=_workspace_payload(spaceAdminIds=[initial_admin_id]),
    )

    assert negative_quota.status_code == 422
    assert negative_quota.json()["error"]["code"] == "QUOTA_INVALID"
    assert no_admin.status_code == 422
    assert no_admin.json()["error"]["code"] == "ROLE_INVALID"
    assert unknown_admin.status_code == 422
    assert unknown_admin.json()["error"]["code"] == "ROLE_INVALID"
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "WORKSPACE_EXISTS"


async def test_update_workspace_scopes_fields_and_checks_live_usage(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Space admins may raise quota; global admins may rename; quota cannot undercut usage."""
    app, client = workspace_client
    database = app.state.database
    space_admin_id = await create_user(database, username="space-admin")
    workspace_id = await insert_workspace(database, name="Scoped", quota=10)
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=space_admin_id,
        role="space_admin",
    )
    await insert_bad_case(database, workspace_id=workspace_id, bad_case_id="bc-1")
    await insert_bad_case(database, workspace_id=workspace_id, bad_case_id="bc-2")
    space_header = bearer(access_token(app, user_id=space_admin_id))
    _, admin_header = await _admin(app)

    rename = await client.put(
        f"/api/workspaces/{workspace_id}",
        headers=space_header,
        json={"name": "Renamed"},
    )
    lowered = await client.put(
        f"/api/workspaces/{workspace_id}",
        headers=space_header,
        json={"quota": 1},
    )
    raised = await client.put(
        f"/api/workspaces/{workspace_id}",
        headers=space_header,
        json={"quota": 12},
    )
    renamed = await client.put(
        f"/api/workspaces/{workspace_id}",
        headers=admin_header,
        json={"name": "Renamed", "mark": "R"},
    )

    assert rename.status_code == 403
    assert rename.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert lowered.status_code == 422
    assert lowered.json()["error"]["code"] == "QUOTA_INVALID"
    assert lowered.json()["error"]["details"] == {"quota": 1, "used": 2}
    assert raised.status_code == 200
    assert raised.json()["quota"] == 12
    assert raised.json()["used"] == 2
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["mark"] == "R"


async def test_update_workspace_rejects_duplicate_name_and_missing_space(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """DB uniqueness maps to WORKSPACE_EXISTS and invisible spaces stay 404."""
    app, client = workspace_client
    database = app.state.database
    await insert_workspace(database, name="Taken")
    target = await insert_workspace(database, name="Target")
    _, admin_header = await _admin(app)

    duplicate = await client.put(
        f"/api/workspaces/{target}",
        headers=admin_header,
        json={"name": "Taken"},
    )
    missing = await client.put(
        "/api/workspaces/ws-missing",
        headers=admin_header,
        json={"quota": 1},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "WORKSPACE_EXISTS"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_workspace_list_is_scoped_and_returns_management_fields(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Members list only joined spaces while the global admin lists every space."""
    app, client = workspace_client
    database = app.state.database
    member_id = await create_user(database, username="member-list")
    admin_id, admin_header = await _admin(app)
    joined = await insert_workspace(database, name="Joined", quota=7)
    hidden = await insert_workspace(database, name="Hidden")
    await insert_member(database, workspace_id=joined, user_id=member_id, role="viewer")
    await insert_member(database, workspace_id=joined, user_id=admin_id, role="space_admin")
    member_header = bearer(access_token(app, user_id=member_id))

    member_list = await client.get("/api/workspaces", headers=member_header)
    admin_list = await client.get("/api/workspaces", headers=admin_header)

    assert member_list.status_code == 200
    assert [item["id"] for item in member_list.json()["items"]] == [joined]
    assert member_list.json()["items"][0]["spaceAdmins"] == [
        {"id": admin_id, "displayName": "root"},
    ]
    assert member_list.json()["items"][0]["memberCount"] == 2
    admin_ids = [item["id"] for item in admin_list.json()["items"]]
    assert {joined, hidden, "ws-default"} <= set(admin_ids)


async def test_members_are_listed_by_role_then_join_time(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Viewers can read the member table in the documented order."""
    app, client = workspace_client
    database = app.state.database
    reader_id = await create_user(database, username="member-reader")
    admin_id = await create_user(database, username="member-space-admin")
    viewer_id = await create_user(database, username="member-viewer")
    workspace_id = await insert_workspace(database, name="Ordered")
    await insert_member(database, workspace_id=workspace_id, user_id=reader_id, role="member")
    await insert_member(database, workspace_id=workspace_id, user_id=viewer_id, role="viewer")
    await insert_member(database, workspace_id=workspace_id, user_id=admin_id, role="space_admin")
    header = bearer(access_token(app, user_id=reader_id))
    viewer_header = bearer(access_token(app, user_id=viewer_id))

    response = await client.get(
        f"/api/workspaces/{workspace_id}/members",
        headers=header,
    )
    viewer_response = await client.get(
        f"/api/workspaces/{workspace_id}/members",
        headers=viewer_header,
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["role"] for item in items] == ["space_admin", "member", "viewer"]
    assert viewer_response.status_code == 403
    assert viewer_response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert items[0]["workspaceId"] == workspace_id
    assert items[0]["userId"] == admin_id
    assert items[0]["username"] == "member-space-admin"
    assert items[0]["displayName"] == "member-space-admin"
    assert items[0]["joinedAt"].endswith("+08:00")


async def test_member_candidates_search_non_members_without_the_directory(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Search is limited, excludes existing members, and returns no admin directory page."""
    app, client = workspace_client
    database = app.state.database
    space_admin_id = await create_user(database, username="search-admin")
    await create_user(database, username="candidate-one")
    await create_user(database, username="candidate-two")
    member_id = await create_user(database, username="candidate-member")
    workspace_id = await insert_workspace(database, name="Search")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=space_admin_id,
        role="space_admin",
    )
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=member_id,
        role="member",
    )
    header = bearer(access_token(app, user_id=space_admin_id))

    response = await client.get(
        f"/api/workspaces/{workspace_id}/member-candidates",
        headers=header,
        params={"q": "candidate", "limit": 1},
    )
    blank = await client.get(
        f"/api/workspaces/{workspace_id}/member-candidates",
        headers=header,
        params={"q": ""},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] != member_id
    assert items[0]["username"].startswith("candidate-")
    assert items[0]["active"] is True
    assert blank.status_code == 200
    assert blank.json()["items"] == []


async def test_space_admin_cannot_grant_or_touch_space_admin_rows(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Space admins stay inside member/viewer and never edit existing space admins."""
    app, client = workspace_client
    database = app.state.database
    space_admin_id = await create_user(database, username="limited-admin")
    other_admin_id = await create_user(database, username="peer-admin")
    member_id = await create_user(database, username="new-member")
    workspace_id = await insert_workspace(database, name="Limited")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=space_admin_id,
        role="space_admin",
    )
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=other_admin_id,
        role="space_admin",
    )
    header = bearer(access_token(app, user_id=space_admin_id))

    grant_admin = await client.post(
        f"/api/workspaces/{workspace_id}/members",
        headers=header,
        json={"userId": member_id, "role": "space_admin"},
    )
    update_admin = await client.put(
        f"/api/workspaces/{workspace_id}/members/{other_admin_id}",
        headers=header,
        json={"role": "member"},
    )
    remove_admin = await client.delete(
        f"/api/workspaces/{workspace_id}/members/{other_admin_id}",
        headers=header,
    )
    added = await client.post(
        f"/api/workspaces/{workspace_id}/members",
        headers=header,
        json={"userId": member_id, "role": "viewer"},
    )
    duplicate = await client.post(
        f"/api/workspaces/{workspace_id}/members",
        headers=header,
        json={"userId": member_id, "role": "member"},
    )

    assert grant_admin.status_code == 403
    assert grant_admin.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert update_admin.status_code == 409
    assert update_admin.json()["error"]["code"] == "ROLE_LOCKED"
    assert remove_admin.status_code == 409
    assert remove_admin.json()["error"]["code"] == "ROLE_LOCKED"
    assert added.status_code == 201
    assert added.json()["role"] == "viewer"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "MEMBER_EXISTS"


async def test_last_space_admin_cannot_be_demoted_or_removed(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Every workspace keeps at least one space admin, even when a global admin tries."""
    app, client = workspace_client
    database = app.state.database
    only_admin_id = await create_user(database, username="only-admin")
    workspace_id = await insert_workspace(database, name="KeepAdmin")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=only_admin_id,
        role="space_admin",
    )
    _, admin_header = await _admin(app)

    demote = await client.put(
        f"/api/workspaces/{workspace_id}/members/{only_admin_id}",
        headers=admin_header,
        json={"role": "member"},
    )
    remove = await client.delete(
        f"/api/workspaces/{workspace_id}/members/{only_admin_id}",
        headers=admin_header,
    )

    assert demote.status_code == 409
    assert demote.json()["error"]["code"] == "ROLE_LOCKED"
    assert remove.status_code == 409
    assert remove.json()["error"]["code"] == "ROLE_LOCKED"
    members = await client.get(
        f"/api/workspaces/{workspace_id}/members",
        headers=admin_header,
    )
    assert [item["userId"] for item in members.json()["items"]] == [only_admin_id]


async def test_global_admin_can_appoint_self_and_grant_space_admin(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Self-appointment is global-admin only and idempotent; that admin may grant admins."""
    app, client = workspace_client
    database = app.state.database
    admin_id, admin_header = await _admin(app)
    space_admin_id = await create_user(database, username="not-global")
    workspace_id = await insert_workspace(database, name="Appoint")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=space_admin_id,
        role="space_admin",
    )
    space_header = bearer(access_token(app, user_id=space_admin_id))

    denied = await client.post(
        f"/api/workspaces/{workspace_id}/members/self-admin",
        headers=space_header,
    )
    appointed = await client.post(
        f"/api/workspaces/{workspace_id}/members/self-admin",
        headers=admin_header,
    )
    again = await client.post(
        f"/api/workspaces/{workspace_id}/members/self-admin",
        headers=admin_header,
    )
    granted = await client.post(
        f"/api/workspaces/{workspace_id}/members",
        headers=admin_header,
        json={"userId": space_admin_id, "role": "space_admin"},
    )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert appointed.status_code == 200
    assert appointed.json()["userId"] == admin_id
    assert appointed.json()["role"] == "space_admin"
    assert again.status_code == 200
    assert granted.status_code == 409
    assert granted.json()["error"]["code"] == "MEMBER_EXISTS"


async def test_member_update_and_remove_require_an_existing_member(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Unknown member ids and unknown space roles fail with stable codes."""
    app, client = workspace_client
    database = app.state.database
    missing_user_id = await create_user(database, username="not-member")
    workspace_id = await insert_workspace(database, name="Membership")
    _, admin_header = await _admin(app)

    update = await client.put(
        f"/api/workspaces/{workspace_id}/members/{missing_user_id}",
        headers=admin_header,
        json={"role": "member"},
    )
    remove = await client.delete(
        f"/api/workspaces/{workspace_id}/members/{missing_user_id}",
        headers=admin_header,
    )
    invalid_role = await client.put(
        f"/api/workspaces/{workspace_id}/members/{missing_user_id}",
        headers=admin_header,
        json={"role": "owner"},
    )

    assert update.status_code == 404
    assert update.json()["error"]["code"] == "MEMBER_NOT_FOUND"
    assert remove.status_code == 404
    assert remove.json()["error"]["code"] == "MEMBER_NOT_FOUND"
    assert invalid_role.status_code == 422
    assert invalid_role.json()["error"]["code"] == "VALIDATION_INVALID"


async def test_global_admin_updates_and_removes_a_non_last_space_admin(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A global admin may demote and remove one admin while another remains."""
    app, client = workspace_client
    database = app.state.database
    keep_id = await create_user(database, username="keep-admin")
    change_id = await create_user(database, username="change-admin")
    workspace_id = await insert_workspace(database, name="AdminMoves")
    await insert_member(database, workspace_id=workspace_id, user_id=keep_id, role="space_admin")
    await insert_member(database, workspace_id=workspace_id, user_id=change_id, role="space_admin")
    _, admin_header = await _admin(app)

    empty_update = await client.put(
        f"/api/workspaces/{workspace_id}",
        headers=admin_header,
        json={},
    )
    demoted = await client.put(
        f"/api/workspaces/{workspace_id}/members/{change_id}",
        headers=admin_header,
        json={"role": "member"},
    )
    removed = await client.delete(
        f"/api/workspaces/{workspace_id}/members/{change_id}",
        headers=admin_header,
    )
    members = await client.get(
        f"/api/workspaces/{workspace_id}/members",
        headers=admin_header,
    )

    assert empty_update.status_code == 200
    assert empty_update.json()["name"] == "AdminMoves"
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "member"
    assert removed.status_code == 204
    assert [item["userId"] for item in members.json()["items"]] == [keep_id]


async def test_add_member_requires_an_existing_user_and_preserves_grants(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Unknown users and a space admin promoting a plain member fail closed."""
    app, client = workspace_client
    database = app.state.database
    space_admin_id = await create_user(database, username="grant-admin")
    member_id = await create_user(database, username="grant-member")
    workspace_id = await insert_workspace(database, name="Grant")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=space_admin_id,
        role="space_admin",
    )
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=member_id,
        role="member",
    )
    header = bearer(access_token(app, user_id=space_admin_id))

    unknown = await client.post(
        f"/api/workspaces/{workspace_id}/members",
        headers=header,
        json={"userId": "ghost-user", "role": "member"},
    )
    promote = await client.put(
        f"/api/workspaces/{workspace_id}/members/{member_id}",
        headers=header,
        json={"role": "space_admin"},
    )

    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "ROLE_INVALID"
    assert promote.status_code == 403
    assert promote.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


async def test_workspace_list_is_empty_for_an_unjoined_member(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A member with no membership rows still gets a complete empty list."""
    app, client = workspace_client
    database = app.state.database
    member_id = await create_user(database, username="no-spaces")
    header = bearer(access_token(app, user_id=member_id))

    response = await client.get("/api/workspaces", headers=header)

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
async def test_invisible_workspaces_never_leak_membership(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
    method: str,
) -> None:
    """Every management route returns the uniform invisible-space 404 for outsiders."""
    app, client = workspace_client
    database = app.state.database
    outsider_id = await create_user(database, username="outsider")
    workspace_id = await insert_workspace(database, name="Private")
    header = bearer(access_token(app, user_id=outsider_id))
    paths = {
        "get": f"/api/workspaces/{workspace_id}/members",
        "post": f"/api/workspaces/{workspace_id}/members",
        "put": f"/api/workspaces/{workspace_id}/members/ghost",
        "delete": f"/api/workspaces/{workspace_id}/members/ghost",
    }
    if method == "post":
        response = await client.post(
            paths[method],
            headers=header,
            json={"userId": "ghost", "role": "member"},
        )
    else:
        response = await getattr(client, method)(paths[method], headers=header)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
