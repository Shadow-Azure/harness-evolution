"""Bad-case ingest success, upsert, and request-contract behaviour."""

import logging

import httpx
import pytest
from fastapi import FastAPI

from tests.ingest.helpers import (
    CREATED_AT,
    SESSION_ID,
    count_cases,
    create_ingest_workspace,
    fetch_case,
    ingest_body,
    report,
    stored_created_at,
)


async def test_first_report_creates_the_row_and_reports_usage(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A brand-new badCaseId answers 201 and logs structured fields at INFO."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest New")

    with caplog.at_level(logging.INFO, logger="app.db.crud.bad_case_ingest"):
        response = await report(client, workspace, ingest_body())

    assert response.status_code == 201
    assert response.json() == {"badCaseId": "BC-HC-021", "workspaceUsed": 1}
    assert response.headers["x-he-workspace-used"] == "1"
    ingested = [
        record
        for record in caplog.records
        if record.name == "app.db.crud.bad_case_ingest"
    ]
    assert len(ingested) == 1
    assert ingested[0].inserted is True
    assert ingested[0].bad_case_id == "BC-HC-021"

    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    assert row["workspace_id"] == workspace.workspace_id
    assert row["bad_case_session_id"] == SESSION_ID
    assert row["bad_case_type"] == "self"
    assert row["object_name"] == "deep-research"
    assert row["object_type"] == "skill"
    assert row["object_version"] == "v2.4.0"
    assert row["bad_case_agent_id"] is None
    assert row["title"] == "输出缺少来源校验"
    assert row["bad_case_description"] == "12 条结论中有 5 条没有附带来源。"
    assert row["meta_data"] == {"file": "skills/deep-research/SKILL.md", "line": 91}
    assert row["source"] == "agent-runtime"
    assert stored_created_at(row).isoformat() == "2026-11-09T15:58:00+08:00"


async def test_repeat_report_updates_fields_without_consuming_quota(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The same badCaseId in the same workspace is a 200 upsert with stable usage."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Upsert", quota=1)
    first = await report(client, workspace, ingest_body())
    assert first.status_code == 201

    second = await report(
        client,
        workspace,
        ingest_body(
            title="检索索引读取失败",
            reason="ENOENT apps/server/src/search/index.ts:142",
            objectVersion="v2.5.0",
            badCaseType="discovery",
            metaData={"file": "apps/server/src/search/index.ts", "line": 142},
            createdAt="2026-11-10T09:00:00+08:00",
        ),
    )

    assert second.status_code == 200
    assert second.json() == {"badCaseId": "BC-HC-021", "workspaceUsed": 1}
    assert second.headers["x-he-workspace-used"] == "1"
    assert await count_cases(app.state.database, workspace.workspace_id) == 1

    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    assert row["title"] == "检索索引读取失败"
    assert row["bad_case_description"] == "ENOENT apps/server/src/search/index.ts:142"
    assert row["object_version"] == "v2.5.0"
    assert row["bad_case_type"] == "discovery"
    assert row["meta_data"] == {"file": "apps/server/src/search/index.ts", "line": 142}
    assert row["workspace_id"] == workspace.workspace_id
    assert stored_created_at(row).isoformat() == "2026-11-10T09:00:00+08:00"


async def test_usage_counts_only_the_reported_workspace(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Usage is a live per-workspace count, never a shared or materialized total."""
    app, client = ingest_client
    first = await create_ingest_workspace(app, client, name="Ingest A", username="a-admin")
    second = await create_ingest_workspace(app, client, name="Ingest B", username="b-admin")

    await report(client, first, ingest_body(badCaseId="BC-A-1", sessionId="session-a-1"))
    again = await report(client, first, ingest_body(badCaseId="BC-A-2", sessionId="session-a-2"))
    other = await report(client, second, ingest_body(badCaseId="BC-B-1", sessionId="session-b-1"))

    assert again.json()["workspaceUsed"] == 2
    assert other.json()["workspaceUsed"] == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(ingest_body(workspaceId="ws-other"), id="extra-workspace-id"),
        pytest.param(ingest_body(workspace_id="ws-other"), id="extra-snake-workspace-id"),
        pytest.param(
            {
                "bad_case_id": "BC-HC-021",
                "session_id": SESSION_ID,
                "bad_case_type": "self",
                "object_name": "deep-research",
                "object_type": "skill",
                "title": "t",
                "reason": "r",
                "created_at": CREATED_AT,
            },
            id="snake-case-body",
        ),
        pytest.param(ingest_body(badCaseType="suspicion"), id="bad-case-type"),
        pytest.param(ingest_body(objectType="workflow"), id="object-type"),
        pytest.param(ingest_body(title=""), id="empty-title"),
        pytest.param(ingest_body(reason=""), id="empty-reason"),
        pytest.param(ingest_body(badCaseId=""), id="empty-bad-case-id"),
        pytest.param(ingest_body(badCaseId="x" * 65), id="long-bad-case-id"),
        pytest.param(ingest_body(title="x" * 256), id="long-title"),
        pytest.param(ingest_body(sessionId="x" * 37), id="long-session-id"),
        pytest.param(ingest_body(objectName="x" * 129), id="long-object-name"),
        pytest.param(ingest_body(createdAt="not-a-timestamp"), id="bad-timestamp"),
        pytest.param(ingest_body(createdAt="2026-11-09T07:58:00"), id="naive-timestamp"),
        pytest.param(ingest_body(metaData="not-an-object"), id="bad-metadata"),
    ],
)
async def test_body_contract_rejects_missing_or_foreign_fields(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
    body: dict[str, object],
) -> None:
    """Snake case, extra workspace identity, and out-of-range values are 422."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Invalid")

    response = await report(client, workspace, body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_INVALID"
    assert await count_cases(app.state.database, workspace.workspace_id) == 0


async def test_offset_timestamp_is_normalized_and_accepted(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A timestamp with an offset is stored as Asia/Shanghai, not relabeled."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Offset")

    response = await report(
        client,
        workspace,
        ingest_body(badCaseId="BC-OFFSET-1", createdAt="2026-11-09T07:58:00Z"),
    )

    assert response.status_code == 201
    row = await fetch_case(app.state.database, "BC-OFFSET-1")
    assert row is not None
    assert stored_created_at(row).isoformat() == "2026-11-09T15:58:00+08:00"


async def test_response_never_echoes_server_owned_columns(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The success body is exactly badCaseId plus workspaceUsed."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Ingest Shape")

    response = await report(client, workspace, ingest_body())

    assert set(response.json()) == {"badCaseId", "workspaceUsed"}
    assert isinstance(response.json()["workspaceUsed"], int)
