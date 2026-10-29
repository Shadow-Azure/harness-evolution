"""HTTP contracts for read-only problems, analysis, and probes."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.fixtures import run_corpus_seed
from app.db.models.domain import bad_case_analysis, bad_cases
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app

ROOT = Path(__file__).resolve().parents[4]

SESSION_1 = "10000000-0000-4000-8000-000000000001"
SESSION_2 = "10000000-0000-4000-8000-000000000002"
SESSION_3 = "10000000-0000-4000-8000-000000000003"
SESSION_4 = "10000000-0000-4000-8000-000000000004"
CASE_1 = "badcase-synthetic-0001"
CASE_2 = "badcase-synthetic-0002"
CASE_4 = "badcase-synthetic-0004"
CASE_5 = "badcase-synthetic-0005"
PROBE_1 = "probe-synthetic-0001"
PROBE_3 = "probe-synthetic-0003"


@dataclass(frozen=True, slots=True)
class ProblemApiEnvironment:
    """Authenticated client plus its seeded application database."""

    client: httpx.AsyncClient
    app: Any
    database: Database
    authorization: dict[str, str]


@pytest_asyncio.fixture
async def problem_api(tmp_path: Path) -> AsyncIterator[ProblemApiEnvironment]:
    """Seed external fixtures and authenticate as a completed admin."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("problem-api-test-signing-secret-with-length"),
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
        yield ProblemApiEnvironment(
            client=client,
            app=app,
            database=app.state.database,
            authorization={
                "Authorization": f"Bearer {authenticated.json()['accessToken']}",
            },
        )


async def test_problem_routes_require_auth(problem_api: Any) -> None:
    """Every problem read is behind the central bearer gate."""
    for path in (
        f"/api/sessions/{SESSION_1}/bad-cases",
        f"/api/sessions/{SESSION_1}/probes",
        f"/api/bad-cases/{CASE_1}",
        f"/api/bad-cases/{CASE_1}/analysis",
        f"/api/probes/{PROBE_1}",
    ):
        response = await problem_api.client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_session_problem_list_has_full_public_shape_and_anchor(
    problem_api: Any,
) -> None:
    """The list combines session title, anchor, reporter, and analysis."""
    response = await problem_api.client.get(
        f"/api/sessions/{SESSION_1}/bad-cases",
        headers=problem_api.authorization,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["badCaseId"] for item in items] == [CASE_1, CASE_5]
    assert items[0] == {
        "badCaseId": CASE_1,
        "sessionId": SESSION_1,
        "sessionTitle": "示例会话一：主会话与评审子任务",  # noqa: RUF001
        "badCaseType": "self",
        "objectName": "Explore",
        "objectType": "agent",
        "objectVersion": "synthetic-1",
        "anchor": {"agentId": "agent-s1-review-0001", "eventIndex": -1},
        "badCaseAgent": {
            "sessionId": SESSION_1,
            "agentId": "agent-s1-review-0001",
        },
        "title": "检查结论缺少目标文件",
        "reason": "合成示例：检查结论缺少目标文件。",  # noqa: RUF001
        "metaData": {"fixture": True},
        "analysis": {
            "status": "analyzed_issue",
            "probeId": PROBE_1,
            "attributeType": "prompt",
            "displayState": "analyzed_issue_prompt",
            "result": {"summary": "提示缺少输出约束"},
        },
        "degraded": False,
        "diagnosticCode": None,
    }
    assert items[1]["anchor"] == {"agentId": SESSION_1, "eventIndex": 0}
    assert items[1]["badCaseAgent"]["agentId"] == "agent-s1-review-0001"


async def test_case_detail_analysis_and_session_mismatch(problem_api: Any) -> None:
    """Case detail supports deep-link ownership checks and analysis placeholder."""
    matching = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}?sessionId={SESSION_1}",
        headers=problem_api.authorization,
    )
    mismatch = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}?sessionId={SESSION_2}",
        headers=problem_api.authorization,
    )
    missing = await problem_api.client.get(
        "/api/bad-cases/missing",
        headers=problem_api.authorization,
    )
    analysis = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}/analysis?sessionId={SESSION_1}",
        headers=problem_api.authorization,
    )
    placeholder = await problem_api.client.get(
        f"/api/bad-cases/{CASE_4}/analysis",
        headers=problem_api.authorization,
    )

    assert matching.status_code == 200
    assert matching.json()["sessionTitle"].startswith("示例会话一")
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "BAD_CASE_SESSION_MISMATCH"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"
    assert analysis.status_code == 200
    assert analysis.json() == {
        "status": "analyzed_issue",
        "probeId": PROBE_1,
        "attributeType": "prompt",
        "displayState": "analyzed_issue_prompt",
        "result": {"summary": "提示缺少输出约束"},
    }
    assert placeholder.status_code == 200
    assert placeholder.json() == {
        "status": "unanalyzed",
        "probeId": None,
        "attributeType": None,
        "displayState": "unanalyzed",
        "result": None,
    }


