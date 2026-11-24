"""Workspace badcase label configuration HTTP contract."""

import httpx
from fastapi import FastAPI
from sqlalchemy import insert

from app.db.models.domain import bad_cases, workspace_bad_cases
from app.utils.time import now_shanghai
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)


async def _insert_catalog_case(
    app: FastAPI,
    *,
    case_id: str,
    label: str | None,
) -> None:
    """Insert one canonical public case with its validated label projection."""
    now = now_shanghai()
    async with app.state.database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=case_id,
                workspace_id="ws-default",
                bad_case_session_id=f"session-{case_id}",
                bad_case_type="self",
                object_name="example-object",
                object_type="skill",
                title=f"Case {case_id}",
                bad_case_description="Public catalog case.",
                meta_data={"label": label} if label is not None else {},
                catalog_label=label,
                created_at=now,
                updated_at=now,
            ),
        )


async def test_viewers_read_labels_but_only_space_admins_replace_them(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The management resource follows the viewer/read and space-admin/write boundary."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="Label access")
    viewer_id = await create_user(database, username="label-viewer")
    member_id = await create_user(database, username="label-member")
    admin_id = await create_user(database, username="label-admin")
    outsider_id = await create_user(database, username="label-outsider")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=viewer_id,
        role="viewer",
    )
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=member_id,
        role="member",
    )
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=admin_id,
        role="space_admin",
    )
    viewer_header = bearer(access_token(app, user_id=viewer_id))
    member_header = bearer(access_token(app, user_id=member_id))
    admin_header = bearer(access_token(app, user_id=admin_id))
    outsider_header = bearer(access_token(app, user_id=outsider_id))

    initial = await client.get(
        f"/api/workspaces/{workspace_id}/bad-case-labels",
        headers=viewer_header,
    )
    denied = await client.put(
        f"/api/workspaces/{workspace_id}/bad-case-labels",
        headers=member_header,
        json={"items": ["review"]},
    )
    hidden = await client.get(
        f"/api/workspaces/{workspace_id}/bad-case-labels",
        headers=outsider_header,
    )
    saved = await client.put(
        f"/api/workspaces/{workspace_id}/bad-case-labels",
        headers=admin_header,
        json={"items": ["tool-use", "review"]},
    )

    assert initial.status_code == 200
    assert initial.json() == {"items": [], "assignedBadCaseCount": 0}
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert saved.status_code == 200
    assert saved.json() == {
        "items": ["review", "tool-use"],
        "assignedBadCaseCount": 0,
    }


async def test_replacement_reassigns_history_to_every_matching_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Exact replacement fans out shared labels and preserves direct ownership."""
    app, client = workspace_client
    database = app.state.database
    first_workspace = await insert_workspace(database, name="Label first")
    second_workspace = await insert_workspace(database, name="Label second")
    admin_id = await create_user(database, username="routing-admin", role="admin")
    headers = bearer(access_token(app, user_id=admin_id, role="admin"))
    await _insert_catalog_case(app, case_id="case-review", label="review")
    await _insert_catalog_case(app, case_id="case-tools", label="tool-use")
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(workspace_bad_cases).values(
                workspace_id=first_workspace,
                bad_case_id="case-review",
                assignment_source="direct_ingest",
                label=None,
                assigned_at=now,
            ),
        )

    first = await client.put(
        f"/api/workspaces/{first_workspace}/bad-case-labels",
        headers=headers,
        json={"items": ["tool-use", "review"]},
    )
    second = await client.put(
        f"/api/workspaces/{second_workspace}/bad-case-labels",
        headers=headers,
        json={"items": ["review"]},
    )
    replaced = await client.put(
        f"/api/workspaces/{first_workspace}/bad-case-labels",
        headers=headers,
        json={"items": ["tool-use"]},
    )

    assert first.json() == {
        "items": ["review", "tool-use"],
        "assignedBadCaseCount": 2,
    }
    assert second.json() == {
        "items": ["review"],
        "assignedBadCaseCount": 1,
    }
    assert replaced.json() == {
        "items": ["tool-use"],
        "assignedBadCaseCount": 2,
    }
    listed = await client.get("/api/workspaces", headers=headers)
    usage = {item["id"]: item["used"] for item in listed.json()["items"]}
    assert usage[first_workspace] == 2
    assert usage[second_workspace] == 1


async def test_label_request_rejects_duplicates_whitespace_and_oversize(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Ambiguous labels never enter the exact-match rule set."""
    app, client = workspace_client
    workspace_id = await insert_workspace(app.state.database, name="Label validation")
    admin_id = await create_user(
        app.state.database,
        username="validation-admin",
        role="admin",
    )
    headers = bearer(access_token(app, user_id=admin_id, role="admin"))

    for items in (["review", "review"], [" review"], ["x" * 129], [""]):
        response = await client.put(
            f"/api/workspaces/{workspace_id}/bad-case-labels",
            headers=headers,
            json={"items": items},
        )
        assert response.status_code == 422
