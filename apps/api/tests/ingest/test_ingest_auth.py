"""Workspace-credential authentication and authorization boundary."""

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.db.crud.workspaces import WorkspaceRepository
from app.db.models.workspace import workspace_ingest_credentials
from app.utils.time import now_shanghai
from tests.ingest.helpers import (
    count_cases,
    create_ingest_workspace,
    ingest_body,
    report,
)
from tests.workspaces.helpers import bearer


async def _credential_id(app: FastAPI, workspace_id: str) -> str:
    """Return the single minted credential id for a test workspace."""
    async with app.state.database.session() as session:
        return str(
            (
                await session.execute(
                    select(workspace_ingest_credentials.c.id).where(
                        workspace_ingest_credentials.c.workspace_id == workspace_id,
                    ),
                )
            ).scalar_one(),
        )


def _missing_credential() -> str:
    """Return a syntactically plausible but unminted workspace credential."""
    return "whk_" + "never-minted"


async def test_credential_is_required_for_every_ingest_request(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Missing, malformed, and unnamespaced bearer values all answer 401."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest 401")

    missing = await client.post(
        f"/api/workspaces/{workspace.workspace_id}/bad-cases",
        json=ingest_body(),
    )
    unknown = await client.post(
        f"/api/workspaces/{workspace.workspace_id}/bad-cases",
        headers=bearer(_missing_credential()),
        json=ingest_body(),
    )
    unnamespaced = await client.post(
        f"/api/workspaces/{workspace.workspace_id}/bad-cases",
        headers=bearer("not-a-workspace-token"),
        json=ingest_body(),
    )
    wrong_scheme = await client.post(
        f"/api/workspaces/{workspace.workspace_id}/bad-cases",
        headers={"Authorization": f"Basic {workspace.credential}"},
        json=ingest_body(),
    )

    for response in (missing, unknown, unnamespaced, wrong_scheme):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "CREDENTIAL_INVALID"
    assert await count_cases(app.state.database, workspace.workspace_id) == 0


async def test_jwt_access_token_cannot_ingest(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A valid browser session token is not a workspace credential."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Jwt")

    response = await client.post(
        f"/api/workspaces/{workspace.workspace_id}/bad-cases",
        headers=workspace.admin_authorization,
        json=ingest_body(),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "CREDENTIAL_INVALID"


async def test_revoked_credential_cannot_ingest(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Revocation applies to the next request without touching stored cases."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Revoked")
    credential_id = await _credential_id(app, workspace.workspace_id)
    accepted = await report(client, workspace, ingest_body())
    revoked = await client.delete(
        f"/api/workspaces/{workspace.workspace_id}/credentials/{credential_id}",
        headers=workspace.admin_authorization,
    )
    rejected = await report(client, workspace, ingest_body(badCaseId="BC-HC-022"))

    assert accepted.status_code == 201
    assert revoked.status_code == 204
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "CREDENTIAL_INVALID"
    assert await count_cases(app.state.database, workspace.workspace_id) == 1


async def test_credential_for_another_workspace_is_forbidden(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A valid credential cannot write into a different workspace."""
    app, client = ingest_client
    first = await create_ingest_workspace(app, client, name="Ingest Own", username="own-admin")
    second = await create_ingest_workspace(app, client, name="Ingest Other", username="other-admin")

    response = await report(client, first, ingest_body(), workspace_id=second.workspace_id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert await count_cases(app.state.database, first.workspace_id) == 0
    assert await count_cases(app.state.database, second.workspace_id) == 0


async def test_unknown_workspace_is_not_found_after_credential_validation(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A missing path workspace is 404; a missing credential stays 401."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest 404")

    missing_workspace = await report(
        client,
        workspace,
        ingest_body(),
        workspace_id="ws-does-not-exist",
    )
    unauthenticated = await client.post(
        "/api/workspaces/ws-does-not-exist/bad-cases",
        json=ingest_body(),
    )

    assert missing_workspace.status_code == 404
    assert missing_workspace.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "CREDENTIAL_INVALID"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/workspaces"),
        ("GET", "/api/workspaces/{wid}"),
        ("GET", "/api/workspaces/{wid}/credentials"),
        ("POST", "/api/workspaces/{wid}/credentials"),
        ("GET", "/api/workspaces/{wid}/sessions"),
        ("GET", "/api/sessions"),
        ("GET", "/api/acquisition/status"),
        ("POST", "/api/workspaces/{wid}/bad-cases/"),
    ],
)
async def test_workspace_credential_is_rejected_outside_the_ingest_route(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
    method: str,
    path: str,
) -> None:
    """The middleware exemption covers exactly one POST route and nothing else."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Scope")
    resolved = path.format(wid=workspace.workspace_id)

    response = await client.request(method, resolved, headers=workspace.authorization)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_admin_jwt_still_works_where_the_jwt_middleware_applies(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The exemption does not weaken adjacent JWT-protected routes."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Jwt Elsewhere")

    response = await client.get(
        f"/api/workspaces/{workspace.workspace_id}/credentials",
        headers=workspace.admin_authorization,
    )

    assert response.status_code == 200


async def test_ingest_marks_the_credential_as_used(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A successful report records a diagnostic last-used timestamp."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Touch Api")
    credential_id = await _credential_id(app, workspace.workspace_id)

    response = await report(client, workspace, ingest_body())

    assert response.status_code == 201
    listed = await client.get(
        f"/api/workspaces/{workspace.workspace_id}/credentials",
        headers=workspace.admin_authorization,
    )
    item = listed.json()["items"][0]
    assert item["id"] == credential_id
    assert item["lastUsedAt"] is not None


async def test_last_used_writes_are_throttled_to_one_window(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The credential touch is a diagnostic write, not a per-report counter."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Throttle")
    credential_id = await _credential_id(app, workspace.workspace_id)
    repository = WorkspaceRepository(app.state.database)
    now = now_shanghai().replace(microsecond=0)

    first = await repository.touch_credential(
        credential_id,
        now=now,
        not_before=now - timedelta(seconds=60),
    )
    throttled = await repository.touch_credential(
        credential_id,
        now=now + timedelta(seconds=30),
        not_before=now - timedelta(seconds=30),
    )
    credential = await repository.get_credential(workspace.workspace_id, credential_id)
    later = await repository.touch_credential(
        credential_id,
        now=now + timedelta(seconds=61),
        not_before=now + timedelta(seconds=1),
    )

    assert first is True
    assert throttled is False
    assert later is True
    assert credential is not None
    assert credential.last_used_at == now