async def test_empty_session_ownership_parameter_is_a_validation_error(
    problem_api: Any,
) -> None:
    """An explicitly empty deep-link Session id is malformed input, not a mismatch."""
    for path in (
        f"/api/bad-cases/{CASE_1}",
        f"/api/bad-cases/{CASE_1}/analysis",
    ):
        response = await problem_api.client.get(
            f"{path}?sessionId=",
            headers=problem_api.authorization,
        )
        assert response.status_code == 422, path
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_INVALID"
        assert body["error"]["message"] == "request validation failed"
        assert body["error"]["details"]["errors"][0]["loc"] == [
            "query",
            "sessionId",
        ]


async def test_missing_routes_and_remaining_anchor_semantics(problem_api: Any) -> None:
    """Missing Sessions/cases and skill/main anchors use stable public values."""
    missing_session = await problem_api.client.get(
        "/api/sessions/missing/bad-cases",
        headers=problem_api.authorization,
    )
    missing_analysis = await problem_api.client.get(
        "/api/bad-cases/missing/analysis",
        headers=problem_api.authorization,
    )
    skill = await problem_api.client.get(
        f"/api/sessions/{SESSION_3}/bad-cases",
        headers=problem_api.authorization,
    )
    main_discovery = await problem_api.client.get(
        f"/api/sessions/{SESSION_4}/bad-cases",
        headers=problem_api.authorization,
    )

    assert missing_session.status_code == 404
    assert missing_session.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert missing_analysis.status_code == 404
    assert missing_analysis.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"
    assert skill.json()["items"][0]["anchor"] == {
        "agentId": SESSION_3,
        "eventIndex": 0,
    }
    assert skill.json()["items"][0]["badCaseAgent"]["agentId"] is None
    assert main_discovery.json()["items"][0]["anchor"] == {
        "agentId": SESSION_4,
        "eventIndex": -1,
    }


async def test_all_five_display_states_are_reachable(problem_api: Any) -> None:
    """Session routes expose prompt/model/error/nonissue/unanalyzed states."""
    states: list[str] = []
    for session_id in (SESSION_1, SESSION_2, SESSION_3, SESSION_4):
        response = await problem_api.client.get(
            f"/api/sessions/{session_id}/bad-cases",
            headers=problem_api.authorization,
        )
        assert response.status_code == 200
        states.extend(item["analysis"]["displayState"] for item in response.json()["items"])
    assert states == [
        "analyzed_issue_prompt",
        "analyzed_issue_model",
        "analyzed_nonissue",
        "analyzed_issue_error",
        "unanalyzed",
    ]


async def test_non_issue_analysis_uses_its_closed_result_shape(
    problem_api: Any,
) -> None:
    """The non-issue attribution variant exposes only its reason and reasoning."""
    response = await problem_api.client.get(
        f"/api/sessions/{SESSION_2}/bad-cases",
        headers=problem_api.authorization,
    )
    assert response.status_code == 200
    analysis = next(
        item["analysis"]
        for item in response.json()["items"]
        if item["analysis"]["status"] == "analyzed_nonissue"
    )

    assert analysis["displayState"] == "analyzed_nonissue"
    assert set(analysis["result"]) == {"reason", "reasoning"}
    assert analysis["result"]["reason"]
    assert isinstance(analysis["result"]["reasoning"], list)
    assert all(isinstance(item, str) for item in analysis["result"]["reasoning"])


async def test_probe_detail_and_session_probe_list(problem_api: Any) -> None:
    """Probe reads include validated reverse links and stable not-found codes."""
    detail = await problem_api.client.get(
        f"/api/probes/{PROBE_1}",
        headers=problem_api.authorization,
    )
    missing = await problem_api.client.get(
        "/api/probes/missing",
        headers=problem_api.authorization,
    )
    listed = await problem_api.client.get(
        f"/api/sessions/{SESSION_1}/probes",
        headers=problem_api.authorization,
    )
    missing_session = await problem_api.client.get(
        "/api/sessions/missing/probes",
        headers=problem_api.authorization,
    )

    assert detail.status_code == 200
    assert detail.json()["probeId"] == PROBE_1
    assert detail.json()["fromBadCases"] == [CASE_1]
    assert detail.json()["fromBadCasesCount"] == 1
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROBE_NOT_FOUND"
    assert listed.status_code == 200
    assert [item["probeId"] for item in listed.json()["items"]] == [PROBE_1, PROBE_3]
    assert missing_session.status_code == 404
    assert missing_session.json()["error"]["code"] == "SESSION_NOT_FOUND"


