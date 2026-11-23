"""Launch wizard API contract: probe preview, run creation, cluster previews."""

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.domain import (
    agent_events,
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
from app.service.evolution.attribution import AttributionInput, AttributionResult, RuleBasedEngine
from app.third_party_api.git.workspace import PreparedWorkspace
from app.utils.definition import definition_file_hash
from tests.target_content_support import FakeDefinitionSource, FakeTargetVersionResolver

ADMIN_TEMP_PASSWORD = "launch-wizard-admin-temp-password"
ADMIN_PASSWORD = "launch-wizard-admin-password"
NOW = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
CASE_AT = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
SESSION_S1 = "10000000-0000-4000-8000-0000000000a1"
SESSION_S2 = "10000000-0000-4000-8000-0000000000a2"
SESSION_S3 = "10000000-0000-4000-8000-0000000000a3"


def _session_values(
    session_id: str,
    title: str,
    started: datetime,
    *,
    model: str = "glm-5.3",
) -> dict[str, Any]:
    """Build one minimal session-family row joined by the probe query."""
    return {
        "id": session_id,
        "short_title": title,
        "title": title,
        "search_text": title,
        "repo_name": "example/repo",
        "project_path": "/repo",
        "model": model,
        "models": [model],
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


def _agent_values(
    agent_id: str,
    session_id: str,
    model: str,
    *,
    kind: str = "main",
    spawn_depth: int = 0,
) -> dict[str, Any]:
    """Build one agent row inside a session tree."""
    return {
        "id": agent_id,
        "root_session_id": session_id,
        "kind": kind,
        "model": model,
        "spawn_depth": spawn_depth,
        "lines": 1,
        "messages_count": 1,
        "tokens_total": 1,
        "tools_count": 0,
        "errors_count": 0,
        "sort_key": 0.0,
    }


def _case_values(
    case_id: str,
    session_id: str,
    *,
    object_name: str = "deep-research",
    version: str = "v2.0.0",
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Build one bad case row for the reported object."""
    return {
        "bad_case_id": case_id,
        "bad_case_session_id": session_id,
        "bad_case_type": "self",
        "object_name": object_name,
        "object_type": "skill",
        "object_version": version,
        "bad_case_agent_id": agent_id,
        "title": f"case {case_id}",
        "bad_case_description": f"reason {case_id}",
        "meta_data": {},
        "source": "fixtures",
        "created_at": CASE_AT,
        "updated_at": CASE_AT,
    }


def _probe_values(
    probe_id: str,
    session_id: str,
    attribute_type: str,
    *,
    object_name: str = "deep-research",
    version: str = "v2.0.0",
) -> dict[str, Any]:
    """Build one probe report owned by the root-cause target."""
    return {
        "probe_id": probe_id,
        "session_id": session_id,
        "probe_type": "skill",
        "probe_object": object_name,
        "object_version": version,
        "attribute_type": attribute_type,
        "probe_description": f"description {probe_id}",
        "probe_analysis": f"analysis {probe_id}",
        "created_at": NOW,
        "updated_at": NOW,
    }


def _analysis_values(
    case_id: str,
    status: str,
    probe_id: str | None,
) -> dict[str, Any]:
    """Build one attribution row linking a bad case to an optional probe."""
    return {
        "bad_case_id": case_id,
        "analysis_status": status,
        "probe_id": probe_id,
        "analysis_result": {"summary": "s"} if status == "analyzed_issue" else None,
        "updated_at": NOW,
    }


async def _seed_hits(app: Any, revision: str = "tag:v2.0.0") -> None:
    """Insert divergent reported objects, probe root causes, and foreign targets."""
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
                    model="glm-5.3-flash",
                ),
                _session_values(
                    SESSION_S3,
                    "研究 session 三",
                    datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
                ),
            ],
        )
        await session.execute(
            insert(agents),
            [
                _agent_values(f"agent-{SESSION_S1}", SESSION_S1, "glm-5.3"),
                _agent_values(f"agent-{SESSION_S2}", SESSION_S2, "glm-5.3-flash"),
                _agent_values(f"agent-{SESSION_S3}", SESSION_S3, "glm-5.3"),
                _agent_values(
                    "agent-case", SESSION_S2, "glm-5.3-case", kind="agent", spawn_depth=1
                ),
            ],
        )
        await session.execute(
            insert(bad_cases),
            [
                _case_values("case-1", SESSION_S1),
                _case_values("case-2", SESSION_S2, agent_id="agent-case"),
                _case_values("case-3", SESSION_S1),
                _case_values("case-4", SESSION_S2, version="v1.0.0"),
                _case_values("case-window", SESSION_S3, object_name="reported-object"),
                _case_values(
                    "case-unanalyzed", SESSION_S2, object_name="web-search", version="v1.0.0"
                ),
                _case_values(
                    "case-nonissue", SESSION_S2, object_name="web-search", version="v1.0.0"
                ),
            ],
        )
        await session.execute(
            insert(probe_reports),
            [
                _probe_values("probe-1", SESSION_S1, "error"),
                _probe_values("probe-2", SESSION_S2, "prompt"),
                _probe_values("probe-window", SESSION_S1, "model"),
                _probe_values("probe-4", SESSION_S2, "error", version="v1.0.0"),
            ],
        )
        await session.execute(
            insert(bad_case_analysis),
            [
                _analysis_values("case-1", "analyzed_issue", "probe-1"),
                _analysis_values("case-2", "analyzed_issue", "probe-2"),
                _analysis_values("case-3", "unanalyzed", None),
                _analysis_values("case-4", "analyzed_issue", "probe-4"),
                _analysis_values("case-window", "analyzed_issue", "probe-window"),
                _analysis_values("case-unanalyzed", "unanalyzed", None),
                _analysis_values("case-nonissue", "analyzed_nonissue", None),
            ],
        )
        await session.execute(
            insert(agent_events),
            [
                {
                    "agent_id": f"agent-{SESSION_S1}",
                    "event_index": 0,
                    "line_no": 1,
                    "message_offset": 0,
                    "kind": "skill",
                    "name": "deep-research",
                    "object_version": "v2.0.0",
                    "object_revision": revision,
                    "triggered_at": datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
                },
                {
                    "agent_id": f"agent-{SESSION_S2}",
                    "event_index": 0,
                    "line_no": 1,
                    "message_offset": 0,
                    "kind": "skill",
                    "name": "deep-research",
                    "object_version": "v2.0.0",
                    "object_revision": revision,
                    "triggered_at": datetime(2026, 9, 5, 8, 0, tzinfo=UTC),
                },
                {
                    "agent_id": f"agent-{SESSION_S3}",
                    "event_index": 0,
                    "line_no": 1,
                    "message_offset": 0,
                    "kind": "skill",
                    "name": "reported-object",
                    "object_version": "v2.0.0",
                    "object_revision": revision,
                    "triggered_at": datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
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
                    "validation_project_id": "val-deep-research",
                    "test_project_id": "test-deep-research",
                    "enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "id": "target-reported",
                    "object_type": "skill",
                    "object_name": "reported-object",
                    "repo_url": "https://git.example.com/agent-skills.git",
                    "sub_dir": "skills/reported-object",
                    "default_ref": "v2.0.0",
                    "validation_project_id": "val-reported-object",
                    "test_project_id": "test-reported-object",
                    "enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "id": "target-web-search",
                    "object_type": "skill",
                    "object_name": "web-search",
                    "repo_url": "https://git.example.com/agent-skills.git",
                    "sub_dir": "skills/web-search",
                    "default_ref": "v1.0.0",
                    "validation_project_id": "val-web-search",
                    "test_project_id": "test-web-search",
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
                    "validation_project_id": "val-code-review",
                    "test_project_id": "test-code-review",
                    "enabled": False,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )


class _FakeWorkspacePreparer:
    """Return deterministic local workspace facts without network access."""

    supports_candidate_lifecycle = False

    def __init__(self, root: Path) -> None:
        """Bind one temporary data root."""
        self._root = root

    async def prepare(self, run: Any) -> PreparedWorkspace:
        """Create directory placeholders matching the real workspace contract."""
        repo_path = self._root / "repos" / str(run.target_config_id)
        workspace = self._root / "workspaces" / run.id
        workspace.mkdir(parents=True, exist_ok=True)
        repo_path.mkdir(parents=True, exist_ok=True)
        return PreparedWorkspace(
            repo_path=repo_path,
            path=workspace,
            ref=run.target_version,
            base_commit="a" * 40,
            branch=f"evo/{run.created_at:%Y%m%d}-{run.id}",
        )

    def cleanup_workspaces(
        self,
        *,
        active_run_ids: set[str],
        keep: int = 20,
    ) -> tuple[Path, ...]:
        """Keep prepare-only tests free of background candidate cleanup."""
        del active_run_ids, keep
        return ()


@pytest_asyncio.fixture
async def launch_api(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an authenticated admin client over a migrated, seeded app."""
    from app.third_party_api.ai_agent import factory
    from tests.attribution.test_local_runtime import ScriptAgent

    if getattr(request, "param", None) == "provider":
        monkeypatch.setitem(factory._REGISTRY, ScriptAgent.provider_id, ScriptAgent)
        monkeypatch.setenv("AI_AGENT_PROVIDER", ScriptAgent.provider_id)
    revision = (
        f"digest:{definition_file_hash(FakeDefinitionSource.body)}"
        if getattr(request, "param", None)
        else "tag:v2.0.0"
    )
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            attribution_package_dir=tmp_path / "attribute",
            attribution_agent=getattr(request, "param", None),
            jwt_secret=SecretStr("launch-wizard-api-signing-secret-sufficient"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
            # This fixture exercises the launch/prepare plumbing with the
            # placeholder backend; failing explicitly is covered by the
            # clustering and strict-policy tests instead.
            ai_agent_failure_policy="degrade",
        ),
        git_workspaces=_FakeWorkspacePreparer(tmp_path),
        target_version_resolver=FakeTargetVersionResolver(revisions={"v2.0.0": revision}),
        definition_source=FakeDefinitionSource(),
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
            await _seed_hits(app, revision)
            yield client
    finally:
        await client.aclose()


def _query_body(**overrides: Any) -> dict[str, Any]:
    """Build one probe query body aimed at the seeded target."""
    body: dict[str, Any] = {
        "targetType": "skill",
        "cacheEnabled": False,
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


async def test_launch_records_creation_and_prepare_start_events(
    launch_api: httpx.AsyncClient,
) -> None:
    """Run admission and its queued prepare job leave durable replay history."""
    accepted = await launch_api.post("/api/evolution/runs", json=_query_body())
    assert accepted.status_code == 202
    app = _app_of(launch_api)
    await app.state.jobs.wait(accepted.json()["jobId"])

    events = await launch_api.get(
        f"/api/evolution/runs/{accepted.json()['runId']}/events",
    )

    assert events.status_code == 200
    event_types = [item["eventType"] for item in events.json()["items"]]
    assert event_types[:5] == [
        "run_created",
        "prepare_started",
        "sessions_linked",
        "potential_computed",
        "attribution_created",
    ]
    # With explicit degrade, the placeholder provider falls back once per task.
    assert event_types[5:-2] == ["ai_agent_call", "degraded"] * 3
    assert event_types[-2:] == ["clusters_created", "workspace_prepared"]
    assert events.json()["hasMore"] is False


async def test_probe_query_returns_hit_statistics_and_rows(
    launch_api: httpx.AsyncClient,
) -> None:
    """Preview statistics and one row per probe come from the root-cause object."""
    response = await launch_api.post("/api/evolution/probes/query", json=_query_body())

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "sessions": 2,
        "badCases": 3,
        "analyzed": 3,
        "unanalyzed": 0,
        "probes": 3,
        "usedProbes": 3,
        "byAttributeType": {
            "model": 1,
            "prompt": 1,
            "error": 1,
            "flow": 0,
            "context": 0,
            "nonIssue": 0,
        },
    }
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["pageSize"] == 8
    assert [item["probeId"] for item in body["items"]] == [
        "probe-1",
        "probe-window",
        "probe-2",
    ]
    first = body["items"][0]
    assert first["sessionId"] == SESSION_S1
    assert first["sessionTitle"] == "研究 session 一"
    assert first["probeObject"] == "deep-research"
    assert first["objectVersion"] == "v2.0.0"
    assert first["attributeType"] == "error"
    assert first["description"] == "description probe-1"
    assert first["sourceBadCaseIds"] == ["case-1"]
    assert first["model"] == "glm-5.3"
    assert body["items"][2]["model"] == "glm-5.3-case"
    assert body["items"][2]["sourceBadCaseIds"] == ["case-2"]


async def test_probe_query_applies_window_models_and_paging(
    launch_api: httpx.AsyncClient,
) -> None:
    """Time window, model chips, and pagination narrow the probe-ranked preview."""
    september = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(**{"from": "2026-09-01", "to": "2026-09-30"}),
    )
    assert september.status_code == 200
    assert september.json()["summary"]["probes"] == 1
    assert [item["probeId"] for item in september.json()["items"]] == ["probe-2"]

    august = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(**{"from": "2026-08-01", "to": "2026-08-31"}),
    )
    assert august.status_code == 200
    assert [item["probeId"] for item in august.json()["items"]] == [
        "probe-1",
        "probe-window",
    ]

    modeled = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(models=["glm-5.3"]),
    )
    assert modeled.status_code == 200
    assert [item["probeId"] for item in modeled.json()["items"]] == [
        "probe-1",
        "probe-window",
    ]

    tree_modeled = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(models=["glm-5.3-case"]),
    )
    assert tree_modeled.status_code == 200
    assert [item["probeId"] for item in tree_modeled.json()["items"]] == ["probe-2"]

    paged = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(pageSize=1, page=2),
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 3
    assert [item["probeId"] for item in paged.json()["items"]] == ["probe-window"]


