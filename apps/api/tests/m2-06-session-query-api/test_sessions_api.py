"""HTTP and read-model contracts for the session query API."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import update

from app.db.crud.sessions import SessionRepository
from app.db.models.domain import agent_events, agents, bad_cases, session_families
from app.service.sessions.service import SessionService

SESSION_1 = "10000000-0000-4000-8000-000000000001"
SESSION_2 = "10000000-0000-4000-8000-000000000002"
SESSION_3 = "10000000-0000-4000-8000-000000000003"
SESSION_4 = "10000000-0000-4000-8000-000000000004"
AGENT_1 = "agent-s1-review-0001"
WORKFLOW = "wf_9e88822acbfcd60c0837bf523793af78"
WORKFLOW_AGENT = "agent-s2-worker-0001"


async def test_list_requires_auth_and_returns_backend_aggregates(
    session_query: Any,
) -> None:
    """The authenticated list returns the complete source-of-truth card model."""
    unauthenticated = await session_query.client.get("/api/sessions")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTH_REQUIRED"

    response = await session_query.client.get(
        "/api/sessions",
        headers=session_query.authorization,
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [SESSION_4, SESSION_3, SESSION_2, SESSION_1]
    assert items[0] == {
        "id": SESSION_4,
        "short": "示例最小会话",
        "title": "示例会话四：最小主会话",  # noqa: RUF001
        "repo": "minimal-repo",
        "model": "claude-sonnet-synthetic",
        "startedAt": "2026-10-23T12:00:00+08:00",
        "durationSeconds": 60,
        "status": "ok",
        "skills": [],
        "stats": {
            "userTurns": 1,
            "messages": 1,
            "tools": 0,
            "errors": 0,
            "agents": 0,
            "badCases": 1,
            "tokens": 40,
            "failPer100Messages": 0.0,
            "badCasesPer100Messages": 100.0,
        },
    }


async def test_list_search_status_sort_limit_and_validation(
    session_query: Any,
) -> None:
    """Filters use canonical search text, escaped wildcards, and stable sorts."""
    async with session_query.database.transaction() as session:
        await session.execute(
            update(session_families)
            .where(session_families.c.id == SESSION_1)
            .values(user_turns_count=4, messages_count=10, agents_count=5),
        )
        await session.execute(
            update(session_families)
            .where(session_families.c.id == SESSION_2)
            .values(user_turns_count=3, messages_count=5, agents_count=4),
        )
        await session.execute(
            update(session_families)
            .where(session_families.c.id == SESSION_3)
            .values(user_turns_count=2, messages_count=20, agents_count=3),
        )
        await session.execute(
            update(session_families)
            .where(session_families.c.id == SESSION_4)
            .values(
                user_turns_count=1,
                messages_count=1,
                agents_count=0,
                status="fail",
            ),
        )

    base = "/api/sessions"
    headers = session_query.authorization

    problem = await session_query.client.get(
        f"{base}?status=problem",
        headers=headers,
    )
    assert [item["id"] for item in problem.json()["items"]] == [SESSION_4, SESSION_3]

    search = await session_query.client.get(
        f"{base}?q=WORKFLOW",
        headers=headers,
    )
    assert [item["id"] for item in search.json()["items"]] == [SESSION_2]

    wildcard = await session_query.client.get(f"{base}?q=%25", headers=headers)
    assert wildcard.json()["items"] == []
    underscore = await session_query.client.get(f"{base}?q=_", headers=headers)
    assert underscore.json()["items"] == []

    for sort, expected in {
        "userTurns": [SESSION_1, SESSION_2, SESSION_3, SESSION_4],
        "messages": [SESSION_3, SESSION_1, SESSION_2, SESSION_4],
        "agents": [SESSION_1, SESSION_2, SESSION_3, SESSION_4],
    }.items():
        response = await session_query.client.get(
            f"{base}?sort={sort}&limit=3",
            headers=headers,
        )
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == expected[:3]

    invalid_status = await session_query.client.get(
        f"{base}?status=broken",
        headers=headers,
    )
    invalid_sort = await session_query.client.get(
        f"{base}?sort=bad",
        headers=headers,
    )
    too_large = await session_query.client.get(f"{base}?limit=501", headers=headers)
    zero = await session_query.client.get(f"{base}?limit=0", headers=headers)
    assert invalid_status.status_code == 422
    assert invalid_sort.status_code == 422
    assert too_large.status_code == 422
    assert zero.status_code == 422


async def test_overview_is_list_shape_and_missing_session_is_stable(
    session_query: Any,
) -> None:
    """Overview reuses the list item and uses the closed session-not-found code."""
    listed = await session_query.client.get(
        "/api/sessions",
        headers=session_query.authorization,
    )
    expected = next(item for item in listed.json()["items"] if item["id"] == SESSION_1)

    overview = await session_query.client.get(
        f"/api/sessions/{SESSION_1}",
        headers=session_query.authorization,
    )
    missing = await session_query.client.get(
        "/api/sessions/ffffffff-ffff-4fff-8fff-ffffffffffff",
        headers=session_query.authorization,
    )

    assert overview.status_code == 200
    assert overview.json() == expected
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SESSION_NOT_FOUND"


async def test_tree_returns_flat_agents_events_and_bad_case_anchors(
    session_query: Any,
) -> None:
    """Tree fields map directly to the prototype execution-flow contract."""
    response = await session_query.client.get(
        f"/api/sessions/{SESSION_1}/tree",
        headers=session_query.authorization,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sessionId"] == SESSION_1
    assert [agent["agentId"] for agent in payload["agents"]] == [SESSION_1, AGENT_1]

    main, child = payload["agents"]
    assert main == {
        "agentId": SESSION_1,
        "parentAgentId": None,
        "kind": "main",
        "agentType": "claude",
        "taskKind": None,
        "teamName": None,
        "skillName": None,
        "label": "主会话",
        "desc": "",
        "toolUseId": None,
        "spawnDepth": 0,
        "lines": 2,
        "messagesCount": 1,
        "events": [
            {
                "line": 2,
                "kind": "agent",
                "name": "Explore",
                "desc": "检查合成路径",
                "toolUseId": "tool-agent-1",
                "messageOffset": 0,
            },
        ],
    }
    assert child["parentAgentId"] == SESSION_1
    assert child["label"] == "Explore"
    assert child["toolUseId"] == "tool-agent-1"
    assert payload["badCases"] == [
        {
            "badCaseId": "badcase-synthetic-0001",
            "badCaseType": "self",
            "objectName": "Explore",
            "objectType": "agent",
            "objectVersion": "synthetic-1",
            "anchor": {"agentId": AGENT_1, "eventIndex": -1},
            "badCaseAgent": {"sessionId": SESSION_1, "agentId": AGENT_1},
            "reason": "合成示例：检查结论缺少目标文件。",  # noqa: RUF001
        },
        {
            "badCaseId": "badcase-synthetic-0005",
            "badCaseType": "discovery",
            "objectName": "Explore",
            "objectType": "agent",
            "objectVersion": "synthetic-1",
            "anchor": {"agentId": SESSION_1, "eventIndex": 0},
            "badCaseAgent": {"sessionId": SESSION_1, "agentId": AGENT_1},
            "reason": "合成示例：推理步骤越过工具边界。",  # noqa: RUF001
        },
    ]

    workflow_tree = await session_query.client.get(
        f"/api/sessions/{SESSION_2}/tree",
        headers=session_query.authorization,
    )
    workflow_payload = workflow_tree.json()
    assert [agent["agentId"] for agent in workflow_payload["agents"]] == [
        SESSION_2,
        WORKFLOW,
        WORKFLOW_AGENT,
    ]
    workflow = workflow_payload["agents"][1]
    assert workflow["kind"] == "workflow"
    assert workflow["parentAgentId"] == SESSION_2
    assert workflow["toolUseId"] == "tool-wf-1"
    assert workflow_payload["badCases"][0]["anchor"] == {
        "agentId": SESSION_2,
        "eventIndex": -1,
    }
    assert workflow_payload["badCases"][0]["badCaseAgent"] == {
        "sessionId": SESSION_2,
        "agentId": WORKFLOW_AGENT,
    }


async def test_tree_missing_session_and_timeline_endpoint_are_absent(
    session_query: Any,
) -> None:
    """Unknown sessions and the retired timeline route are stable 404 responses."""
    missing_tree = await session_query.client.get(
        "/api/sessions/ffffffff-ffff-4fff-8fff-ffffffffffff/tree",
        headers=session_query.authorization,
    )
    timeline = await session_query.client.get(
        f"/api/sessions/{SESSION_1}/timeline",
        headers=session_query.authorization,
    )

    assert missing_tree.status_code == 404
    assert missing_tree.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert timeline.status_code == 404


async def test_tree_resolves_skill_and_discovery_agent_anchors(
    session_query: Any,
) -> None:
    """Skill and discovery anchors use the reported Agent's trigger history."""
    async with session_query.database.transaction() as session:
        await session.execute(
            update(agent_events)
            .where(
                agent_events.c.agent_id == SESSION_3,
                agent_events.c.event_index == 0,
            )
            .values(event_index=5),
        )

    skill_tree = await session_query.client.get(
        f"/api/sessions/{SESSION_3}/tree",
        headers=session_query.authorization,
    )
    skill_case = skill_tree.json()["badCases"][0]
    skill_agent = next(
        agent for agent in skill_tree.json()["agents"] if agent["agentId"] == SESSION_3
    )
    assert len(skill_agent["events"]) == 1
    assert skill_agent["events"][0]["kind"] == "skill"
    assert skill_case["anchor"] == {"agentId": SESSION_3, "eventIndex": 0}
    assert skill_case["badCaseAgent"] == {
        "sessionId": SESSION_3,
        "agentId": None,
    }

    async with session_query.database.transaction() as session:
        await session.execute(
            update(agent_events)
            .where(
                agent_events.c.agent_id == SESSION_1,
                agent_events.c.event_index == 0,
            )
            .values(event_index=7),
        )
        await session.execute(
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == "badcase-synthetic-0001")
            .values(bad_case_type="discovery"),
        )

    discovery_tree = await session_query.client.get(
        f"/api/sessions/{SESSION_1}/tree",
        headers=session_query.authorization,
    )
    discovery_case = discovery_tree.json()["badCases"][0]
    assert discovery_case["anchor"] == {
        "agentId": SESSION_1,
        "eventIndex": 0,
    }


