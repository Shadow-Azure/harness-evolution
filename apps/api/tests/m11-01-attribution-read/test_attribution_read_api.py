"""HTTP contracts for paged attribution reads and stable deep links."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import CandidateTriggerRecord
from app.db.crud.fixtures import run_corpus_seed
from app.db.models.domain import agents, bad_case_analysis, bad_cases, probe_reports
from app.db.models.evolution import evolution_run_candidates, evolution_runs
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app
from app.service.bad_cases.attribution import _trigger_order
from app.utils.time import SHANGHAI
from tests.workspaces.helpers import (
    access_token,
    backfill_legacy_associations,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)

ROOT = Path(__file__).resolve().parents[4]
SESSION = "10000000-0000-4000-8000-000000000001"
CASE = "m11-case-main"
CASE_EMPTY = "m11-case-empty"
CASE_CROSS = "m11-case-cross"
CASE_OTHER_WS = "m11-case-other-workspace"
# Imported reports can share a long prefix and differ only at the end.
PROBE_PREFIX = SESSION + "*部门/review-" + "ab" * 64 + "*"
PROBE_OLD = PROBE_PREFIX + "case-old"
PROBE_TWIN = "m11-probe-twin"
PROBE_COORD = "m11-probe-coord"
PROBE_NEW = PROBE_PREFIX + "case-new"
PROBE_CROSS = "m11-probe-cross"
PROBE_OTHER_WS = "m11-probe-other-workspace"
RUN_ID = "m11-run-attribution"
RUN_COORD_ID = "m11-run-coordinate"
AGENT_ROOT = "m11-agent-root"
AGENT_CHILD = "m11-agent-child"
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=SHANGHAI)
TWIN_AT = NOW + timedelta(minutes=30)
COORD_AT = NOW + timedelta(hours=1)
NEW_AT = NOW + timedelta(hours=2)


@dataclass(frozen=True, slots=True)
class AttributionApiEnvironment:
    """Authenticated client, seeded database, and the outsider's token."""

    client: httpx.AsyncClient
    database: Database
    admin: dict[str, str]
    outsider: dict[str, str]
    other_workspace: str


def _probe(
    probe_id: str,
    *,
    updated_at: datetime,
    object_version: str | None,
    probe_type: str = "skill",
    probe_object: str = "deep-research",
    conclusion: str = "attributed",
    attribute_type: str | None = "error",
    attribution_engine: str = "rule-v1",
    created_run_id: str | None = None,
    last_reused_run_id: str | None = None,
    reused_count: int = 0,
    structured: bool = False,
) -> dict[str, object]:
    """Build one probe row with a deterministic attribution identity."""
    row: dict[str, object] = {
        "probe_id": probe_id,
        "workspace_id": "ws-default",
        "session_id": SESSION,
        "probe_type": probe_type,
        "probe_object": probe_object,
        "object_version": object_version,
        "attribute_type": attribute_type,
        "conclusion": conclusion,
        "confidence": 0.8,
        "probe_description": f"{probe_id} reason",
        "probe_analysis": f"{probe_id} reasoning",
        "policy_version": "v1",
        "attribution_engine": attribution_engine,
        "cache_key": sha256(probe_id.encode()).hexdigest(),
        "report_schema_version": None,
        "report_payload": None,
        "execution_manifest": None,
        "execution_manifest_hash": None,
        "created_run_id": created_run_id,
        "last_reused_run_id": last_reused_run_id,
        "reused_count": reused_count,
        "created_at": NOW,
        "updated_at": updated_at,
    }
    if structured:
        row.update(
            {
                "report_schema_version": "probe-report/v2",
                "report_payload": {
                    "schemaVersion": "probe-report/v2",
                    "target": {
                        "objectType": probe_type,
                        "objectName": probe_object,
                        "objectVersion": object_version,
                    },
                    "conclusion": conclusion,
                    "category": attribute_type,
                    "evidence": [],
                    "analysis": {
                        "summary": f"{probe_id} reason",
                        "reasoning": f"{probe_id} reasoning",
                    },
                    "suggestionClues": [],
                    "warnings": [],
                },
                "execution_manifest": {
                    "manifestVersion": "attribution-execution/v1",
                    "workspaceId": "ws-default",
                    "badCaseId": CASE,
                    "target": {
                        "objectType": probe_type,
                        "objectName": probe_object,
                        "objectVersion": object_version,
                    },
                    "policyVersion": "v1",
                    "engine": attribution_engine,
                    "skill": {
                        "key": "platform-default",
                        "revision": "builtin-v1",
                        "contentHash": "a" * 64,
                    },
                    "modelConfigFingerprint": "none",
                    "contextSnapshotHash": "b" * 64,
                    "outputSchemaVersion": "probe-report/v2",
                },
                "execution_manifest_hash": "c" * 64,
            },
        )
    return row


