"""Preview endpoints: permissions, paging, error matrix, and read-only behavior."""

from __future__ import annotations

from datetime import datetime

import httpx

from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.db.models.evolution import evolution_run_candidates
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    LATER,
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    WORKSPACE_B,
    PreviewApi,
    seed_case,
    seed_event,
    seed_probe,
    seed_session,
    seed_target,
    table_count,
)

OBJECT_ENTRY = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)
CASE_AFTER = datetime(2026, 11, 17, 10, 30, tzinfo=SHANGHAI)
WINDOW = {"from": "2026-11-01", "to": "2026-11-30"}


def path(api: PreviewApi, stage: str, workspace_id: str | None = None) -> str:
    """Return one workspace preview endpoint path."""
    return f"/api/workspaces/{workspace_id or api.workspace_id}/evolution/preview/{stage}"


def body(
    *,
    target_type: str = "skill",
    target_name: str = TARGET_NAME,
    target_version: str | None = TARGET_VERSION,
    **extra: object,
) -> dict[str, object]:
    """Build one preview request with the shared condition."""
    payload: dict[str, object] = {
        "targetType": target_type,
        "targetName": target_name,
        **WINDOW,
        **extra,
    }
    if target_version is not None:
        payload["targetVersion"] = target_version
    return payload


def error_code(response: httpx.Response) -> str:
    """Read the stable error code from the shared envelope."""
    return str(response.json()["error"]["code"])


async def seed_associated(
    api: PreviewApi,
    *,
    session_id: str,
    entry_at: datetime = OBJECT_ENTRY,
    version: str | None = TARGET_VERSION,
) -> str:
    """Seed one session with a matching object entry and return its main Agent id."""
    main_id = await seed_session(
        api.database,
        session_id=session_id,
        started_at=NOW,
        title=session_id,
    )
    await seed_event(
        api.database,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=version,
        triggered_at=entry_at,
    )
    return main_id


async def test_preview_requires_authentication_and_workspace_membership(
    preview_api: PreviewApi,
) -> None:
    """Preview is viewer-readable, 401 without a token, and 404 outside the space."""
    await seed_associated(preview_api, session_id="session-auth")
    await seed_case(
        preview_api.database,
        case_id="case-auth",
        session_id="session-auth",
        case_type="self",
        object_name=TARGET_NAME,
        created_at=LATER,
    )

    anonymous = await preview_api.client.post(
        path(preview_api, "sessions"),
        json=body(),
    )
    outsider = await preview_api.client.post(
        path(preview_api, "sessions", WORKSPACE_B),
        headers=preview_api.reader,
        json=body(),
    )
    readable = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(),
    )

    assert anonymous.status_code == 401
    assert outsider.status_code == 404
    assert error_code(outsider) == "WORKSPACE_NOT_FOUND"
    assert readable.status_code == 200


async def test_sessions_preview_partitions_and_paginates(preview_api: PreviewApi) -> None:
    """Step 2 returns the non-overlapping partition and 4 rows per page."""
    for index in range(6):
        session_id = f"session-associated-{index}"
        await seed_associated(
            preview_api,
            session_id=session_id,
            entry_at=datetime(2026, 11, 17, 10, index, tzinfo=SHANGHAI),
        )
        await seed_case(
            preview_api.database,
            case_id=f"case-associated-{index}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )

    unresolved_main = await seed_session(
        preview_api.database,
        session_id="session-unresolved",
        started_at=NOW,
    )
    await seed_event(
        preview_api.database,
        agent_id=unresolved_main,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=None,
        triggered_at=OBJECT_ENTRY,
    )
    skipped_main = await seed_session(
        preview_api.database,
        session_id="session-skipped",
        started_at=NOW,
    )
    await seed_event(
        preview_api.database,
        agent_id=skipped_main,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version="v1.0.0",
        triggered_at=OBJECT_ENTRY,
    )
    for session_id in ("session-unresolved", "session-skipped", "session-pending"):
        await seed_case(
            preview_api.database,
            case_id=f"case-{session_id}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )

    first = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(pageSize=4),
    )
    second = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(page=2, pageSize=4),
    )

    assert first.status_code == 200
    payload = first.json()
    assert payload["summary"] == {
        "reported": 9,
        "associated": 6,
        "skipped": 1,
        "versionUnresolved": 1,
        "pending": 1,
    }
    assert payload["total"] == 6
    assert len(payload["items"]) == 4
    assert payload["pageSize"] == 4
    assert set(payload["items"][0]) == {
        "sessionId",
        "title",
        "objectTriggerAt",
        "badCaseCount",
        "potentialCount",
    }
    assert second.status_code == 200
    assert len(second.json()["items"]) == 2


