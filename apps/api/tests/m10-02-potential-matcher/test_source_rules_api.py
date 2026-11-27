"""Workspace API integration for the two-step editor and its per-card report list."""

from datetime import timedelta

from app.db.crud.evolution_targets import EvolutionTargetRepository
from tests.m10_02_potential_support import NOW, PreviewApi, seed_case, seed_event, seed_session


async def test_report_source_and_later_target(preview_api: PreviewApi) -> None:
    api = preview_api
    base = f"/api/workspaces/{api.workspace_id}/evolution"
    window = {"from": "2026-11-01", "to": "2026-11-30"}
    client = api.client
    session_id = "source-later-target"
    main = await seed_session(api.database, session_id=session_id)
    for index, name in enumerate(["C", "A", "C"]):
        await seed_event(
            api.database,
            agent_id=main,
            event_index=index,
            kind="skill",
            name=name,
            triggered_at=NOW + timedelta(minutes=index),
        )
    await seed_case(
        api.database, case_id="A-self", session_id=session_id, object_name="A", case_type="self"
    )
    rule = {"kind": "skill", "name": "A", "types": ["self"], "relation": "after"}
    policy = {"mode": "custom", "rules": [rule]}
    body = {
        "objectName": "C",
        "objectType": "skill",
        "repoUrl": "https://example.com/c.git",
        "subDir": "c",
        "defaultRef": "v1",
        "validationProjectId": "val",
        "testProjectId": "test",
        "primaryMetricKey": "score",
        "candidatePolicy": policy,
    }
    missing = {"mode": "custom", "rules": [{**rule, "name": "unused"}]}
    invalid = await client.post(
        base + "/targets", json={**body, "candidatePolicy": missing}, headers=api.admin
    )
    assert invalid.status_code == 422
    targets = EvolutionTargetRepository(api.database)
    assert await targets.find("skill", "C", workspace_ids=[api.workspace_id]) is None
    created = await client.post(base + "/targets", json=body, headers=api.admin)
    assert created.status_code == 201 and created.json()["candidatePolicy"] == policy
    url = base + "/targets/" + created.json()["id"] + "/candidate-policy"
    assert (await client.put(url, json=missing, headers=api.reader)).status_code == 403
    assert (await client.put(url, json=missing, headers=api.admin)).status_code == 422
    assert (
        await client.get(base + "/candidate-sources", params=window, headers=api.reader)
    ).json() == [{"kind": "skill", "name": "A", "selfCount": 1, "discoveryCount": 0}]
    reports = await client.get(
        base + "/candidate-source-reports",
        params={**window, "name": "A", "kind": "skill", "types": "self"},
        headers=api.reader,
    )
    assert reports.status_code == 200 and reports.json()["items"][0]["id"] == "A-self"
    preview = await client.post(
        base + "/preview/potential",
        json={**window, "targetType": "skill", "targetName": "C"},
        headers=api.reader,
    )
    assert preview.status_code == 200, preview.text
    assert [(r["badCaseId"], r["hitReason"]) for r in preview.json()["items"]] == [
        ("A-self", "custom_source")
    ]
    cleared = await client.put(url, json={"mode": "default", "rules": []}, headers=api.admin)
    assert cleared.status_code == 200 and cleared.json()["rules"] == []
