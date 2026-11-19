"""Read-model API exposes post-process anchors and the closed kind vocabulary."""

from __future__ import annotations

from tests.m10_02_potential_support import (
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    PreviewApi,
    seed_case,
    seed_event,
    seed_session,
)

SESSION_ID = "session-m13-anchor-api"


async def _seed_unmatched_skill_case(api: PreviewApi) -> None:
    """Seed one resolved reporter whose reported skill has no trigger record."""
    main_id = await seed_session(api.database, session_id=SESSION_ID, started_at=NOW)
    await seed_event(
        api.database,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=NOW,
    )
    await seed_case(
        api.database,
        case_id="case-m13-anchor-api",
        session_id=SESSION_ID,
        case_type="discovery",
        object_name="missing-skill",
        created_at=NOW,
    )


async def test_tree_problem_anchor_reports_post_process(
    preview_api: PreviewApi,
) -> None:
    """eventIndex=INT_MAX and kind=post_process replace the old -1 fallback."""
    await _seed_unmatched_skill_case(preview_api)

    response = await preview_api.client.get(
        f"/api/workspaces/{preview_api.workspace_id}/sessions/{SESSION_ID}/tree",
        headers=preview_api.reader,
    )

    assert response.status_code == 200
    case = response.json()["badCases"][0]
    assert case["anchor"] == {
        "agentId": case["anchor"]["agentId"],
        "eventIndex": 2_147_483_647,
        "kind": "post_process",
    }


async def test_problem_list_anchor_reports_post_process(
    preview_api: PreviewApi,
) -> None:
    """The session problem list shares the same anchor semantics as the tree."""
    await _seed_unmatched_skill_case(preview_api)

    response = await preview_api.client.get(
        f"/api/sessions/{SESSION_ID}/bad-cases",
        headers=preview_api.reader,
    )

    assert response.status_code == 200
    anchor = response.json()["items"][0]["anchor"]
    assert anchor["eventIndex"] == 2_147_483_647
    assert anchor["kind"] == "post_process"