async def test_potential_preview_paginates_included_rows_and_reports_reasons(
    preview_api: PreviewApi,
) -> None:
    """Step 3 pages only included cases while byReason keeps excluded counts."""
    session_id = "session-potential"
    main_id = await seed_associated(preview_api, session_id=session_id)
    await seed_event(
        preview_api.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="early-skill",
        triggered_at=datetime(2026, 11, 17, 8, 30, tzinfo=SHANGHAI),
    )
    for index in range(6):
        await seed_case(
            preview_api.database,
            case_id=f"case-potential-{index}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )
    for index in range(2):
        await seed_case(
            preview_api.database,
            case_id=f"case-excluded-{index}",
            session_id=session_id,
            object_name="early-skill",
            created_at=LATER,
        )

    first = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(),
    )
    second = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(page=2),
    )

    assert first.status_code == 200
    payload = first.json()
    assert payload["summary"] == {
        "badCases": 8,
        "potential": 6,
        "byReason": {
            "selfReport": 6,
            "afterObject": 0,
            "both": 0,
            "policyExcluded": 2,
            "orderUnknown": 0,
        },
    }
    assert payload["total"] == 6
    assert payload["pageSize"] == 5
    assert len(payload["items"]) == 5
    assert set(payload["items"][0]) == {
        "badCaseId",
        "objectName",
        "badCaseType",
        "triggerAt",
        "sessionId",
        "hitReason",
        "orderState",
    }
    assert payload["items"][0]["hitReason"] == "self_report"
    assert payload["items"][0]["orderState"] == "comparable"
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1


async def test_attribution_preview_counts_cache_and_non_target(
    preview_api: PreviewApi,
) -> None:
    """Step 4 reports exact cache reuse and honors cacheEnabled=false."""
    session_id = "session-attribution-api"
    main_id = await seed_associated(preview_api, session_id=session_id)
    await seed_event(
        preview_api.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="early-skill",
        triggered_at=datetime(2026, 11, 17, 8, 30, tzinfo=SHANGHAI),
    )
    for index in range(3):
        await seed_case(
            preview_api.database,
            case_id=f"case-cache-{index}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )
    await seed_case(
        preview_api.database,
        case_id="case-non-target",
        session_id=session_id,
        object_name="early-skill",
        created_at=LATER,
    )
    await seed_probe(
        preview_api.database,
        case_id="case-cache-0",
        session_id=session_id,
        conclusion="attributed",
    )
    await seed_probe(
        preview_api.database,
        case_id="case-cache-1",
        session_id=session_id,
        conclusion="attributed",
    )
    await seed_probe(
        preview_api.database,
        case_id="case-non-target",
        session_id=session_id,
        conclusion="non_target",
    )

    enabled = await preview_api.client.post(
        path(preview_api, "attribution"),
        headers=preview_api.reader,
        json=body(cacheEnabled=True),
    )
    disabled = await preview_api.client.post(
        path(preview_api, "attribution"),
        headers=preview_api.reader,
        json=body(cacheEnabled=False),
    )

    assert enabled.status_code == 200
    assert enabled.json() == {
        "summary": {
            "potential": 3,
            "reused": 2,
            "fresh": 1,
            "nonTargetKnown": 1,
        },
    }
    assert disabled.status_code == 200
    assert disabled.json()["summary"]["reused"] == 0
    assert disabled.json()["summary"]["fresh"] == 3


async def test_target_not_configured_or_disabled_returns_409(preview_api: PreviewApi) -> None:
    """A missing or disabled workspace target is the same stable 409."""
    await seed_target(
        preview_api.database,
        target_id="target-disabled",
        object_name="disabled-target",
        enabled=False,
    )
    missing = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(target_name="unknown-target"),
    )
    disabled = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(target_name="disabled-target"),
    )

    assert missing.status_code == 409
    assert error_code(missing) == "TARGET_NOT_CONFIGURED"
    assert disabled.status_code == 409
    assert error_code(disabled) == "TARGET_NOT_CONFIGURED"


async def test_policy_invalid_returns_422(preview_api: PreviewApi) -> None:
    """Default switches, missing custom switches, and empty rules are 422."""
    default_switch = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(policy={"preset": "default", "includeSelfReport": True}),
    )
    missing_switch = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(
            policy={
                "preset": "custom",
                "includeSelfReport": True,
                "includeAfterObject": True,
            },
        ),
    )
    no_rule = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(
            policy={
                "preset": "custom",
                "includeSelfReport": False,
                "includeAfterObject": False,
                "sameObjectOnly": True,
            },
        ),
    )

    for response in (default_switch, missing_switch, no_rule):
        assert response.status_code == 422
        assert error_code(response) == "POLICY_INVALID"


async def test_window_invalid_returns_422(preview_api: PreviewApi) -> None:
    """An inverted or oversized window is rejected before any query."""
    inverted = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(**{"from": "2026-11-30", "to": "2026-11-01"}),
    )
    oversized = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(**{"from": "2025-01-01", "to": "2026-11-01"}),
    )

    for response in (inverted, oversized):
        assert response.status_code == 422
        assert error_code(response) == "WINDOW_INVALID"