async def test_tree_warns_when_reporter_agent_is_unknown(
    session_query: Any,
    caplog: Any,
) -> None:
    """Unknown reporters keep their reported id while the anchor degrades to main."""
    async with session_query.database.transaction() as session:
        await session.execute(
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == "badcase-synthetic-0001")
            .values(bad_case_agent_id="missing-reporter"),
        )

    with caplog.at_level(logging.WARNING, logger="app.service.sessions.service"):
        response = await session_query.client.get(
            f"/api/sessions/{SESSION_1}/tree",
            headers=session_query.authorization,
        )

    case = response.json()["badCases"][0]
    assert case["anchor"] == {"agentId": SESSION_1, "eventIndex": -1}
    assert case["badCaseAgent"]["agentId"] == "missing-reporter"
    assert "bad case reporter Agent was not found" in caplog.text


async def test_tree_unknown_skill_reporter_does_not_borrow_main_trigger(
    session_query: Any,
    caplog: Any,
) -> None:
    """A missing skill reporter anchors to main itself, never a same-name trigger."""
    async with session_query.database.transaction() as session:
        await session.execute(
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == "badcase-synthetic-0003")
            .values(bad_case_agent_id="missing-skill-reporter"),
        )

    with caplog.at_level(logging.WARNING, logger="app.service.sessions.service"):
        response = await session_query.client.get(
            f"/api/sessions/{SESSION_3}/tree",
            headers=session_query.authorization,
        )

    case = response.json()["badCases"][0]
    assert case["anchor"] == {"agentId": SESSION_3, "eventIndex": -1}
    assert case["badCaseAgent"]["agentId"] == "missing-skill-reporter"
    assert "bad case reporter Agent was not found" in caplog.text