async def test_probe_query_matches_root_cause_not_reported_object(
    launch_api: httpx.AsyncClient,
) -> None:
    """A case reported against object A is found through its probe's object B."""
    root_cause = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetName="deep-research"),
    )
    assert root_cause.status_code == 200
    window_item = next(
        item for item in root_cause.json()["items"] if item["probeId"] == "probe-window"
    )
    assert window_item["probeObject"] == "deep-research"
    assert window_item["sourceBadCaseIds"] == ["case-window"]

    reported = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetName="reported-object"),
    )
    assert reported.status_code == 409
    assert reported.json()["error"]["code"] == "NO_PROBES_MATCHED"


async def test_probe_query_ignores_unanalyzed_reports(
    launch_api: httpx.AsyncClient,
) -> None:
    """Unanalyzed and non-issue reports never count as a probe hit."""
    preview = await launch_api.post("/api/evolution/probes/query", json=_query_body())
    assert preview.status_code == 200
    summary = preview.json()["summary"]
    assert summary["unanalyzed"] == 0
    assert summary["badCases"] == 3
    assert summary["byAttributeType"]["nonIssue"] == 0

    only_unanalyzed = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetName="web-search", targetVersion="v1.0.0"),
    )
    assert only_unanalyzed.status_code == 409
    assert only_unanalyzed.json()["error"]["code"] == "NO_PROBES_MATCHED"


