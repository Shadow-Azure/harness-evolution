"""Workspace quota enforcement, idempotent accounting, and concurrency."""

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


async def test_quota_exceeded_reports_details_and_keeps_old_rows(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A new id beyond the quota answers 409 and never deletes earlier cases."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Quota Full", quota=1)
    first = await report(client, workspace, ingest_body())
    refused = await report(client, workspace, ingest_body(badCaseId="BC-HC-022"))

    assert first.status_code == 201
    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "QUOTA_EXCEEDED"
    assert error["details"] == {"quota": 1, "used": 1}
    assert await count_cases(app.state.database, workspace.workspace_id) == 1
    assert await fetch_case(app.state.database, "BC-HC-022") is None


async def test_zero_quota_workspace_rejects_every_new_id(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A zero quota workspace can never grow and reports zero usage."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Quota Zero", quota=0)

    refused = await report(client, workspace, ingest_body())

    assert refused.status_code == 409
    assert refused.json()["error"]["details"] == {"quota": 0, "used": 0}
    assert await count_cases(app.state.database, workspace.workspace_id) == 0


async def test_full_quota_still_accepts_a_repeat_report(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """An existing id never consumes new quota, even at the limit."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Quota Upsert", quota=1)
    await report(client, workspace, ingest_body())

    repeat = await report(client, workspace, ingest_body(title="更新后的标题"))

    assert repeat.status_code == 200
    assert repeat.json()["workspaceUsed"] == 1
    assert repeat.headers["x-he-workspace-used"] == "1"


async def test_concurrent_distinct_reports_never_oversell(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Parallel inserts cannot both observe free quota and overshoot the limit."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Quota Race", quota=3)

    responses = await asyncio.gather(
        *[
            report(
                client,
                workspace,
                ingest_body(
                    badCaseId=f"BC-RACE-{index}",
                    sessionId=f"session-race-{index}",
                ),
            )
            for index in range(8)
        ],
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses.count(201) == 3
    assert statuses.count(409) == 5
    refused = [response.json()["error"] for response in responses if response.status_code == 409]
    assert {error["code"] for error in refused} == {"QUOTA_EXCEEDED"}
    assert {error["details"]["quota"] for error in refused} == {3}
    assert await count_cases(app.state.database, workspace.workspace_id) == 3


async def test_concurrent_identical_reports_create_one_row(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The same id reported in parallel yields one 201 followed by 200 upserts."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Quota Same", quota=5)

    responses = await asyncio.gather(
        *[report(client, workspace, ingest_body()) for _ in range(4)],
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 200, 200, 201]
    assert await count_cases(app.state.database, workspace.workspace_id) == 1
    assert {response.json()["workspaceUsed"] for response in responses} == {1}