async def test_no_associated_sessions_returns_409(preview_api: PreviewApi) -> None:
    """A configured target with no object event in the window is a 409."""
    main_id = await seed_session(
        preview_api.database,
        session_id="session-no-object",
        started_at=NOW,
    )
    await seed_event(
        preview_api.database,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name="another-object",
        object_version=TARGET_VERSION,
        triggered_at=OBJECT_ENTRY,
    )
    await seed_case(
        preview_api.database,
        case_id="case-no-object",
        session_id="session-no-object",
        case_type="self",
        object_name=TARGET_NAME,
        created_at=LATER,
    )

    for stage in ("sessions", "potential", "attribution"):
        response = await preview_api.client.post(
            path(preview_api, stage),
            headers=preview_api.reader,
            json=body(),
        )
        assert response.status_code == 409
        assert error_code(response) == "NO_ASSOCIATED_SESSIONS"


async def test_no_potential_matched_returns_409(preview_api: PreviewApi) -> None:
    """An associated Session with zero included cases is a 409 for steps 3 and 4."""
    session_id = "session-no-potential"
    main_id = await seed_associated(preview_api, session_id=session_id, entry_at=CASE_AFTER)
    await seed_event(
        preview_api.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="early-skill",
        triggered_at=datetime(2026, 11, 17, 8, 30, tzinfo=SHANGHAI),
    )
    await seed_case(
        preview_api.database,
        case_id="case-no-potential",
        session_id=session_id,
        object_name="early-skill",
        created_at=LATER,
    )

    sessions = await preview_api.client.post(
        path(preview_api, "sessions"),
        headers=preview_api.reader,
        json=body(),
    )
    potential = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(),
    )
    attribution = await preview_api.client.post(
        path(preview_api, "attribution"),
        headers=preview_api.reader,
        json=body(),
    )

    assert sessions.status_code == 200
    assert sessions.json()["items"][0]["potentialCount"] == 0
    for response in (potential, attribution):
        assert response.status_code == 409
        assert error_code(response) == "NO_POTENTIAL_MATCHED"


async def test_unknown_custom_policy_edge_and_engine_are_422(preview_api: PreviewApi) -> None:
    """An unregistered engine key is rejected before association or cache reads."""
    response = await preview_api.client.post(
        path(preview_api, "attribution"),
        headers=preview_api.reader,
        json=body(engineKey="missing-engine"),
    )

    assert response.status_code == 422
    assert error_code(response) == "ENGINE_INVALID"


async def test_knowledge_target_is_configurable_and_previewable(preview_api: PreviewApi) -> None:
    """The target API accepts knowledge and the matcher associates its events."""
    created = await preview_api.client.post(
        f"/api/workspaces/{preview_api.workspace_id}/evolution/targets",
        headers=preview_api.admin,
        json={
            "objectType": "knowledge",
            "objectName": "Runbook",
            "repoUrl": "https://example.invalid/kb.git",
            "subDir": "knowledge",
            "defaultRef": "rev-1",
            "validationProjectId": "validation",
            "testProjectId": "test",
            "enabled": True,
        },
    )
    session_id = "session-knowledge-api"
    main_id = await seed_session(
        preview_api.database,
        session_id=session_id,
        started_at=NOW,
    )
    await seed_event(
        preview_api.database,
        agent_id=main_id,
        event_index=0,
        kind="knowledge",
        name="Runbook",
        object_version="rev-1",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_case(
        preview_api.database,
        case_id="case-knowledge-api",
        session_id=session_id,
        case_type="self",
        object_name="Runbook",
        created_at=LATER,
    )

    preview = await preview_api.client.post(
        path(preview_api, "potential"),
        headers=preview_api.reader,
        json=body(target_type="knowledge", target_name="Runbook", target_version="rev-1"),
    )

    assert created.status_code == 201
    assert created.json()["objectType"] == "knowledge"
    assert preview.status_code == 200
    assert preview.json()["summary"]["potential"] == 1


async def test_preview_endpoints_are_read_only(preview_api: PreviewApi) -> None:
    """All three preview calls leave probes, links, candidates, and cases untouched."""
    session_id = "session-read-only-api"
    await seed_associated(preview_api, session_id=session_id)
    for index in range(2):
        await seed_case(
            preview_api.database,
            case_id=f"case-read-only-{index}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )
    await seed_probe(
        preview_api.database,
        case_id="case-read-only-0",
        session_id=session_id,
        conclusion="attributed",
    )
    before = {
        "probes": await table_count(preview_api.database, probe_reports),
        "links": await table_count(preview_api.database, bad_case_analysis),
        "candidates": await table_count(preview_api.database, evolution_run_candidates),
        "cases": await table_count(preview_api.database, bad_cases),
    }

    for stage in ("sessions", "potential", "attribution"):
        response = await preview_api.client.post(
            path(preview_api, stage),
            headers=preview_api.reader,
            json=body(),
        )
        assert response.status_code == 200

    after = {
        "probes": await table_count(preview_api.database, probe_reports),
        "links": await table_count(preview_api.database, bad_case_analysis),
        "candidates": await table_count(preview_api.database, evolution_run_candidates),
        "cases": await table_count(preview_api.database, bad_cases),
    }
    assert before == after
