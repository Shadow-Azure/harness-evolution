"""Cross-stack contract: one catalog case may be shared by many workspaces.

These scenarios are impossible under the legacy ``bad_cases.workspace_id``
visibility model, so they pin the association boundary that every workspace
read path now uses. Visibility is asserted through the overview summary
``totals.badCases``, which is association-driven and independent of whether
the case's root Session has normalized yet.
"""

import httpx
from fastapi import FastAPI
from sqlalchemy import insert

from app.db.models.domain import bad_cases
from app.utils.time import now_shanghai
from tests.workspaces.helpers import (
    access_token,
    bearer,
    insert_workspace,
)


async def _insert_catalog_case(
    app: FastAPI,
    *,
    case_id: str,
    label: str,
) -> None:
    """Insert one canonical public case whose validated label is already projected."""
    now = now_shanghai()
    async with app.state.database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=case_id,
                workspace_id="ws-default",
                bad_case_session_id=f"session-{case_id}",
                bad_case_type="self",
                object_name="shared-object",
                object_type="skill",
                title=f"Case {case_id}",
                bad_case_description="Shared catalog case.",
                meta_data={"label": label},
                catalog_label=label,
                created_at=now,
                updated_at=now,
            ),
        )


async def _configure(
    app: FastAPI,
    client: httpx.AsyncClient,
    wid: str,
    items: list[str],
) -> None:
    response = await client.put(
        f"/api/workspaces/{wid}/bad-case-labels",
        headers=bearer(access_token(app, user_id="admin", role="admin")),
        json={"items": items},
    )
    assert response.status_code == 200


async def _bad_case_total(
    client: httpx.AsyncClient,
    wid: str,
    admin: dict[str, str],
) -> int:
    """Return the association-driven bad-case total for one workspace."""
    summary = await client.get(
        f"/api/workspaces/{wid}/overview/summary",
        headers=admin,
    )
    assert summary.status_code == 200, wid
    return int(summary.json()["totals"]["badCases"])


async def test_shared_catalog_case_is_readable_by_every_matching_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """One canonical row fans out to both configured spaces; a third sees nothing."""
    app, client = workspace_client
    database = app.state.database
    first = await insert_workspace(database, name="shared-first")
    second = await insert_workspace(database, name="shared-second")
    outsider = await insert_workspace(database, name="shared-outsider")
    admin = bearer(access_token(app, user_id="admin", role="admin"))

    await _insert_catalog_case(app, case_id="case-shared", label="shared")
    await _configure(app, client, first, ["shared"])
    await _configure(app, client, second, ["shared"])

    assert await _bad_case_total(client, first, admin) == 1
    assert await _bad_case_total(client, second, admin) == 1
    assert await _bad_case_total(client, outsider, admin) == 0

    hidden = await client.get(
        f"/api/workspaces/{outsider}/bad-cases/case-shared",
        headers=admin,
    )
    assert hidden.status_code == 404


async def test_removing_label_revokes_catalog_visibility_only_for_that_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Clearing one workspace's rule removes its association but not the sibling's."""
    app, client = workspace_client
    database = app.state.database
    first = await insert_workspace(database, name="revoke-first")
    second = await insert_workspace(database, name="revoke-second")
    admin = bearer(access_token(app, user_id="admin", role="admin"))

    await _insert_catalog_case(app, case_id="case-revoke", label="shared")
    await _configure(app, client, first, ["shared"])
    await _configure(app, client, second, ["shared"])
    await _configure(app, client, second, [])

    assert await _bad_case_total(client, first, admin) == 1
    assert await _bad_case_total(client, second, admin) == 0