async def test_problem_snapshot_is_requested_once_per_session_list(
    problem_api: Any,
) -> None:
    """The HTTP list delegates to one snapshot read instead of per-row queries."""
    service = problem_api.app.state.problems
    calls = 0
    original = service._repository.session_snapshot

    async def observed(session_id: str) -> object:
        nonlocal calls
        calls += 1
        return await original(session_id)

    service._repository.session_snapshot = observed
    response = await problem_api.client.get(
        f"/api/sessions/{SESSION_1}/bad-cases",
        headers=problem_api.authorization,
    )

    assert response.status_code == 200
    assert calls == 1


async def test_analysis_result_drift_degrades_to_unanalyzed(
    problem_api: Any,
) -> None:
    """Malformed external result shapes remain renderable as unanalyzed."""
    async with problem_api.database.transaction() as session:
        await session.execute(
            update(bad_case_analysis)
            .where(bad_case_analysis.c.bad_case_id == CASE_1)
            .values(analysis_result={"not_summary": "drifted"}),
        )

    listed = await problem_api.client.get(
        f"/api/sessions/{SESSION_1}/bad-cases",
        headers=problem_api.authorization,
    )
    detail = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}",
        headers=problem_api.authorization,
    )
    analysis = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}/analysis",
        headers=problem_api.authorization,
    )

    assert listed.status_code == 200
    listed_case = next(item for item in listed.json()["items"] if item["badCaseId"] == CASE_1)
    assert listed_case["analysis"] == {
        "status": "unanalyzed",
        "probeId": None,
        "attributeType": None,
        "displayState": "unanalyzed",
        "result": None,
    }
    assert detail.status_code == 200
    assert detail.json()["analysis"] == listed_case["analysis"]
    assert analysis.status_code == 200
    assert analysis.json() == listed_case["analysis"]


async def test_invalid_problem_presentation_returns_degraded_placeholder(
    problem_api: Any,
) -> None:
    """Presentation enum drift stays visible and never turns detail into 500."""
    async with problem_api.database.transaction() as session:
        await session.execute(
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == CASE_1)
            .values(bad_case_type="unknown", object_type="unknown"),
        )

    listed = await problem_api.client.get(
        f"/api/sessions/{SESSION_1}/bad-cases",
        headers=problem_api.authorization,
    )
    detail = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}",
        headers=problem_api.authorization,
    )

    assert listed.status_code == 200
    listed_case = next(item for item in listed.json()["items"] if item["badCaseId"] == CASE_1)
    assert listed_case["degraded"] is True
    assert listed_case["diagnosticCode"] == "EXTERNAL_FIELD_INVALID"
    assert listed_case["anchor"] == {"agentId": SESSION_1, "eventIndex": -1}
    assert detail.status_code == 200
    assert detail.json() == listed_case


async def test_blank_title_is_derived_and_reported_as_degraded(
    problem_api: Any,
) -> None:
    """A blank external title derives from the body and stays diagnosable."""
    async with problem_api.database.transaction() as session:
        await session.execute(
            update(bad_cases).where(bad_cases.c.bad_case_id == CASE_1).values(title="   "),
        )

    listed = await problem_api.client.get(
        f"/api/sessions/{SESSION_1}/bad-cases",
        headers=problem_api.authorization,
    )
    detail = await problem_api.client.get(
        f"/api/bad-cases/{CASE_1}",
        headers=problem_api.authorization,
    )

    assert listed.status_code == 200
    listed_case = next(item for item in listed.json()["items"] if item["badCaseId"] == CASE_1)
    assert listed_case["title"] == "合成示例：检查结论缺少目标文件。"  # noqa: RUF001
    assert listed_case["degraded"] is True
    assert listed_case["diagnosticCode"] == "EXTERNAL_FIELD_MISSING"
    # A derived title must not fall back to the main-node placeholder anchor:
    # the reporter anchor stays identical to the tree read model.
    assert listed_case["anchor"] == {"agentId": "agent-s1-review-0001", "eventIndex": -1}
    assert detail.status_code == 200
    assert detail.json() == listed_case
