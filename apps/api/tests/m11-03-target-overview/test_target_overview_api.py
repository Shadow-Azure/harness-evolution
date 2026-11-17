"""HTTP contracts for the evolution-target overview aggregation API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import pytest_asyncio
from sqlalchemy import insert

from app.db.base import Database
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.domain import bad_case_analysis, probe_reports
from app.main import create_app
from app.utils.time import SHANGHAI
from tests.identity.helpers import identity_settings
from tests.m10_02_potential_support import (
    FakeGitRemote,
    seed_case,
    seed_event,
    seed_session,
    seed_target,
    seed_workspace,
)
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
)

WORKSPACE_A = "ws-m11-03-a"
WORKSPACE_B = "ws-m11-03-b"
WORKSPACE_C = "ws-m11-03-c"
TARGET_SKILL = "target-m11-03-skill"
TARGET_AGENT = "target-m11-03-agent"
TARGET_KNOWLEDGE = "target-m11-03-knowledge"
TARGET_DISABLED = "target-m11-03-disabled"
TARGET_B = "target-m11-03-b"
SESSION_A = "m11-03-session-a"
SESSION_B = "m11-03-session-b"
SESSION_C = "m11-03-session-c"
SESSION_D = "m11-03-session-d"
SESSION_E = "m11-03-session-e"
SESSION_F = "m11-03-session-f"
SESSION_B_WS = "m11-03-session-b-ws"
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
OBJECT_ENTRY = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)
OLD_ENTRY = datetime(2026, 11, 17, 8, 30, tzinfo=SHANGHAI)
WINDOW = {"from": "2026-11-01", "to": "2026-11-30"}


@dataclass(frozen=True, slots=True)
class TargetOverviewApi:
    """Authenticated clients for three spaces and one seeded database."""

    client: httpx.AsyncClient
    database: Database
    workspace_a: str
    workspace_b: str
    workspace_c: str
    reader_a: dict[str, str]
    reader_b: dict[str, str]
    reader_c: dict[str, str]


def _at(hour: int, minute: int) -> datetime:
    """Return one deterministic Asia/Shanghai instant on 2026-11-17."""
    return datetime(2026, 11, 17, hour, minute, tzinfo=SHANGHAI)


async def seed_attribution(
    database: Database,
    *,
    probe_id: str,
    case_id: str,
    session_id: str,
    workspace_id: str = WORKSPACE_A,
    probe_type: str = "skill",
    probe_object: str = "deep-research",
    object_version: str,
    conclusion: str,
    category: str | None,
    updated_at: datetime,
) -> None:
    """Insert one probe link with explicit identity and attribution time."""
    async with database.transaction() as session:
        await session.execute(
            insert(probe_reports).values(
                probe_id=probe_id,
                workspace_id=workspace_id,
                session_id=session_id,
                probe_type=probe_type,
                probe_object=probe_object,
                object_version=object_version,
                attribute_type=category,
                conclusion=conclusion,
                confidence=0.8,
                probe_description=f"description {probe_id}",
                probe_analysis=f"analysis {probe_id}",
                policy_version="v1",
                attribution_engine="rule-v1",
                cache_key=f"{probe_id}-cache".ljust(64, "0")[:64],
                created_at=updated_at,
                updated_at=updated_at,
            ),
        )
        await session.execute(
            insert(bad_case_analysis).values(
                bad_case_id=case_id,
                probe_id=probe_id,
                analysis_status=None,
                analysis_result=None,
                updated_at=updated_at,
            ),
        )


async def seed_skill_sessions(database: Database) -> None:
    """Seed two skill versions plus the cross-space neighbor."""
    main_a = await seed_session(database, session_id=SESSION_A, started_at=NOW, title="A")
    await seed_event(
        database,
        agent_id=main_a,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_version="v2.0.0",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_event(
        database,
        agent_id=main_a,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(10, 30),
    )
    await seed_event(
        database,
        agent_id=main_a,
        event_index=2,
        kind="skill",
        name="deep-research",
        object_version="v2.0.0",
        triggered_at=_at(10, 40),
    )
    await seed_event(
        database,
        agent_id=main_a,
        event_index=3,
        kind="skill",
        name="early-skill",
        triggered_at=_at(9, 50),
    )
    await seed_case(
        database,
        case_id="m11-03-case-attributed",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_A,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(10, 35),
    )
    await seed_case(
        database,
        case_id="m11-03-case-self",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_A,
        case_type="self",
        object_name="deep-research",
        object_type="agent",
        created_at=_at(9, 30),
    )
    await seed_case(
        database,
        case_id="m11-03-case-nontarget",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_A,
        case_type="discovery",
        object_name="deep-research",
        object_type="skill",
        created_at=_at(10, 45),
    )
    await seed_case(
        database,
        case_id="m11-03-case-before",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_A,
        case_type="discovery",
        object_name="early-skill",
        object_type="skill",
        created_at=_at(9, 55),
    )

    main_b = await seed_session(database, session_id=SESSION_B, started_at=_at(8, 30), title="B")
    await seed_event(
        database,
        agent_id=main_b,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_version="v1.9.0",
        triggered_at=_at(9, 0),
    )
    await seed_event(
        database,
        agent_id=main_b,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(9, 30),
    )
    await seed_case(
        database,
        case_id="m11-03-case-old",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_B,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(9, 35),
    )

    main_e = await seed_session(database, session_id=SESSION_E, started_at=_at(8, 0), title="E")
    await seed_event(
        database,
        agent_id=main_e,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_revision="tag:v1.8.0",
        triggered_at=OLD_ENTRY,
    )
    await seed_event(
        database,
        agent_id=main_e,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(8, 45),
    )
    await seed_case(
        database,
        case_id="m11-03-case-revision",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_E,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(8, 50),
    )

    main_f = await seed_session(database, session_id=SESSION_F, started_at=_at(8, 30), title="F")
    await seed_event(
        database,
        agent_id=main_f,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_version="v2.0.0",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_event(
        database,
        agent_id=main_f,
        event_index=1,
        kind="skill",
        name="early-skill",
        triggered_at=_at(9, 50),
    )
    await seed_case(
        database,
        case_id="m11-03-case-only-associated",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_F,
        case_type="discovery",
        object_name="early-skill",
        object_type="skill",
        created_at=_at(9, 55),
    )

    main_ws = await seed_session(
        database,
        session_id=SESSION_B_WS,
        started_at=NOW,
        title="B neighbor",
    )
    await seed_event(
        database,
        agent_id=main_ws,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_version="v2.0.0",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_event(
        database,
        agent_id=main_ws,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(10, 30),
    )
    await seed_case(
        database,
        case_id="m11-03-case-neighbor",
        session_id=SESSION_B_WS,
        workspace_id=WORKSPACE_B,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(10, 35),
    )


async def seed_other_objects(database: Database) -> None:
    """Seed one agent target session and one knowledge revision session."""
    main_c = await seed_session(database, session_id=SESSION_C, started_at=NOW, title="C")
    await seed_event(
        database,
        agent_id=main_c,
        event_index=0,
        kind="agent",
        name="Explore",
        object_version="v1.0.0",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_event(
        database,
        agent_id=main_c,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(10, 30),
    )
    await seed_case(
        database,
        case_id="m11-03-case-agent",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_C,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(10, 35),
    )

    main_d = await seed_session(database, session_id=SESSION_D, started_at=NOW, title="D")
    await seed_event(
        database,
        agent_id=main_d,
        event_index=0,
        kind="knowledge",
        name="kb-doc",
        object_revision="digest:aaa",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_event(
        database,
        agent_id=main_d,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(10, 30),
    )
    await seed_case(
        database,
        case_id="m11-03-case-knowledge",
        workspace_id=WORKSPACE_A,
        session_id=SESSION_D,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(10, 35),
    )


async def seed_attributions(database: Database) -> None:
    """Seed attributed/non-target links plus one older duplicate link."""
    await seed_attribution(
        database,
        probe_id="probe-old-non-target",
        case_id="m11-03-case-attributed",
        session_id=SESSION_A,
        object_version="v2.0.0",
        conclusion="non_target",
        category=None,
        updated_at=_at(10, 50),
    )
    await seed_attribution(
        database,
        probe_id="probe-attributed",
        case_id="m11-03-case-attributed",
        session_id=SESSION_A,
        object_version="tag:v2.0.0",
        conclusion="attributed",
        category="error",
        updated_at=_at(11, 0),
    )
    await seed_attribution(
        database,
        probe_id="probe-non-target",
        case_id="m11-03-case-nontarget",
        session_id=SESSION_A,
        object_version="tag:v2.0.0",
        conclusion="non_target",
        category=None,
        updated_at=_at(11, 30),
    )
    await seed_attribution(
        database,
        probe_id="probe-knowledge",
        case_id="m11-03-case-knowledge",
        session_id=SESSION_D,
        probe_type="knowledge",
        probe_object="kb-doc",
        object_version="digest:aaa",
        conclusion="attributed",
        category="prompt",
        updated_at=_at(12, 0),
    )
    await seed_attribution(
        database,
        probe_id="probe-neighbor",
        case_id="m11-03-case-neighbor",
        session_id=SESSION_B_WS,
        workspace_id=WORKSPACE_B,
        object_version="tag:v2.0.0",
        conclusion="attributed",
        category="error",
        updated_at=_at(11, 0),
    )


@pytest_asyncio.fixture
async def target_overview_api(tmp_path: Path) -> AsyncIterator[TargetOverviewApi]:
    """Seed three spaces with targets, versions, cases, and attributions."""
    settings = identity_settings(tmp_path)
    app = create_app(settings, git_remote=FakeGitRemote())
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        database = app.state.database
        await ensure_fixture_external_tables(database)
        for workspace_id in (WORKSPACE_A, WORKSPACE_B, WORKSPACE_C):
            await seed_workspace(database, workspace_id)
        await seed_target(
            database,
            workspace_id=WORKSPACE_A,
            target_id=TARGET_SKILL,
            object_type="skill",
            object_name="deep-research",
            default_ref="v2.0.0",
        )
        await seed_target(
            database,
            workspace_id=WORKSPACE_A,
            target_id=TARGET_AGENT,
            object_type="agent",
            object_name="Explore",
            default_ref="v1.0.0",
        )
        await seed_target(
            database,
            workspace_id=WORKSPACE_A,
            target_id=TARGET_KNOWLEDGE,
            object_type="knowledge",
            object_name="kb-doc",
            default_ref="digest:aaa",
        )
        await seed_target(
            database,
            workspace_id=WORKSPACE_A,
            target_id=TARGET_DISABLED,
            object_type="skill",
            object_name="disabled-skill",
            default_ref="v1.0.0",
            enabled=False,
        )
        await seed_target(
            database,
            workspace_id=WORKSPACE_B,
            target_id=TARGET_B,
            object_type="skill",
            object_name="deep-research",
            default_ref="v2.0.0",
        )
        await seed_skill_sessions(database)
        await seed_other_objects(database)
        await seed_attributions(database)

        users: dict[str, str] = {}
        for key, workspace_id in (
            ("a", WORKSPACE_A),
            ("b", WORKSPACE_B),
            ("c", WORKSPACE_C),
        ):
            user_id = await create_user(database, username=f"m11-03-reader-{key}")
            await insert_member(
                database,
                workspace_id=workspace_id,
                user_id=user_id,
                role="viewer",
            )
            users[key] = user_id
        headers = {
            key: bearer(access_token(app, user_id=user_id)) for key, user_id in users.items()
        }
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield TargetOverviewApi(
                client=client,
                database=database,
                workspace_a=WORKSPACE_A,
                workspace_b=WORKSPACE_B,
                workspace_c=WORKSPACE_C,
                reader_a=headers["a"],
                reader_b=headers["b"],
                reader_c=headers["c"],
            )


async def test_target_list_summary_states_and_versions(
    target_overview_api: TargetOverviewApi,
) -> None:
    """The list summary totals equal the item rows and hide disabled/foreign targets."""
    response = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets",
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "targets": 3,
        "sessions": 6,
        "potential": 7,
        "attributed": 2,
        "nonTarget": 1,
        "unanalyzed": 4,
    }
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["pageSize"] == 5
    assert [item["objectName"] for item in body["items"]] == [
        "deep-research",
        "Explore",
        "kb-doc",
    ]
    skill, agent, knowledge = body["items"]
    assert skill["targetId"] == TARGET_SKILL
    assert skill["objectType"] == "skill"
    assert skill["versions"] == ["v2.0.0", "v1.9.0", "v1.8.0"]
    assert skill["sessions"] == 4
    assert skill["potential"] == 5
    assert skill["attributed"] == 1
    assert skill["nonTarget"] == 1
    assert skill["unanalyzed"] == 3
    assert skill["evolvable"] == 4
    assert skill["attributed"] + skill["nonTarget"] + skill["unanalyzed"] == skill["potential"]
    assert agent["objectType"] == "agent"
    assert agent["versions"] == ["v1.0.0"]
    assert agent["potential"] == 1
    assert agent["unanalyzed"] == 1
    assert knowledge["objectType"] == "knowledge"
    assert knowledge["versions"] == ["digest:aaa"]
    assert knowledge["attributed"] == 1
    assert TARGET_DISABLED not in {item["targetId"] for item in body["items"]}
    assert TARGET_B not in {item["targetId"] for item in body["items"]}


async def test_target_list_pages_and_empty_workspace(
    target_overview_api: TargetOverviewApi,
) -> None:
    """Paging only affects items, and a space without targets answers zeroes."""
    response = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets",
        headers=target_overview_api.reader_a,
        params={**WINDOW, "pageSize": 2, "page": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["items"][0]["objectName"] == "kb-doc"

    empty = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_c}/overview/targets",
        headers=target_overview_api.reader_c,
        params=WINDOW,
    )
    assert empty.status_code == 200
    empty_body = empty.json()
    assert empty_body["summary"] == {
        "targets": 0,
        "sessions": 0,
        "potential": 0,
        "attributed": 0,
        "nonTarget": 0,
        "unanalyzed": 0,
    }
    assert empty_body["items"] == []
    assert empty_body["total"] == 0


async def test_newest_attribution_wins_and_versions_do_not_double_count(
    target_overview_api: TargetOverviewApi,
) -> None:
    """A newer attributed link overwrites an older non-target link for one version."""
    response = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/cases",
        headers=target_overview_api.reader_a,
        params={
            **WINDOW,
            "targets": TARGET_SKILL,
            "states": "attributed",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["badCaseId"] == "m11-03-case-attributed"
    assert item["objectVersion"] == "v2.0.0"
    assert item["state"] == "attributed"
    assert item["attributionId"] == "probe-attributed"
    assert item["category"] == "error"


async def test_cases_filters_sorting_and_pagination(
    target_overview_api: TargetOverviewApi,
) -> None:
    """Every case filter narrows the same projection and keeps a stable page total."""
    url = f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/cases"
    all_rows = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert all_rows.status_code == 200
    body = all_rows.json()
    assert body["total"] == 7
    assert body["pageSize"] == 8
    assert len(body["items"]) == 7
    created = [item["createdAt"] for item in body["items"]]
    assert created == sorted(created, reverse=True)
    assert {item["state"] for item in body["items"]} == {
        "attributed",
        "nonTarget",
        "unanalyzed",
    }

    unanalyzed = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "states": "unanalyzed"},
    )
    assert unanalyzed.json()["total"] == 4

    skill = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": TARGET_SKILL},
    )
    assert skill.json()["total"] == 5

    sources = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "objects": "deep-research"},
    )
    assert sources.json()["total"] == 2
    assert {item["source"] for item in sources.json()["items"]} == {"deep-research"}

    agent = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": TARGET_AGENT},
    )
    agent_body = agent.json()
    assert agent_body["total"] == 1
    assert agent_body["items"][0]["objectName"] == "Explore"
    assert agent_body["items"][0]["objectVersion"] == "v1.0.0"
    assert agent_body["items"][0]["sessionId"] == SESSION_C

    page = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "pageSize": 2, "page": 2},
    )
    assert page.json()["total"] == 7
    assert len(page.json()["items"]) == 2

    missing = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": "missing-target"},
    )
    assert missing.json()["total"] == 0
    assert missing.json()["items"] == []


async def test_trend_bucket_policy_states_and_grain(
    target_overview_api: TargetOverviewApi,
) -> None:
    """Attributed rows bucket by attribution time and unanalyzed rows by report time."""
    url = f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/trend"
    response = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": TARGET_SKILL, "states": "attributed,unanalyzed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grain"] == "day"
    assert len(body["buckets"]) == 30
    assert body["meta"]["bucketPolicy"] == (
        "attributed and nonTarget rows bucket by attribution createdAt; "
        "unanalyzed rows bucket by badCase createdAt"
    )
    assert len(body["buckets"][0]["byTarget"]) == 1
    assert body["buckets"][0]["byTarget"][0]["targetId"] == TARGET_SKILL
    day = next(bucket for bucket in body["buckets"] if bucket["bucket"] == "2026-11-17")
    assert day["attributed"] == 1
    assert day["nonTarget"] == 0
    assert day["unanalyzed"] == 3
    assert sum(bucket["attributed"] for bucket in body["buckets"]) == 1
    assert sum(bucket["unanalyzed"] for bucket in body["buckets"]) == 3

    unfiltered = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    unfiltered_day = next(
        bucket for bucket in unfiltered.json()["buckets"] if bucket["bucket"] == "2026-11-17"
    )
    assert unfiltered_day["attributed"] == 2
    assert unfiltered_day["nonTarget"] == 1
    assert unfiltered_day["unanalyzed"] == 4
    assert len(unfiltered_day["byTarget"]) == 3

    weekly = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={"from": "2026-01-01", "to": "2026-06-30"},
    )
    assert weekly.status_code == 200
    assert weekly.json()["grain"] == "week"
    assert weekly.json()["buckets"]
    assert sum(bucket["attributed"] for bucket in weekly.json()["buckets"]) == 0

    invalid = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "states": "bogus"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_INVALID"


async def test_detail_versions_stats_and_sources(
    target_overview_api: TargetOverviewApi,
) -> None:
    """The detail card scopes versions independently and dedupes case totals."""
    url = (
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/{TARGET_SKILL}/detail"
    )
    response = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target"]["targetId"] == TARGET_SKILL
    assert body["target"]["defaultRef"] == "v2.0.0"
    assert body["target"]["versions"] == ["v2.0.0", "v1.9.0", "v1.8.0"]
    assert body["stats"] == {
        "sessions": 4,
        "potential": 5,
        "distinctCases": 5,
        "versions": 3,
    }
    assert [row["version"] for row in body["byVersion"]] == [
        "v2.0.0",
        "v1.9.0",
        "v1.8.0",
    ]
    assert body["byVersion"][0] == {
        "version": "v2.0.0",
        "potential": 3,
        "attributed": 1,
        "nonTarget": 1,
        "unanalyzed": 1,
    }
    assert body["byVersion"][1]["unanalyzed"] == 1
    assert [row["source"] for row in body["bySource"]] == ["workflow", "deep-research"]
    assert body["bySource"][0] == {
        "source": "workflow",
        "total": 3,
        "distinctCases": 3,
    }
    assert body["bySource"][1] == {
        "source": "deep-research",
        "total": 2,
        "distinctCases": 2,
    }

    default_limit = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "versionLimit": 5},
    )
    default_limit_body = default_limit.json()
    assert default_limit_body["stats"]["versions"] == 3

    everything = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "versionLimit": 0},
    )
    assert everything.json()["stats"]["versions"] == 3

    selected = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "versions": "v1.9.0,v1.8.0"},
    )
    selected_body = selected.json()
    assert selected_body["stats"]["versions"] == 2
    assert selected_body["stats"]["potential"] == 2
    assert [row["version"] for row in selected_body["byVersion"]] == ["v1.9.0", "v1.8.0"]

    unknown = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "versions": "v9.9.9"},
    )
    unknown_body = unknown.json()
    assert unknown_body["stats"]["versions"] == 0
    assert unknown_body["stats"]["potential"] == 0
    assert unknown_body["byVersion"] == []
    assert unknown_body["bySource"] == []

    invalid_limit = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "versionLimit": 7},
    )
    assert invalid_limit.status_code == 422


async def test_knowledge_target_uses_revision_coordinates(
    target_overview_api: TargetOverviewApi,
) -> None:
    """A knowledge target is discovered by digest revision and shares the state math."""
    url = (
        f"/api/workspaces/{target_overview_api.workspace_a}"
        f"/overview/targets/{TARGET_KNOWLEDGE}/detail"
    )
    response = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target"]["objectType"] == "knowledge"
    assert body["target"]["versions"] == ["digest:aaa"]
    assert body["stats"] == {
        "sessions": 1,
        "potential": 1,
        "distinctCases": 1,
        "versions": 1,
    }
    assert body["byVersion"] == [
        {
            "version": "digest:aaa",
            "potential": 1,
            "attributed": 1,
            "nonTarget": 0,
            "unanalyzed": 0,
        },
    ]

    cases = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/cases",
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": TARGET_KNOWLEDGE},
    )
    item = cases.json()["items"][0]
    assert item["objectType"] == "knowledge"
    assert item["objectVersion"] == "digest:aaa"
    assert item["attributionId"] == "probe-knowledge"
    assert item["category"] == "prompt"


async def test_workspace_isolation_and_cross_space_404(
    target_overview_api: TargetOverviewApi,
) -> None:
    """Foreign cases never enter a space aggregate and foreign targets answer 404."""
    list_a = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets",
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert list_a.json()["summary"]["potential"] == 7

    list_b = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_b}/overview/targets",
        headers=target_overview_api.reader_b,
        params=WINDOW,
    )
    assert list_b.status_code == 200
    assert list_b.json()["summary"] == {
        "targets": 1,
        "sessions": 1,
        "potential": 1,
        "attributed": 1,
        "nonTarget": 0,
        "unanalyzed": 0,
    }
    assert list_b.json()["items"][0]["targetId"] == TARGET_B

    cases_a = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/cases",
        headers=target_overview_api.reader_a,
        params={**WINDOW, "objects": "workflow"},
    )
    assert cases_a.json()["total"] == 5

    cross_target = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/{TARGET_B}/detail",
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert cross_target.status_code == 404
    assert cross_target.json()["error"]["code"] == "TARGET_NOT_FOUND"

    disabled = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}"
        f"/overview/targets/{TARGET_DISABLED}/detail",
        headers=target_overview_api.reader_a,
        params=WINDOW,
    )
    assert disabled.status_code == 404

    foreign_space = await target_overview_api.client.get(
        f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets",
        headers=target_overview_api.reader_b,
        params=WINDOW,
    )
    assert foreign_space.status_code == 404
    assert foreign_space.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_target_overview_requires_auth_and_validates_parameters(
    target_overview_api: TargetOverviewApi,
) -> None:
    """The routes share bearer auth and reject impossible paging/filter inputs."""
    base = f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets"
    unauthenticated = await target_overview_api.client.get(base, params=WINDOW)
    assert unauthenticated.status_code == 401

    bad_page = await target_overview_api.client.get(
        base,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "page": 0},
    )
    assert bad_page.status_code == 422

    bad_size = await target_overview_api.client.get(
        base,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "pageSize": 51},
    )
    assert bad_size.status_code == 422

    repeated = await target_overview_api.client.get(
        f"{base}/cases",
        headers=target_overview_api.reader_a,
        params=[
            ("from", WINDOW["from"]),
            ("to", WINDOW["to"]),
            ("targets", TARGET_SKILL),
            ("targets", TARGET_AGENT),
        ],
    )
    assert repeated.status_code == 200
    assert repeated.json()["total"] == 6

    empty_states = await target_overview_api.client.get(
        f"{base}/cases",
        headers=target_overview_api.reader_a,
        params={**WINDOW, "states": ""},
    )
    assert empty_states.status_code == 200
    assert empty_states.json()["total"] == 7

    too_many = await target_overview_api.client.get(
        f"{base}/trend",
        headers=target_overview_api.reader_a,
        params={
            **WINDOW,
            "targets": ",".join(f"target-{index}" for index in range(51)),
        },
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "VALIDATION_INVALID"


def test_selected_versions_applies_limit_and_explicit_scope() -> None:
    """The detail version scope is the newest N versions or the explicit filter."""
    from app.db.crud.evolution_targets import EvolutionTargetRecord
    from app.service.overview.targets import TargetAnalysis, _selected_versions

    target = EvolutionTargetRecord(
        id="target-unit",
        object_type="skill",
        object_name="deep-research",
        repo_url="https://example.invalid/deep-research.git",
        sub_dir="skills/deep-research",
        default_ref="v6.0.0",
        validation_project_id="validation",
        test_project_id="test",
        enabled=True,
        workspace_id=WORKSPACE_A,
    )
    analysis = TargetAnalysis(
        target=target,
        versions=("v6.0.0", "v5.0.0", "v4.0.0", "v3.0.0", "v2.0.0", "v1.0.0"),
        session_ids=frozenset(),
        entries=(),
    )
    assert _selected_versions(analysis, (), 0) == analysis.versions
    assert _selected_versions(analysis, (), 5) == (
        "v6.0.0",
        "v5.0.0",
        "v4.0.0",
        "v3.0.0",
        "v2.0.0",
    )
    assert _selected_versions(analysis, ("v3.0.0", "missing", "v5.0.0"), 5) == (
        "v3.0.0",
        "v5.0.0",
    )


async def test_foreign_workspace_attribution_is_ignored(
    target_overview_api: TargetOverviewApi,
) -> None:
    """A newer probe from another space cannot change this space's three states."""
    await seed_attribution(
        target_overview_api.database,
        probe_id="probe-cross-workspace",
        case_id="m11-03-case-nontarget",
        session_id=SESSION_A,
        workspace_id=WORKSPACE_B,
        object_version="tag:v2.0.0",
        conclusion="attributed",
        category="error",
        updated_at=_at(13, 0),
    )
    url = f"/api/workspaces/{target_overview_api.workspace_a}/overview/targets/cases"
    attributed = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": TARGET_SKILL, "states": "attributed"},
    )
    assert attributed.status_code == 200
    assert {item["badCaseId"] for item in attributed.json()["items"]} == {
        "m11-03-case-attributed",
    }
    non_target = await target_overview_api.client.get(
        url,
        headers=target_overview_api.reader_a,
        params={**WINDOW, "targets": TARGET_SKILL, "states": "nonTarget"},
    )
    assert non_target.status_code == 200
    assert {item["badCaseId"] for item in non_target.json()["items"]} == {
        "m11-03-case-nontarget",
    }