def _case(case_id: str, *, workspace_id: str = "ws-default") -> dict[str, object]:
    """Build one issue row whose session belongs to a workspace projection."""
    return {
        "bad_case_id": case_id,
        "workspace_id": workspace_id,
        "bad_case_session_id": SESSION,
        "bad_case_type": "self",
        "object_name": "deep-research",
        "object_type": "skill",
        "object_version": "v2.0.0",
        "bad_case_agent_id": None,
        "title": case_id,
        "bad_case_description": "paged attribution test case",
        "meta_data": None,
        "source": "fixtures",
        "created_at": NOW,
        "updated_at": NOW,
    }


@pytest_asyncio.fixture
async def attribution_api(tmp_path: Path) -> AsyncIterator[AttributionApiEnvironment]:
    """Seed one workspace with several attributions, candidates, and a neighbor."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("attribution-read-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    corpus = load_fixture_corpus(ROOT / "fixtures" / "m2-synthetic" / "corpus.json")
    await run_corpus_seed(settings, corpus)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "initial-password"},
        )
        assert login.status_code == 200
        changed = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
            json={
                "oldPassword": "initial-password",
                "newPassword": "replacement-password",
            },
        )
        assert changed.status_code == 204
        authenticated = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "replacement-password"},
        )
        assert authenticated.status_code == 200

        database = app.state.database
        other_workspace = await insert_workspace(database, name="m11-neighbor")
        outsider_id = await create_user(database, username="m11-outsider")
        await insert_member(
            database,
            workspace_id=other_workspace,
            user_id=outsider_id,
            role="viewer",
        )

        async with database.transaction() as session:
            await session.execute(
                insert(agents),
                [
                    {
                        "id": AGENT_ROOT,
                        "runtime_key": "claude-code",
                        "root_session_id": SESSION,
                        "parent_agent_id": None,
                        "kind": "subagent",
                        "spawn_depth": 1,
                        "lines": 1,
                        "messages_count": 0,
                        "tokens_total": 0,
                        "tools_count": 0,
                        "errors_count": 0,
                        "sort_key": 1.0,
                        "tree_index": 0,
                    },
                    {
                        "id": AGENT_CHILD,
                        "runtime_key": "claude-code",
                        "root_session_id": SESSION,
                        "parent_agent_id": AGENT_ROOT,
                        "kind": "subagent",
                        "spawn_depth": 2,
                        "lines": 1,
                        "messages_count": 0,
                        "tokens_total": 0,
                        "tools_count": 0,
                        "errors_count": 0,
                        "sort_key": 2.0,
                        "tree_index": 1,
                    },
                ],
            )
            await session.execute(
                insert(bad_cases),
                [
                    _case(CASE),
                    _case(CASE_EMPTY),
                    _case(CASE_CROSS),
                    _case(CASE_OTHER_WS, workspace_id=other_workspace),
                ],
            )
            await session.execute(
                insert(probe_reports),
                [
                    _probe(PROBE_OLD, updated_at=NOW, object_version="v1.0.0"),
                    _probe(
                        PROBE_TWIN,
                        updated_at=TWIN_AT,
                        object_version="v1.0.0",
                    ),
                    _probe(
                        PROBE_COORD,
                        updated_at=COORD_AT,
                        object_version=None,
                        probe_type="agent",
                        probe_object="Explore",
                        conclusion="non_target",
                        attribute_type=None,
                        attribution_engine="legacy-probe-import",
                    ),
                    _probe(
                        PROBE_NEW,
                        updated_at=NEW_AT,
                        object_version="v2.0.0",
                        created_run_id=RUN_ID,
                        last_reused_run_id=RUN_ID,
                        reused_count=2,
                        structured=True,
                    ),
                    _probe(PROBE_CROSS, updated_at=NOW, object_version="v3.0.0"),
                    _probe(PROBE_OTHER_WS, updated_at=NOW, object_version="v4.0.0"),
                ],
            )
            await session.execute(
                insert(bad_case_analysis),
                [
                    {
                        "bad_case_id": CASE,
                        "analysis_status": None,
                        "probe_id": PROBE_OLD,
                        "analysis_result": None,
                        "updated_at": NOW,
                    },
                    {
                        "bad_case_id": CASE,
                        "analysis_status": None,
                        "probe_id": PROBE_TWIN,
                        "analysis_result": None,
                        "updated_at": TWIN_AT,
                    },
                    {
                        "bad_case_id": CASE,
                        "analysis_status": None,
                        "probe_id": PROBE_COORD,
                        "analysis_result": None,
                        "updated_at": COORD_AT,
                    },
                    {
                        "bad_case_id": CASE,
                        "analysis_status": None,
                        "probe_id": PROBE_NEW,
                        "analysis_result": None,
                        "updated_at": NEW_AT,
                    },
                    {
                        "bad_case_id": CASE,
                        "analysis_status": "unanalyzed",
                        "probe_id": None,
                        "analysis_result": None,
                        "updated_at": NOW,
                    },
                    {
                        "bad_case_id": CASE_CROSS,
                        "analysis_status": None,
                        "probe_id": PROBE_CROSS,
                        "analysis_result": None,
                        "updated_at": NOW,
                    },
                    {
                        "bad_case_id": CASE_OTHER_WS,
                        "analysis_status": None,
                        "probe_id": PROBE_OTHER_WS,
                        "analysis_result": None,
                        "updated_at": NOW,
                    },
                ],
            )
            await session.execute(
                insert(evolution_runs),
                [
                    {
                        "id": RUN_ID,
                        "workspace_id": "ws-default",
                        "title": "m11 attribution read",
                        "mode": "full",
                        "engine_key": "full",
                        "eval_config": {},
                        "target_type": "skill",
                        "target_name": "deep-research",
                        "target_version": "v2.0.0",
                        "base_commit": "a3f9c21d4e5f60718293a4b5c6d7e8f901234567",
                        "repo_url": "https://example.invalid/skills.git",
                        "sub_dir": "skills/deep-research",
                        "created_at": NOW,
                    },
                    {
                        "id": RUN_COORD_ID,
                        "workspace_id": "ws-default",
                        "title": "m11 coordinate attribution",
                        "mode": "full",
                        "engine_key": "full",
                        "eval_config": {},
                        "target_type": "agent",
                        "target_name": "Explore",
                        "target_version": "v1.0.0",
                        "base_commit": None,
                        "repo_url": "https://example.invalid/agents.git",
                        "sub_dir": "agents/explore",
                        "created_at": NOW,
                    },
                ],
            )
            await session.execute(
                insert(evolution_run_candidates),
                [
                    {
                        "id": "m11-candidate-new",
                        "run_id": RUN_ID,
                        "workspace_id": "ws-default",
                        "session_id": SESSION,
                        "bad_case_id": CASE,
                        "object_trigger_agent_id": None,
                        "object_trigger_event_index": None,
                        "object_trigger_at": NOW - timedelta(hours=2),
                        "case_trigger_agent_id": None,
                        "case_trigger_event_index": None,
                        "case_trigger_at": NOW - timedelta(hours=1),
                        "order_state": "comparable",
                        "included": True,
                        "included_reason": "self_report",
                        "probe_id": PROBE_NEW,
                        "is_cached": True,
                        "created_at": NEW_AT,
                    },
                    {
                        "id": "m11-candidate-coord",
                        "run_id": RUN_COORD_ID,
                        "workspace_id": "ws-default",
                        "session_id": SESSION,
                        "bad_case_id": CASE,
                        "object_trigger_agent_id": AGENT_ROOT,
                        "object_trigger_event_index": 1,
                        "object_trigger_at": None,
                        "case_trigger_agent_id": AGENT_CHILD,
                        "case_trigger_event_index": 2,
                        "case_trigger_at": None,
                        "order_state": "comparable",
                        "included": True,
                        "included_reason": "self_report",
                        "probe_id": PROBE_COORD,
                        "is_cached": False,
                        "created_at": COORD_AT,
                    },
                ],
            )

        await backfill_legacy_associations(database)

        yield AttributionApiEnvironment(
            client=client,
            database=database,
            admin=bearer(authenticated.json()["accessToken"]),
            outsider=bearer(access_token(app, user_id=outsider_id)),
            other_workspace=other_workspace,
        )


async def test_attribution_routes_require_auth(attribution_api: AttributionApiEnvironment) -> None:
    """Both attribution reads sit behind the central bearer gate."""
    for path in (
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions",
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions/{PROBE_NEW}",
    ):
        response = await attribution_api.client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_attribution_pages_are_newest_first_and_totals_count_links(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """Two-item pages follow updated_at and attributionId descending."""
    base = f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions"
    first = await attribution_api.client.get(
        base,
        headers=attribution_api.admin,
        params={"page": 1, "pageSize": 2},
    )
    second = await attribution_api.client.get(
        base,
        headers=attribution_api.admin,
        params={"page": 2, "pageSize": 2},
    )
    beyond = await attribution_api.client.get(
        base,
        headers=attribution_api.admin,
        params={"page": 3, "pageSize": 2},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert beyond.status_code == 200
    assert beyond.json() == {"items": [], "total": 4, "page": 3, "pageSize": 2}
    assert first.json()["total"] == 4
    assert first.json()["page"] == 1
    assert first.json()["pageSize"] == 2
    assert [item["attributionId"] for item in first.json()["items"]] == [
        PROBE_NEW,
        PROBE_COORD,
    ]
    assert [item["attributionId"] for item in second.json()["items"]] == [
        PROBE_TWIN,
        PROBE_OLD,
    ]
    newest = first.json()["items"][0]
    assert newest["objectVersion"] == "v2.0.0"
    assert newest["objectRef"] == "v2.0.0"
    assert newest["objectCommit"] == "a3f9c21"
    assert newest["runId"] == RUN_ID
    assert newest["isCached"] is True
    assert newest["reusedCount"] == 2
    non_target = first.json()["items"][1]
    assert non_target["conclusion"] == "non_target"
    assert non_target["category"] is None
    assert non_target["objectVersion"] is None
    assert non_target["objectRef"] is None
    assert non_target["objectCommit"] is None


async def test_attribution_detail_returns_reasoning_and_trigger_compare(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """Detail adds reasoning, policy metadata, and a time-based comparison."""
    response = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions/{PROBE_NEW}",
        headers=attribution_api.admin,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["attributionId"] == PROBE_NEW
    assert payload["badCaseId"] == CASE
    assert payload["reason"] == f"{PROBE_NEW} reason"
    assert payload["reasoning"] == f"{PROBE_NEW} reasoning"
    assert payload["policyVersion"] == "v1"
    assert payload["attributionEngine"] == "rule-v1"
    assert payload["reportSchemaVersion"] == "probe-report/v2"
    assert payload["report"]["target"]["objectVersion"] == "v2.0.0"
    assert payload["executionManifest"]["skill"]["key"] == "platform-default"
    assert payload["executionManifestHash"] == "c" * 64
    assert payload["triggerCompare"]["order"] == "after"
    assert payload["triggerCompare"]["versionState"] == "exact"
    assert payload["triggerCompare"]["objectTriggerAt"] is not None
    assert payload["triggerCompare"]["caseTriggerAt"] is not None
    assert payload["warnings"] == []


async def test_attribution_detail_exposes_evidence_warnings(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """Legacy or uncomparable evidence surfaces fixed warning codes."""
    legacy = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions/{PROBE_OLD}",
        headers=attribution_api.admin,
    )
    assert legacy.status_code == 200
    payload = legacy.json()
    assert payload["triggerCompare"]["order"] == "unknown"
    assert payload["triggerCompare"]["versionState"] == "exact"
    assert [warning["code"] for warning in payload["warnings"]] == [
        "ATTRIBUTION_TRIGGER_UNKNOWN",
        "ATTRIBUTION_RUN_UNKNOWN",
    ]


async def test_attribution_detail_compares_coordinates_without_times(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """Mixed timestamp availability falls back to tree/event coordinates."""
    response = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions/{PROBE_COORD}",
        headers=attribution_api.admin,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["triggerCompare"] == {
        "objectTriggerAt": None,
        "caseTriggerAt": None,
        "order": "after",
        "versionState": "unknown",
    }
    assert [warning["code"] for warning in payload["warnings"]] == [
        "ATTRIBUTION_VERSION_UNKNOWN",
        "ATTRIBUTION_LEGACY_IMPORT",
        "ATTRIBUTION_RUN_UNKNOWN",
    ]


async def test_attribution_detail_hides_cross_case_and_missing_items(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """A probe linked to another case behaves as if it does not exist."""
    cross = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions/{PROBE_CROSS}",
        headers=attribution_api.admin,
    )
    missing = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions/m11-missing",
        headers=attribution_api.admin,
    )
    assert cross.status_code == 404
    assert cross.json()["error"]["code"] == "ATTRIBUTION_NOT_FOUND"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ATTRIBUTION_NOT_FOUND"


async def test_attribution_reads_reject_unknown_and_unowned_cases(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """A case outside the workspace projection answers 404 before any rows."""
    unknown = await attribution_api.client.get(
        "/api/workspaces/ws-default/bad-cases/m11-missing/attributions",
        headers=attribution_api.admin,
    )
    unowned = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE_OTHER_WS}/attributions",
        headers=attribution_api.admin,
    )
    other_route = await attribution_api.client.get(
        f"/api/workspaces/{attribution_api.other_workspace}/bad-cases/{CASE}/attributions",
        headers=attribution_api.admin,
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"
    assert unowned.status_code == 404
    assert unowned.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"
    assert other_route.status_code == 404
    assert other_route.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"


async def test_outsider_cannot_read_another_workspace_attributions(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """Workspace membership gates the attribution routes like other reads."""
    response = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions",
        headers=attribution_api.outsider,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_empty_case_returns_an_empty_page(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """A case without linked probes is an empty page, not a 404."""
    response = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE_EMPTY}/attributions",
        headers=attribution_api.admin,
    )
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "pageSize": 2}


async def test_page_parameters_are_validated(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """Page numbers and page sizes keep the documented closed range."""
    base = f"/api/workspaces/ws-default/bad-cases/{CASE}/attributions"
    for params in ({"page": 0}, {"pageSize": 0}, {"pageSize": 51}):
        response = await attribution_api.client.get(
            base,
            headers=attribution_api.admin,
            params=params,
        )
        assert response.status_code == 422, params


async def test_bad_case_exposes_distinct_attribution_count(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """The count is distinct object/revision identities, not link rows."""
    response = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE}",
        headers=attribution_api.admin,
    )
    empty = await attribution_api.client.get(
        f"/api/workspaces/ws-default/bad-cases/{CASE_EMPTY}",
        headers=attribution_api.admin,
    )
    legacy_list = await attribution_api.client.get(
        f"/api/sessions/{SESSION}/bad-cases",
        headers=attribution_api.admin,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["attributionCount"] == 3
    assert payload["hasAttribution"] is True
    assert empty.json()["attributionCount"] == 0
    assert empty.json()["hasAttribution"] is False
    listed = next(item for item in legacy_list.json()["items"] if item["badCaseId"] == CASE)
    assert listed["attributionCount"] == 3
    assert listed["hasAttribution"] is True


async def test_legacy_analysis_and_probe_reads_keep_working(
    attribution_api: AttributionApiEnvironment,
) -> None:
    """The compatibility endpoints still read the same external rows."""
    analysis = await attribution_api.client.get(
        f"/api/bad-cases/{CASE}/analysis",
        headers=attribution_api.admin,
    )
    probe = await attribution_api.client.get(
        f"/api/probes/{PROBE_OLD}",
        headers=attribution_api.admin,
    )
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "analyzed_issue"
    assert probe.status_code == 200
    assert probe.json()["probeId"] == PROBE_OLD


def _candidate(
    *,
    order_state: str = "comparable",
    object_at: datetime | None = None,
    case_at: datetime | None = None,
    object_tree: int | None = None,
    object_event: int | None = None,
    case_tree: int | None = None,
    case_event: int | None = None,
) -> CandidateTriggerRecord:
    """Build one candidate trigger snapshot for comparison unit cases."""
    return CandidateTriggerRecord(
        order_state=order_state,
        object_trigger_at=object_at,
        case_trigger_at=case_at,
        object_trigger_tree_index=object_tree,
        object_trigger_event_index=object_event,
        case_trigger_tree_index=case_tree,
        case_trigger_event_index=case_event,
    )


def test_trigger_order_covers_equal_before_and_uncomparable_evidence() -> None:
    """Timestamp equality and coordinate ordering both drive the closed set."""
    assert _trigger_order(None) == "unknown"
    assert _trigger_order(_candidate(order_state="unknown")) == "unknown"
    assert _trigger_order(_candidate(object_at=NOW, case_at=NOW)) == "same"
    assert _trigger_order(_candidate(object_at=NEW_AT, case_at=NOW)) == "before"
    assert (
        _trigger_order(
            _candidate(
                object_tree=1,
                object_event=2,
                case_tree=0,
                case_event=9,
            ),
        )
        == "before"
    )
    assert (
        _trigger_order(
            _candidate(
                object_tree=0,
                object_event=1,
                case_tree=0,
                case_event=1,
            ),
        )
        == "same"
    )
    assert _trigger_order(_candidate(object_tree=0, case_tree=0)) == "unknown"