async def test_tree_uses_one_repository_session_for_a_consistent_snapshot(
    session_query: Any,
    monkeypatch: Any,
) -> None:
    """Family, agents, events, and bad cases come from one read transaction."""
    original_session = session_query.database.session
    session_count = 0

    @asynccontextmanager
    async def counted_session() -> AsyncIterator[Any]:
        nonlocal session_count
        session_count += 1
        async with original_session() as session:
            yield session

    monkeypatch.setattr(session_query.database, "session", counted_session)
    service = SessionService(SessionRepository(session_query.database))

    tree = await service.tree(SESSION_1)

    assert tree.session_id == SESSION_1
    assert len(tree.agents) == 2
    assert session_count == 1


async def test_tree_rejects_unsupported_persisted_task_kind(
    session_query: Any,
) -> None:
    """An invalid persisted task kind fails closed through the shared envelope."""
    async with session_query.database.transaction() as session:
        await session.execute(
            update(agents)
            .where(agents.c.id == AGENT_1)
            .values(task_kind="unsupported-provider-task"),
        )

    response = await session_query.client.get(
        f"/api/sessions/{SESSION_1}/tree",
        headers=session_query.authorization,
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL",
            "message": "session tree has an unsupported task kind",
            "details": {},
        },
    }
    assert "unsupported-provider-task" not in response.text