async def test_probe_query_uses_default_ref_and_requires_configured_target(
    launch_api: httpx.AsyncClient,
) -> None:
    """Preview resolves the configured defaultRef and rejects missing targets."""
    defaulted = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetVersion=None),
    )
    assert defaulted.status_code == 200
    assert defaulted.json()["total"] == 3
    assert {item["objectVersion"] for item in defaulted.json()["items"]} == {"v2.0.0"}

    unknown = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetName="unknown-skill"),
    )
    assert unknown.status_code == 409
    assert unknown.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"

    disabled = await launch_api.post(
        "/api/evolution/probes/query",
        json=_query_body(targetName="code-review", targetVersion="v1.0.0"),
    )
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "TARGET_NOT_CONFIGURED"


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
        json=_query_body(targetName="unknown-skill"),
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
        json=_query_body(**{"from": "2026-01-01", "to": "2026-01-02"}),
    )
    reported_only = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(targetName="reported-object", targetVersion="v9.9.9"),
    )

    assert inverted.status_code == 422
    assert inverted.json()["error"]["code"] == "VALIDATION_INVALID"
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "NO_ASSOCIATED_SESSIONS"
    assert reported_only.status_code == 202
    reported_run = reported_only.json()["runId"]
    runs = await launch_api.get("/api/evolution/runs")
    assert reported_run in {
        card["runId"] for card in runs.json()["running"] + runs.json()["history"]
    }


