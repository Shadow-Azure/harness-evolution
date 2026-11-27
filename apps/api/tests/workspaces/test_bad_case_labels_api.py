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


async def _insert_catalog_cases(app: FastAPI, labels: list[str | None]) -> None:
    """Insert one catalog case per entry so repeated labels produce counts."""
    for index, label in enumerate(labels):
        await _insert_catalog_case(app, case_id=f"case-{index}", label=label)


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

    missing = await client.put(
        f"/api/workspaces/{workspace_id}/bad-case-labels",
        headers=headers,
        json={},
    )
    assert missing.status_code == 422


async def test_suggestions_rank_distinct_catalog_labels_by_count_then_name(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Non-null labels are grouped, counted, and ordered without duplicates."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="Suggestion ranking")
    viewer_id = await create_user(database, username="suggestion-viewer")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=viewer_id,
        role="viewer",
    )
    headers = bearer(access_token(app, user_id=viewer_id))
    await _insert_catalog_cases(
        app,
        ["review", "review", "code-review", "code-review", "tool-use", None],
    )

    response = await client.get(
        f"/api/workspaces/{workspace_id}/bad-case-labels/suggestions",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"label": "code-review", "badCaseCount": 2},
            {"label": "review", "badCaseCount": 2},
            {"label": "tool-use", "badCaseCount": 1},
        ],
    }


async def test_suggestions_treat_like_metacharacters_in_prefix_as_literals(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Percent, underscore, and backslash only match their literal characters."""
    app, client = workspace_client
    workspace_id = await insert_workspace(app.state.database, name="Suggestion escaping")
    admin_id = await create_user(
        app.state.database,
        username="suggestion-escaping-admin",
        role="admin",
    )
    headers = bearer(access_token(app, user_id=admin_id, role="admin"))
    await _insert_catalog_cases(
        app,
        ["review", "review", "review-ui", "100%done", "a_b", "axb", "c\\d"],
    )
    url = f"/api/workspaces/{workspace_id}/bad-case-labels/suggestions"

    prefix = await client.get(url, headers=headers, params={"q": "review"})
    percent = await client.get(url, headers=headers, params={"q": "100%"})
    underscore = await client.get(url, headers=headers, params={"q": "a_"})
    backslash = await client.get(url, headers=headers, params={"q": "c\\"})

    assert prefix.json() == {
        "items": [
            {"label": "review", "badCaseCount": 2},
            {"label": "review-ui", "badCaseCount": 1},
        ],
    }
    assert percent.json() == {"items": [{"label": "100%done", "badCaseCount": 1}]}
    assert underscore.json() == {"items": [{"label": "a_b", "badCaseCount": 1}]}
    assert backslash.json() == {"items": [{"label": "c\\d", "badCaseCount": 1}]}


async def test_suggestions_apply_limit_and_validate_query_parameters(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The limit caps the payload and out-of-range values fail validation."""
    app, client = workspace_client
    workspace_id = await insert_workspace(app.state.database, name="Suggestion limits")
    admin_id = await create_user(
        app.state.database,
        username="suggestion-limits-admin",
        role="admin",
    )
    headers = bearer(access_token(app, user_id=admin_id, role="admin"))
    await _insert_catalog_cases(app, ["review", "review", "tool-use", "code-review"])
    url = f"/api/workspaces/{workspace_id}/bad-case-labels/suggestions"

    limited = await client.get(url, headers=headers, params={"limit": 1})
    zero = await client.get(url, headers=headers, params={"limit": 0})
    oversize = await client.get(url, headers=headers, params={"limit": 51})
    textual = await client.get(url, headers=headers, params={"limit": "many"})
    long_prefix = await client.get(url, headers=headers, params={"q": "x" * 129})

    assert limited.json() == {"items": [{"label": "review", "badCaseCount": 2}]}
    for response in (zero, oversize, textual, long_prefix):
        assert response.status_code == 422


async def test_suggestions_with_empty_query_return_most_common_labels(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """An empty query returns the globally most frequent labels up to the limit."""
    app, client = workspace_client
    workspace_id = await insert_workspace(app.state.database, name="Suggestion top")
    admin_id = await create_user(
        app.state.database,
        username="suggestion-top-admin",
        role="admin",
    )
    headers = bearer(access_token(app, user_id=admin_id, role="admin"))
    await _insert_catalog_cases(
        app,
        ["alpha", "alpha", "beta", "beta", "beta", "gamma"],
    )
    url = f"/api/workspaces/{workspace_id}/bad-case-labels/suggestions"

    response = await client.get(url, headers=headers, params={"q": "", "limit": 2})

    assert response.json() == {
        "items": [
            {"label": "beta", "badCaseCount": 3},
            {"label": "alpha", "badCaseCount": 2},
        ],
    }


async def test_suggestions_require_authentication_and_an_accessible_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Anonymous callers get 401, unknown workspaces get the shared 404."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="Suggestion auth")
    viewer_id = await create_user(database, username="suggestion-auth-viewer")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=viewer_id,
        role="viewer",
    )
    headers = bearer(access_token(app, user_id=viewer_id))

    anonymous = await client.get(
        f"/api/workspaces/{workspace_id}/bad-case-labels/suggestions",
    )
    missing = await client.get(
        "/api/workspaces/ws-does-not-exist/bad-case-labels/suggestions",
        headers=headers,
    )
    readable = await client.get(
        f"/api/workspaces/{workspace_id}/bad-case-labels/suggestions",
        headers=headers,
    )

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "AUTH_REQUIRED"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert readable.status_code == 200
    assert readable.json() == {"items": []}
