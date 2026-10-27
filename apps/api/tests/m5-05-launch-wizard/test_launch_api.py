"""Launch wizard API contract: probe preview, run creation, cluster previews."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.domain import (
    agents,
    bad_case_analysis,
    bad_cases,
    evolution_targets,
    probe_reports,
    session_families,
    source_records,
)
from app.db.models.evolution import evolution_runs
from app.main import create_app

ADMIN_TEMP_PASSWORD = "launch-wizard-admin-temp-password"
ADMIN_PASSWORD = "launch-wizard-admin-password"
NOW = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
SESSION_S1 = "10000000-0000-4000-8000-0000000000a1"
SESSION_S2 = "10000000-0000-4000-8000-0000000000a2"


def _session_values(session_id: str, title: str, started: datetime) -> dict[str, Any]:
    """Build one minimal session-family row joined by the probe query."""
    return {
        "id": session_id,
        "short_title": title,
        "title": title,
        "search_text": title,
        "repo_name": "example/repo",
        "project_path": "/repo",
        "model": "glm-5.3",
        "models": ["glm-5.3"],
        "started_at": started,
        "ended_at": started,
        "duration_seconds": 1,
        "status": "completed",
        "skill_names": [],
        "user_turns_count": 1,
        "messages_count": 1,
        "tools_count": 0,
        "errors_count": 0,
        "agents_count": 1,
        "tokens_total": 1,
        "source_type": "synthetic",
        "main_record_id": 1,
        "imported_at": NOW,
        "updated_at": NOW,
    }


def _case_values(
    case_id: str,
    session_id: str,
    *,
    version: str = "v2.0.0",
) -> dict[str, Any]:
    """Build one bad-case row reported against the wizard target."""
    return {
        "bad_case_id": case_id,
        "bad_case_session_id": session_id,
        "bad_case_type": "self",
        "object_name": "deep-research",
        "object_type": "skill",
        "object_version": version,
        "bad_case_agent_id": None,
        "reason": f"reason {case_id}",
        "meta_data": {},
        "source": "fixtures",
        "created_at": NOW,
        "updated_at": NOW,
    }


def _probe_values(
    probe_id: str,
    session_id: str,
    attribute_type: str,
    *,
    version: str = "v2.0.0",
) -> dict[str, Any]:
    """Build one probe report owned by the wizard target."""
    return {
        "probe_id": probe_id,
        "session_id": session_id,
        "probe_type": "skill",
        "probe_object": "deep-research",
        "object_version": version,
        "attribute_type": attribute_type,
        "probe_description": f"description {probe_id}",
        "probe_analysis": f"analysis {probe_id}",
        "created_at": NOW,
        "updated_at": NOW,
    }


async def _seed_hits(app: Any) -> None:
    """Insert two analyzed hits, one unanalyzed case, and one foreign target."""
    await ensure_fixture_external_tables(app.state.database)
    async with app.state.database.transaction() as session:
        await session.execute(
            insert(source_records),
            {
                "root_session_id": SESSION_S1,
                "agent_id": SESSION_S1,
                "kind": "main",
                "source_type": "synthetic",
                "line_count": 1,
                "received_at": NOW,
            },
        )
        await session.execute(
            insert(session_families),
            [
                _session_values(
                    SESSION_S1,
                    "研究 session 一",
                    datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
                ),
                _session_values(
                    SESSION_S2,
                    "研究 session 二",
                    datetime(2026, 9, 5, 9, 0, tzinfo=UTC),
                ),
            ],
        )
        await session.execute(
            insert(agents),
            [
                {
                    "id": f"agent-{session_id}",
                    "root_session_id": session_id,
                    "kind": "main",
                    "model": model,
                    "spawn_depth": 0,
                    "lines": 1,
                    "messages_count": 1,
                    "tokens_total": 1,
                    "tools_count": 0,
                    "errors_count": 0,
                    "sort_key": 0.0,
                }
                for session_id, model in (
                    (SESSION_S1, "glm-5.3"),
                    (SESSION_S2, "glm-5.3-flash"),
                )
            ],
        )
        await session.execute(
            insert(bad_cases),
            [
                _case_values("case-1", SESSION_S1),
                _case_values("case-2", SESSION_S2),
                _case_values("case-3", SESSION_S1),
                _case_values("case-4", SESSION_S2, version="v1.0.0"),
            ],
        )
        await session.execute(
            insert(probe_reports),
            [
                _probe_values("probe-1", SESSION_S1, "error"),
                _probe_values("probe-2", SESSION_S2, "prompt"),
                _probe_values("probe-4", SESSION_S2, "error", version="v1.0.0"),
            ],
        )
        await session.execute(
            insert(bad_case_analysis),
            [
                {
                    "bad_case_id": "case-1",
                    "analysis_status": "analyzed_issue",
                    "probe_id": "probe-1",
                    "analysis_result": {"summary": "s"},
                    "updated_at": NOW,
                },
                {
                    "bad_case_id": "case-2",
                    "analysis_status": "analyzed_issue",
                    "probe_id": "probe-2",
                    "analysis_result": {"summary": "s"},
                    "updated_at": NOW,
                },
                {
                    "bad_case_id": "case-3",
                    "analysis_status": "unanalyzed",
                    "probe_id": None,
                    "analysis_result": None,
                    "updated_at": NOW,
                },
                {
                    "bad_case_id": "case-4",
                    "analysis_status": "analyzed_issue",
                    "probe_id": "probe-4",
                    "analysis_result": {"summary": "s"},
                    "updated_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(evolution_targets),
            [
                {
                    "id": "target-enabled",
                    "object_type": "skill",
                    "object_name": "deep-research",
                    "repo_url": "https://git.example.com/agent-skills.git",
                    "sub_dir": "skills/deep-research",
                    "default_ref": "v2.0.0",
                    "enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "id": "target-disabled",
                    "object_type": "skill",
                    "object_name": "code-review",
                    "repo_url": "https://git.example.com/agent-skills.git",
                    "sub_dir": "skills/code-review",
                    "default_ref": "v1.0.0",
                    "enabled": False,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )


@pytest_asyncio.fixture
async def launch_api(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an authenticated admin client over a migrated, seeded app."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("launch-wizard-api-signing-secret-sufficient"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            login = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": ADMIN_TEMP_PASSWORD},
            )
            assert login.status_code == 200
            changed = await client.post(
                "/api/auth/change-password",
                headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
                json={"oldPassword": ADMIN_TEMP_PASSWORD, "newPassword": ADMIN_PASSWORD},
            )
            assert changed.status_code == 204
            relogin = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": ADMIN_PASSWORD},
            )
            client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"
            await _seed_hits(app)
            yield client
    finally:
        await client.aclose()


def _query_body(**overrides: Any) -> dict[str, Any]:
    """Build one probe query body aimed at the seeded target."""
    body: dict[str, Any] = {
        "targetType": "skill",
        "targetName": "deep-research",
        "targetVersion": "v2.0.0",
        "from": "2026-08-01",
        "to": "2026-09-30",
        "models": [],
        "page": 1,
        "pageSize": 8,
    }
    body.update(overrides)
    return body


def _app_of(client: httpx.AsyncClient) -> Any:
    """Return the composed test application behind an ASGI transport."""
    return cast(Any, client._transport).app


async def test_launch_endpoints_require_authentication(
    launch_api: httpx.AsyncClient,
) -> None:
    """Wizard endpoints are only reachable for authenticated users."""
    launch_api.headers.pop("Authorization", None)

    preview = await launch_api.post("/api/evolution/probes/query", json=_query_body())
    start = await launch_api.post("/api/evolution/runs", json=_query_body())
    cluster = await launch_api.post("/api/evolution/cluster-previews", json=_query_body())

    assert preview.status_code == 401
    assert start.status_code == 401
    assert cluster.status_code == 401


async def test_probe_query_returns_hit_statistics_and_rows(
    launch_api: httpx.AsyncClient,
) -> None:
    """The preview reports case/analysis/probe statistics and paged probe rows."""
    response = await launch_api.post("/api/evolution/probes/query", json=_query_body())

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "sessions": 2,
        "badCases": 3,
        "analyzed": 2,
        "unanalyzed": 1,
        "probes": 2,
        "usedProbes": 2,
        "byAttributeType": {"model": 0, "prompt": 1, "error": 1, "nonIssue": 0},
    }
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["pageSize"] == 8
    assert [item["probeId"] for item in body["items"]] == ["probe-1", "probe-2"]
    first = body["items"][0]
    assert first["sessionId"] == SESSION_S1
    assert first["sessionTitle"] == "研究 session 一"
    assert first["probeObject"] == "deep-research"
    assert first["objectVersion"] == "v2.0.0"
    assert first["attributeType"] == "error"
    assert first["description"] == "description probe-1"
    assert first["sourceBadCaseIds"] == ["case-1"]


async def test_probe_query_applies_window_models_and_paging(
    launch_api: httpx.AsyncClient,
) -> None:
    """Time window, model chips, and pagination narrow the preview."""
    windowed = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(**{"from": "2026-09-01", "to": "2026-09-30"}),
    )
    assert windowed.status_code == 200
    assert windowed.json()["summary"]["probes"] == 1
    assert [item["probeId"] for item in windowed.json()["items"]] == ["probe-2"]

    modeled = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(models=["glm-5.3"]),
    )
    assert modeled.status_code == 200
    assert [item["probeId"] for item in modeled.json()["items"]] == ["probe-1"]

    paged = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(pageSize=1, page=2),
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert [item["probeId"] for item in paged.json()["items"]] == ["probe-2"]


async def test_probe_query_without_matches_conflicts(launch_api: httpx.AsyncClient) -> None:
    """An empty probe hit count conflicts with the shared launch error code."""
    response = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetVersion="v9.9.9"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_PROBES_MATCHED"


async def test_start_run_rejects_unconfigured_or_disabled_target(
    launch_api: httpx.AsyncClient,
) -> None:
    """Launches fail fast when the object has no enabled configuration."""
    unknown = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(targetName="web-search"),
    )
    disabled = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(targetName="code-review", targetVersion="v1.0.0"),
    )

    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"


async def test_start_run_rejects_window_and_empty_hits(
    launch_api: httpx.AsyncClient,
) -> None:
    """Invalid windows and zero probe hits fail before a run row exists."""
    inverted = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(**{"from": "2026-09-30", "to": "2026-09-01"}),
    )
    empty = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(targetVersion="v9.9.9"),
    )

    assert inverted.status_code == 422
    assert inverted.json()["error"]["code"] == "VALIDATION_INVALID"
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "NO_PROBES_MATCHED"
    runs = await launch_api.get("/api/evolution/runs")
    assert runs.json()["running"] == []


async def test_start_run_accepts_and_snapshots_query(
    launch_api: httpx.AsyncClient,
) -> None:
    """A valid launch returns 202 with identifiers and traceable snapshots."""
    me = await launch_api.get("/api/auth/me")
    assert me.status_code == 200
    creator_id = me.json()["id"]
    response = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(mode="full"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "preparing"
    assert body["runId"] and body["jobId"]

    async with _app_of(launch_api).state.database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_runs).where(evolution_runs.c.id == body["runId"]),
                )
            )
            .mappings()
            .one()
        )
    assert row["mode"] == "full"
    assert row["engine_key"] == "full"
    assert row["status"] == "preparing"
    assert row["target_config_id"] == "target-enabled"
    assert row["target_name"] == "deep-research"
    assert row["target_version"] == "v2.0.0"
    assert row["repo_url"] == "https://git.example.com/agent-skills.git"
    assert row["sub_dir"] == "skills/deep-research"
    assert str(row["window_from"]) == "2026-08-01"
    assert str(row["window_to"]) == "2026-09-30"
    assert row["models"] == []
    assert row["created_by"] == creator_id

    run_card = await launch_api.get("/api/evolution/runs")
    assert [card["runId"] for card in run_card.json()["running"]] == [body["runId"]]
    card = run_card.json()["running"][0]
    assert card["mode"] == "full"
    assert card["status"] == "preparing"
    assert card["window"] == {"from": "2026-08-01", "to": "2026-09-30"}
    assert card["createdBy"]


async def test_start_run_redacts_eval_secrets_before_snapshot(
    launch_api: httpx.AsyncClient,
) -> None:
    """Eval credential fields are redacted before the run snapshot becomes durable."""
    response = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(
            mode="full",
            eval={
                "apiKey": "sk-live-abc123",
                "provider": "x",
                "nested": {
                    "token": "nested-token-123",
                    "options": {"api_key": "sk-nested-456"},
                },
            },
        ),
    )

    assert response.status_code == 202
    body = response.json()
    async with _app_of(launch_api).state.database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_runs).where(evolution_runs.c.id == body["runId"]),
                )
            )
            .mappings()
            .one()
        )
    assert row["eval_config"] == {
        "apiKey": "<redacted>",
        "provider": "x",
        "nested": {
            "token": "<redacted>",
            "options": {"api_key": "<redacted>"},
        },
    }
    serialized = json.dumps(row["eval_config"])
    assert "sk-live-abc123" not in serialized
    assert "nested-token-123" not in serialized
    assert "sk-nested-456" not in serialized


async def test_cluster_preview_creates_cluster_only_run(
    launch_api: httpx.AsyncClient,
) -> None:
    """The cluster-only launch persists a preview run and shares validations."""
    disabled = await launch_api.post(
        "/api/evolution/cluster-previews",
        json=_query_body(mode="cluster_only", targetName="code-review", targetVersion="v1.0.0"),
    )
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"

    empty = await launch_api.post(
        "/api/evolution/cluster-previews",
        json=_query_body(mode="cluster_only", targetVersion="v9.9.9"),
    )
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "NO_PROBES_MATCHED"

    response = await launch_api.post(
        "/api/evolution/cluster-previews",
        json=_query_body(mode="cluster_only"),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "preparing"

    async with _app_of(launch_api).state.database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_runs).where(evolution_runs.c.id == body["runId"]),
                )
            )
            .mappings()
            .one()
        )
    assert row["mode"] == "cluster_only"
    assert row["engine_key"] == "cluster_only"
    assert row["status"] == "preparing"
