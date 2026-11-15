"""Cross-workspace badCaseId ownership conflicts."""

import asyncio

import httpx
from fastapi import FastAPI

from tests.ingest.helpers import (
    count_cases,
    create_ingest_workspace,
    fetch_case,
    ingest_body,
    report,
)


async def test_cross_workspace_reuse_is_rejected_and_never_moves_the_row(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A badCaseId owned by another workspace answers 409 and keeps its owner."""
    app, client = ingest_client
    owner = await create_ingest_workspace(
        app, client, name="Conflict Owner", username="owner-admin"
    )
    intruder = await create_ingest_workspace(
        app,
        client,
        name="Conflict Other",
        username="intruder-admin",
    )
    created = await report(client, owner, ingest_body(title="原始标题"))
    assert created.status_code == 201

    conflict = await report(
        client,
        intruder,
        ingest_body(title="覆盖标题", objectName="other-object", reason="另一段描述"),
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "BAD_CASE_ID_CONFLICT"
    assert await count_cases(app.state.database, intruder.workspace_id) == 0

    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    assert row["workspace_id"] == owner.workspace_id
    assert row["title"] == "原始标题"
    assert row["object_name"] == "deep-research"


async def test_conflict_wins_over_the_owner_workspace_quota(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Quota never applies to another workspace's existing id."""
    app, client = ingest_client
    owner = await create_ingest_workspace(
        app, client, name="Conflict Quota", username="quota-owner"
    )
    intruder = await create_ingest_workspace(
        app,
        client,
        name="Conflict Zero",
        quota=0,
        username="quota-intruder",
    )
    await report(client, owner, ingest_body())

    conflict = await report(client, intruder, ingest_body())

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "BAD_CASE_ID_CONFLICT"


async def test_concurrent_cross_workspace_reports_keep_one_owner(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Two workspaces racing on one id produce exactly one owner and one 409."""
    app, client = ingest_client
    first = await create_ingest_workspace(app, client, name="Race First", username="race-first")
    second = await create_ingest_workspace(app, client, name="Race Second", username="race-second")

    responses = await asyncio.gather(
        report(client, first, ingest_body()),
        report(client, second, ingest_body()),
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409]
    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    winners = [first, second]
    owner = next(item for item in winners if item.workspace_id == row["workspace_id"])
    other = next(item for item in winners if item.workspace_id != owner.workspace_id)
    assert await count_cases(app.state.database, owner.workspace_id) == 1
    assert await count_cases(app.state.database, other.workspace_id) == 0