async def test_editing_unbound_target_keeps_main_remote_validation(
    launch_api: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing an upgraded target must not require a Git definition file until it binds a Skill."""
    service = _app_of(launch_api).state.evolution_targets
    validate = AsyncMock()
    freeze = AsyncMock(side_effect=AssertionError("legacy edit loaded a definition"))
    monkeypatch.setattr(service._git_remote, "validate", validate)
    monkeypatch.setattr(service._definitions, "freeze", freeze)
    route = "/api/workspaces/ws-default/evolution/targets"
    response = await launch_api.get(route)
    target = next(t for t in response.json()["items"] if t["id"] == "target-enabled")
    body = {
        key: target[key]
        for key in (
            "objectType",
            "objectName",
            "repoUrl",
            "subDir",
            "defaultRef",
            "validationProjectId",
            "testProjectId",
            "enabled",
        )
    }
    body["testProjectId"] = "edited-project"
    edited = await launch_api.put(f"{route}/target-enabled", json=body)
    assert edited.status_code == 200, edited.text
    assert edited.json()["attributionPackageId"] is None
    validate.assert_awaited_once()
    freeze.assert_not_awaited()


async def test_unbound_production_target_computes_cache_misses_and_reuses_them(
    launch_api: httpx.AsyncClient,
) -> None:
    """Legacy rule runs keep their production cache identity across the upgrade."""
    workspace = "/api/workspaces/ws-default/evolution"
    body = _query_body(mode="cluster_only", cacheEnabled=True)
    preview_body = {
        key: body[key]
        for key in ("targetType", "targetName", "targetVersion", "from", "to", "cacheEnabled")
    }
    app = _app_of(launch_api)
    for pass_index in range(2):
        preview = await launch_api.post(f"{workspace}/preview/attribution", json=preview_body)
        assert preview.status_code == 200, preview.text
        summary = preview.json()["summary"]
        assert preview.json()["usesBoundSkill"] is False
        assert summary["potential"] > 0
        assert summary["reused"] == (summary["potential"] if pass_index else 0)
        assert summary["fresh"] == (0 if pass_index else summary["potential"])
        launched = await launch_api.post(f"{workspace}/cluster-previews", json=body)
        assert launched.status_code == 202, launched.text
        job = await app.state.jobs.wait(launched.json()["jobId"])
        assert job.status == "completed", job.error
        history = await app.state.attribution_jobs.history(launched.json()["runId"])
        assert history.items[0].observation.reused == summary["reused"]
        assert history.items[0].observation.created == summary["fresh"]


async def test_prepare_joins_paused_attribution_and_resumes_only_missing_cases(
    launch_api: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pause finishes the in-flight case, prevents new calls, and resumes its missing tail."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    class SlowRule(RuleBasedEngine):
        async def attribute(self, item: AttributionInput) -> AttributionResult:
            calls.append(item.bad_case_id)
            started.set()
            await release.wait()
            return await super().attribute(item)

    app = _app_of(launch_api)
    runner = app.state.attribution_jobs._runner
    monkeypatch.setattr(runner, "_engine_factory", lambda _: SlowRule())
    monkeypatch.setattr(runner, "_max_concurrency", 1)
    api = "/api/workspaces/ws-default/evolution"
    result = await launch_api.post(f"{api}/cluster-previews", json=_query_body(mode="cluster_only"))
    assert result.status_code == 202, result.text
    run_id = result.json()["runId"]
    path = f"{api}/runs/{run_id}"
    try:
        await asyncio.wait_for(started.wait(), 5)
        paused = await launch_api.post(f"{path}/pause")
        assert paused.status_code == 200, paused.text
        refused = await launch_api.post(f"{path}/attribution-jobs")
        assert refused.status_code == 409, refused.text
        (child,) = (await app.state.attribution_jobs.history(run_id)).items
        retry = await launch_api.post(f"{path}/attribution-jobs/{child.job_id}/retry")
        assert retry.status_code == 409, retry.text
    finally:
        release.set()
    yielded = await app.state.jobs.wait(result.json()["jobId"])
    assert yielded.result["yielded"] is True
    assert len(calls) == 1
    resumed = await launch_api.post(f"{path}/resume")
    assert resumed.status_code == 200, resumed.text
    async with asyncio.timeout(10):
        while True:
            row = (await launch_api.get(f"{path}")).json()
            if row["status"] == "completed":
                break
            await asyncio.sleep(0.05)
    assert len(calls) > 1
    assert len(set(calls)) == len(calls)


async def test_start_run_accepts_and_snapshots_query(
    launch_api: httpx.AsyncClient,
) -> None:
    """A valid launch returns 202, completes prepare, and keeps the run preparing."""
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

    job = await _app_of(launch_api).state.jobs.wait(body["jobId"])
    assert job.status == "completed"
    assert job.error is None
    assert job.result["runId"] == body["runId"]
    assert job.result["status"] == "running"
    assert job.result["progressUnit"] == 5

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
    assert row["status"] == "running"
    assert row["branch_name"].startswith("evo/")
    assert row["base_commit"] == "a" * 40
    assert row["progress_unit"] == 5
    assert row["target_config_id"] == "target-enabled"
    assert row["target_name"] == "deep-research"
    assert row["target_version"] == "v2.0.0"
    assert row["repo_url"] == "https://git.example.com/agent-skills.git"
    assert row["sub_dir"] == "skills/deep-research"
    assert row["validation_project_id"] == "val-deep-research"
    assert row["test_project_id"] == "test-deep-research"
    assert str(row["window_from"]) == "2026-08-01"
    assert str(row["window_to"]) == "2026-09-30"
    assert row["models"] == []
    assert row["cache_enabled"] is False
    assert row["attribution_skill_key"] == "platform-default"
    assert row["attribution_skill_revision"] == 1
    assert row["attribution_skill_content_hash"] == (
        "7e30d5d3721030420842f9e1f1b08e9a1c33644eb7a78eca82bbd06abbca525d"
    )
    assert row["potential_policy"] == {
        "legacyRule": True,
        "preset": "default",
        "includeSelfReport": True,
        "includeAfterObject": True,
        "sameObjectOnly": False,
    }
    assert row["created_by"] == creator_id

    run_card = await launch_api.get("/api/evolution/runs")
    assert [card["runId"] for card in run_card.json()["running"]] == [body["runId"]]
    card = run_card.json()["running"][0]
    assert card["mode"] == "full"
    assert card["status"] == "running"
    assert card["window"] == {"from": "2026-08-01", "to": "2026-09-30"}
    assert card["createdBy"]


async def test_start_run_snapshots_custom_policy_and_cache_switch(
    launch_api: httpx.AsyncClient,
) -> None:
    """Custom policy switches and a disabled cache are frozen on the run row."""
    response = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(
            mode="full",
            policy={
                "preset": "custom",
                "includeSelfReport": True,
                "includeAfterObject": True,
                "sameObjectOnly": True,
            },
            cacheEnabled=False,
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
    assert row["cache_enabled"] is False
    assert row["potential_policy"] == {
        "legacyRule": True,
        "preset": "custom",
        "includeSelfReport": True,
        "includeAfterObject": True,
        "sameObjectOnly": True,
    }


async def test_start_run_rejects_invalid_custom_policy(
    launch_api: httpx.AsyncClient,
) -> None:
    """A custom policy without both switches fails before any run write."""
    response = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(
            mode="full",
            policy={"preset": "custom", "includeSelfReport": True},
        ),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POLICY_INVALID"


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
        json=_query_body(mode="cluster_only", **{"from": "2026-01-01", "to": "2026-01-02"}),
    )
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "NO_ASSOCIATED_SESSIONS"

    response = await launch_api.post(
        "/api/evolution/cluster-previews",
        json=_query_body(mode="cluster_only", targetVersion="v9.9.9"),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "preparing"

    job = await _app_of(launch_api).state.jobs.wait(body["jobId"])
    assert job.status == "completed"
    assert job.error is None

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
    assert row["status"] == "completed"
    assert row["workspace_path"] is None
    assert row["branch_name"] is None


async def test_launch_rejects_unregistered_engine_before_writes(
    launch_api: httpx.AsyncClient,
) -> None:
    """Unknown engine keys fail synchronously with the stable ENGINE_INVALID code."""
    response = await launch_api.post(
        "/api/evolution/runs",
        json=_query_body(mode="full", engineKey="unknown-engine"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ENGINE_INVALID"
    runs = await launch_api.get("/api/evolution/runs")
    assert runs.json()["running"] == []
    assert runs.json()["history"] == []


@pytest.mark.parametrize(
    "launch_api",
    ["claude" if os.environ.get("HE_TEST_LIVE_ATTRIBUTION") == "1" else "provider"],
    indirect=True,
)
@pytest.mark.parametrize(
    "selection",
    ["other"]
    if os.environ.get("HE_TEST_LIVE_ATTRIBUTION") == "1"
    else ["bound", "implicit", "other"],
)
async def test_local_attribution_from_wizard_to_cluster(
    launch_api: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    selection: str,
) -> None:
    """Start through HTTP and wait for the real job, report transaction and clustering."""
    import io
    import zipfile

    from app.service.evolution.attribution_skill_packages import AttributionSkillPackageService
    from tests.attribution.test_local_runtime import Source

    app = _app_of(launch_api)
    # The binding must use its saved file even if runtime Git reads are unavailable.
    runtime_source = Source()
    app.state.local_attribution.source = runtime_source
    workspace = "/api/workspaces/ws-default"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "SKILL.md",
            "---\nname: acceptance-skill\ndescription: Synthetic case acceptance\n---\n"
            "For this synthetic case classify the reported object as flow. "
            "Use the supplied writer to produce probe_report.json with the reported version.",
        )

    uploaded = await launch_api.post(
        f"{workspace}/attribution-skill-packages",
        files={"file": ("custom.zip", archive.getvalue(), "application/zip")},
    )
    assert uploaded.status_code == 201

    runtime_read = runtime_source.read_file
    offline = AsyncMock(side_effect=AssertionError("bound batch fetched the mutable ref"))
    monkeypatch.setattr(runtime_source, "read_file", offline)

    # Exercise the same atomic create used by the overview form.
    old = await launch_api.get(f"{workspace}/evolution/targets")
    target = next(t for t in old.json()["items"] if t["id"] == "target-enabled")
    deleted = await launch_api.delete(f"{workspace}/evolution/targets/target-enabled")
    assert deleted.status_code == 204
    monkeypatch.setattr(app.state.evolution_targets._git_remote, "validate", AsyncMock())
    body = {
        k: v
        for k, v in target.items()
        if k not in {"id", "attributionSkillName", "attributionFailure", "definition"}
    }
    # Exercise the deployed default as well as an immutable uploaded package.
    bound_id = "default-attribute-badcases" if selection == "bound" else uploaded.json()["id"]
    bound_name = "attribute-badcases" if selection == "bound" else "acceptance-skill"
    body["attributionPackageId"] = bound_id
    created = await launch_api.post(f"{workspace}/evolution/targets", json=body)
    assert created.status_code == 201, created.text
    target_id = created.json()["id"]
    assert created.json()["attributionSkillName"] == bound_name
    protected = await launch_api.delete(f"{workspace}/attribution-skill-packages/{bound_id}")
    assert protected.status_code == 409
    async with asyncio.timeout(600 if os.environ.get("HE_TEST_LIVE_ATTRIBUTION") else 15):
        while True:
            async with app.state.database.session() as session:
                due = await session.scalar(
                    select(evolution_targets.c.attribution_due).where(
                        evolution_targets.c.id == target_id
                    )
                )
            if due is None:
                break
            await asyncio.sleep(0.2)
    before = await launch_api.get("/api/evolution/runs")
    assert before.json()["running"] == before.json()["history"] == []
    root = app.state.local_attribution.root("ws-default")
    batches = root / "attribute_input/batches"
    (binding_batch,) = list(batches.iterdir())
    binding_inputs = [
        json.loads(path.read_bytes()) for path in binding_batch.glob("*/manifest.json")
    ]
    offline.assert_not_awaited()
    monkeypatch.setattr(runtime_source, "read_file", runtime_read)
    assert binding_inputs
    for manifest in binding_inputs:
        definition = root / "attribute_source" / manifest["definitionKey"] / "definition.md"
        assert definition.read_text() == created.json()["definition"]["preview"]
        assert manifest["gitSource"]["commit"] == created.json()["definition"]["commit"]
    assert all(
        m["batchId"] == binding_batch.name and m["trigger"] == "target_binding"
        for m in binding_inputs
    )
    assert all(m["skill"]["name"] == bound_name for m in binding_inputs)
    preview_body = {
        key: value
        for key, value in _query_body(cacheEnabled=True).items()
        if key in {"targetType", "targetName", "targetVersion", "from", "to", "cacheEnabled"}
    }
    cached = await launch_api.post(f"{workspace}/evolution/preview/attribution", json=preview_body)
    assert cached.status_code == 200, cached.text
    counts = cached.json()["summary"]
    assert counts["bySkill"] == {bound_name: counts["potential"]}
    assert counts["potential"] > 0 and counts["missing"] == counts["fresh"] == 0
    cache_run = await launch_api.post(
        f"{workspace}/evolution/cluster-previews",
        json=_query_body(mode="cluster_only", cacheEnabled=True),
    )
    assert cache_run.status_code == 202, cache_run.text
    assert (await app.state.jobs.wait(cache_run.json()["jobId"])).status == "completed"
    assert set(batches.iterdir()) == {binding_batch}
    assert not (root / "attribute_output" / cache_run.json()["runId"]).exists()
    # A deployment can replace the shared writer between binding and launch.
    # Only a newly selected package should pick up these changed bytes.
    old_writer = app.state.local_attribution.packages.writer_path.read_bytes()
    new_writer = tmp_path / "make_probe_report.py"
    new_writer.write_bytes(old_writer + b"\n# Updated platform writer\n")
    monkeypatch.setattr(
        AttributionSkillPackageService, "writer_path", property(lambda _: new_writer)
    )
    body = _query_body()
    if selection == "bound":
        body["attributionPackageId"] = bound_id
    elif selection == "other":
        body["attributionPackageId"] = "default-attribute-badcases"
    expected_skill = "attribute-badcases" if selection == "other" else bound_name
    accepted = await launch_api.post("/api/evolution/runs", json=body)
    assert accepted.status_code == 202
    job = await app.state.jobs.wait(accepted.json()["jobId"])
    assert job.status == "completed", job.error
    range_step = await launch_api.get(
        f"{workspace}/evolution/runs/{accepted.json()['runId']}/steps/range"
    )
    assert range_step.status_code == 200, range_step.text
    assert range_step.json()["payload"]["condition"]["attributionPackageId"] == body.get(
        "attributionPackageId"
    )
    async with app.state.database.session() as session:
        reports = (
            (
                await session.execute(
                    select(probe_reports).where(
                        probe_reports.c.created_run_id == accepted.json()["runId"]
                    )
                )
            )
            .mappings()
            .all()
        )
    assert reports
    binding = await launch_api.get(f"{workspace}/evolution/targets/{target_id}/attribution-skill")
    assert binding.status_code == 200
    assert binding.json()["id"] == bound_id
    assert binding.json()["contentHash"] == binding_inputs[0]["skill"]["snapshotHash"]
    resources = await launch_api.get(f"{workspace}/attribution-skill-packages")
    resource = next(item for item in resources.json()["items"] if item["id"] == bound_id)
    if selection == "bound":
        download = await launch_api.get(
            f"{workspace}/attribution-skill-packages/{bound_id}/download"
        )
        assert download.status_code == 200
        resource_bytes = download.content
    else:
        resource_bytes = archive.getvalue()
    assert resource["contentHash"] == hashlib.sha256(resource_bytes).hexdigest()
    for report in reports:
        assert report["attribution_skill_name"] == expected_skill
        assert report["attribution_engine"] == "local-agent-skill-v1"
        case_id = report["execution_manifest"]["badCaseId"]
        inputs = batches / accepted.json()["runId"] / case_id
        manifest = json.loads((inputs / "manifest.json").read_bytes())
        assert manifest["trigger"] == "evolution_run"
        assert manifest["inputHash"] == report["execution_manifest"]["contextSnapshotHash"]
        assert (
            manifest["skill"]["snapshotHash"]
            == report["execution_manifest"]["skill"]["contentHash"]
        )
        original = next(m for m in binding_inputs if m["badcaseId"] == case_id)
        assert manifest["evidenceHash"] == original["evidenceHash"]
        skill_hash = manifest["skill"]["snapshotHash"]
        writer = root / "attribute_skill/snapshots" / skill_hash / "skill/make_probe_report.py"
        if selection == "other":
            assert skill_hash != original["skill"]["snapshotHash"]
            assert writer.read_bytes() == new_writer.read_bytes()
        else:
            assert manifest["skill"] == original["skill"]
            assert writer.read_bytes() == old_writer
        canonical = report["report_payload"]["sourceReport"]
        assert canonical["attribute_type"] in {
            "prompt",
            "model",
            "flow",
            "context",
            "error",
            "unknown",
        }
        if report["conclusion"] == "attributed":
            assert report["attribute_type"] == canonical["attribute_type"]
        else:
            assert report["attribute_type"] is None
        if os.environ.get("HE_TEST_LIVE_ATTRIBUTION") != "1":
            assert canonical["attribute_type"] == "flow"
    refreshed = await launch_api.post(
        f"{workspace}/evolution/preview/attribution", json=preview_body
    )
    assert refreshed.json()["summary"]["bySkill"] == {expected_skill: counts["potential"]}
