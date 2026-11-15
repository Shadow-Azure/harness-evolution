"""Workspace overview API: pinned aggregation, buckets, filters, and validation.

The fixture is hand-counted: workspace A holds six in-window cases across three
objects, two types, and three days, plus one out-of-window case that only moves
``used``. A pending root (a reported root with no normalized trace) is one of the
three distinct roots, so ``sessions`` counts it while the workspace Session list
never would.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import insert, text

from app.db.base import Database
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.main import create_app
from app.utils.time import SHANGHAI, now_shanghai
from tests.identity.helpers import identity_settings
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)

SESSION_1 = "20000000-0000-4000-8000-000000000001"
SESSION_2 = "20000000-0000-4000-8000-000000000002"
SESSION_3 = "20000000-0000-4000-8000-000000000003"
PENDING_ROOT = "20000000-0000-4000-8000-000000000099"
REMOTE_SESSION_1 = "50000000-0000-4000-8000-000000000001"
REMOTE_SESSION_2 = "50000000-0000-4000-8000-000000000002"

SELF_LABEL = "自身存在问题"
DISCOVERY_LABEL = "发现前置步骤问题"


@dataclass(frozen=True, slots=True)
class OverviewEnvironment:
    """Four seeded workspaces plus authenticated readers of different scopes."""

    client: httpx.AsyncClient
    database: Database
    admin: dict[str, str]
    alice: dict[str, str]
    bob: dict[str, str]
    carol: dict[str, str]
    dave: dict[str, str]
    workspace_a: str
    workspace_b: str
    workspace_c: str
    workspace_g: str
    today: date
    day0: date
    day1: date
    day2: date


def _at(day: date, hour: int, minute: int) -> datetime:
    """Return one Asia/Shanghai timestamp on the supplied local day."""
    return datetime.combine(day, time(hour, minute), tzinfo=SHANGHAI)


def _case(
    *,
    case_id: str,
    workspace_id: str,
    session_id: str,
    bad_case_type: str,
    object_name: str,
    created_at: datetime,
    object_version: str | None = "v1",
) -> dict[str, Any]:
    """Build one externally reported bad case with a deterministic timestamp."""
    return {
        "bad_case_id": case_id,
        "workspace_id": workspace_id,
        "bad_case_session_id": session_id,
        "bad_case_type": bad_case_type,
        "object_name": object_name,
        "object_type": "skill",
        "object_version": object_version,
        "bad_case_agent_id": None,
        "title": f"Case {case_id}",
        "bad_case_description": "Hand-counted workspace overview fixture.",
        "meta_data": None,
        "source": "tests",
        "created_at": created_at,
        "updated_at": created_at,
    }


def _probe(*, probe_id: str, object_version: str | None, created_at: datetime) -> dict[str, Any]:
    """Build one attribution probe report for the attribution-count tests."""
    return {
        "probe_id": probe_id,
        "session_id": SESSION_1,
        "probe_type": "skill",
        "probe_object": "deep-research",
        "object_version": object_version,
        "attribute_type": "model",
        "probe_description": "Probe description.",
        "probe_analysis": "Probe analysis.",
        "created_at": created_at,
        "updated_at": created_at,
    }


def _analysis(*, case_id: str, probe_id: str, updated_at: datetime) -> dict[str, Any]:
    """Build one case-to-probe attribution link."""
    return {
        "bad_case_id": case_id,
        "analysis_status": "analyzed_issue",
        "probe_id": probe_id,
        "analysis_result": None,
        "updated_at": updated_at,
    }


async def _seed_corpus(
    database: Database,
    *,
    workspace_a: str,
    workspace_b: str,
    workspace_g: str,
) -> None:
    """Insert the workspace cases with hand-countable dates and types."""
    today = now_shanghai().date()
    day0 = today
    day1 = today - timedelta(days=1)
    day2 = today - timedelta(days=2)
    outside = today - timedelta(days=90)
    rows = [
        _case(
            case_id="a-deep-self-1",
            workspace_id=workspace_a,
            session_id=SESSION_1,
            bad_case_type="self",
            object_name="deep-research",
            created_at=_at(day0, 15, 58),
        ),
        _case(
            case_id="a-deep-discovery-2",
            workspace_id=workspace_a,
            session_id=SESSION_2,
            bad_case_type="discovery",
            object_name="deep-research",
            created_at=_at(day0, 9, 15),
        ),
        # 00:30+08 must land on day1, never on the previous UTC day.
        _case(
            case_id="a-explore-self-3",
            workspace_id=workspace_a,
            session_id=SESSION_1,
            bad_case_type="self",
            object_name="Explore",
            created_at=_at(day1, 0, 30),
        ),
        _case(
            case_id="a-workflow-discovery-4",
            workspace_id=workspace_a,
            session_id=SESSION_2,
            bad_case_type="discovery",
            object_name="workflow",
            created_at=_at(day1, 23, 59),
        ),
        _case(
            case_id="a-deep-self-5",
            workspace_id=workspace_a,
            session_id=PENDING_ROOT,
            bad_case_type="self",
            object_name="deep-research",
            created_at=_at(day2, 12, 0),
        ),
        _case(
            case_id="a-explore-self-6",
            workspace_id=workspace_a,
            session_id=SESSION_1,
            bad_case_type="self",
            object_name="Explore",
            created_at=_at(day2, 8, 0),
        ),
        _case(
            case_id="a-deep-self-outside-7",
            workspace_id=workspace_a,
            session_id=SESSION_3,
            bad_case_type="self",
            object_name="deep-research",
            created_at=_at(outside, 12, 0),
        ),
        _case(
            case_id="b-deep-self-1",
            workspace_id=workspace_b,
            session_id=REMOTE_SESSION_1,
            bad_case_type="self",
            object_name="deep-research",
            created_at=_at(day0, 10, 0),
        ),
        _case(
            case_id="b-explore-discovery-2",
            workspace_id=workspace_b,
            session_id=REMOTE_SESSION_2,
            bad_case_type="discovery",
            object_name="Explore",
            created_at=_at(day1, 10, 0),
        ),
        # Fixed absolute dates so week, month, and downgrade buckets stay stable.
        _case(
            case_id="g-alpha-self-1",
            workspace_id=workspace_g,
            session_id="60000000-0000-4000-8000-000000000001",
            bad_case_type="self",
            object_name="alpha",
            created_at=_at(date(2025, 12, 30), 9, 0),
        ),
        _case(
            case_id="g-alpha-discovery-2",
            workspace_id=workspace_g,
            session_id="60000000-0000-4000-8000-000000000002",
            bad_case_type="discovery",
            object_name="alpha",
            created_at=_at(date(2026, 1, 5), 9, 0),
        ),
        _case(
            case_id="g-beta-self-3",
            workspace_id=workspace_g,
            session_id="60000000-0000-4000-8000-000000000003",
            bad_case_type="self",
            object_name="beta",
            created_at=_at(date(2026, 1, 18), 9, 0),
        ),
        _case(
            case_id="g-alpha-self-4",
            workspace_id=workspace_g,
            session_id="60000000-0000-4000-8000-000000000001",
            bad_case_type="self",
            object_name="alpha",
            created_at=_at(date(2026, 2, 2), 9, 0),
        ),
        _case(
            case_id="g-beta-discovery-5",
            workspace_id=workspace_g,
            session_id="60000000-0000-4000-8000-000000000003",
            bad_case_type="discovery",
            object_name="beta",
            created_at=_at(date(2026, 2, 28), 9, 0),
        ),
        _case(
            case_id="g-alpha-self-6",
            workspace_id=workspace_g,
            session_id="60000000-0000-4000-8000-000000000002",
            bad_case_type="self",
            object_name="alpha",
            created_at=_at(date(2026, 3, 31), 9, 0),
        ),
    ]
    async with database.transaction() as session:
        await session.execute(insert(bad_cases), rows)


@pytest_asyncio.fixture
async def overview(tmp_path: Path) -> AsyncIterator[OverviewEnvironment]:
    """Seed four workspaces with hand-countable cases and authenticated readers."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        database = app.state.database
        await ensure_fixture_external_tables(database)
        workspace_a = await insert_workspace(database, name="overview-a", quota=60)
        workspace_b = await insert_workspace(database, name="overview-b", quota=5)
        workspace_c = await insert_workspace(database, name="overview-c", quota=10)
        workspace_g = await insert_workspace(database, name="overview-g", quota=20)
        alice_id = await create_user(database, username="overview-alice")
        bob_id = await create_user(database, username="overview-bob")
        carol_id = await create_user(database, username="overview-carol")
        dave_id = await create_user(database, username="overview-dave")
        admin_id = await create_user(database, username="overview-admin", role="admin")
        for workspace_id in (workspace_a, workspace_g):
            await insert_member(
                database,
                workspace_id=workspace_id,
                user_id=alice_id,
                role="viewer",
            )
        await insert_member(
            database,
            workspace_id=workspace_b,
            user_id=bob_id,
            role="viewer",
        )
        await insert_member(
            database,
            workspace_id=workspace_c,
            user_id=carol_id,
            role="viewer",
        )
        await _seed_corpus(
            database,
            workspace_a=workspace_a,
            workspace_b=workspace_b,
            workspace_g=workspace_g,
        )
        today = now_shanghai().date()
        yield OverviewEnvironment(
            client=client,
            database=database,
            admin=bearer(access_token(app, user_id=admin_id, role="admin")),
            alice=bearer(access_token(app, user_id=alice_id)),
            bob=bearer(access_token(app, user_id=bob_id)),
            carol=bearer(access_token(app, user_id=carol_id)),
            dave=bearer(access_token(app, user_id=dave_id)),
            workspace_a=workspace_a,
            workspace_b=workspace_b,
            workspace_c=workspace_c,
            workspace_g=workspace_g,
            today=today,
            day0=today,
            day1=today - timedelta(days=1),
            day2=today - timedelta(days=2),
        )


def _params(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    range_days: int | None = None,
    objects: tuple[str, ...] = (),
    grain: str | None = None,
    bad_case_type: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[tuple[str, str]]:
    """Build repeated query parameters exactly as the browser would send them."""
    items: list[tuple[str, str]] = []
    if date_from is not None:
        items.append(("from", date_from.isoformat()))
    if date_to is not None:
        items.append(("to", date_to.isoformat()))
    if range_days is not None:
        items.append(("range", str(range_days)))
    for name in objects:
        items.append(("objects", name))
    if grain is not None:
        items.append(("grain", grain))
    if bad_case_type is not None:
        items.append(("badCaseType", bad_case_type))
    if page is not None:
        items.append(("page", str(page)))
    if page_size is not None:
        items.append(("pageSize", str(page_size)))
    return items


async def _get(
    environment: OverviewEnvironment,
    workspace: str,
    suffix: str,
    headers: dict[str, str],
    *,
    params: list[tuple[str, str]] | None = None,
) -> httpx.Response:
    """Call one overview route under the supplied workspace."""
    return await environment.client.get(
        f"/api/workspaces/{workspace}/{suffix}",
        headers=headers,
        params=cast(Any, params),
    )


def _in_window(environment: OverviewEnvironment) -> list[tuple[str, str]]:
    """Return the explicit three-day window the main corpus was counted over."""
    return _params(date_from=environment.day2, date_to=environment.day0)


def _error_code(response: httpx.Response) -> str:
    """Return the stable error code from the shared envelope."""
    payload = response.json()
    code: str = payload["error"]["code"]
    return code


async def test_summary_matches_hand_counted_aggregates(
    overview: OverviewEnvironment,
) -> None:
    """Summary totals, quota/used, and object options match the seeded corpus."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=_in_window(environment),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window"] == {
        "from": environment.day2.isoformat(),
        "to": environment.day0.isoformat(),
    }
    assert payload["totals"] == {
        "badCases": 6,
        "self": 4,
        "discovery": 2,
        "sessions": 3,
        "sources": 3,
        "quota": 60,
        "used": 7,
    }
    assert payload["objects"] == ["deep-research", "Explore", "workflow"]


async def test_summary_defaults_to_the_last_ninety_days(
    overview: OverviewEnvironment,
) -> None:
    """No window parameters resolve to today-89..today and still count day0 rows."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window"] == {
        "from": (environment.today - timedelta(days=89)).isoformat(),
        "to": environment.today.isoformat(),
    }
    assert payload["totals"]["badCases"] == 6
    assert payload["totals"]["used"] == 7


async def test_summary_used_ignores_the_window_and_quota_is_workspace_scoped(
    overview: OverviewEnvironment,
) -> None:
    """One out-of-window case moves only ``used``; another workspace stays separate."""
    environment = overview
    one_day = _params(date_from=environment.day0, date_to=environment.day0)

    narrow = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=one_day,
    )
    remote = await _get(
        environment,
        environment.workspace_b,
        "overview/summary",
        environment.bob,
        params=_in_window(environment),
    )

    assert narrow.json()["totals"] == {
        "badCases": 2,
        "self": 1,
        "discovery": 1,
        "sessions": 2,
        "sources": 1,
        "quota": 60,
        "used": 7,
    }
    assert remote.json()["totals"] == {
        "badCases": 2,
        "self": 1,
        "discovery": 1,
        "sessions": 2,
        "sources": 2,
        "quota": 5,
        "used": 2,
    }


async def test_summary_object_filter_and_object_options(
    overview: OverviewEnvironment,
) -> None:
    """Selected objects narrow the totals but the option list still shows every object."""
    environment = overview

    one = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=[*_in_window(environment), ("objects", "deep-research")],
    )
    union = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=[
            *_in_window(environment),
            ("objects", "deep-research"),
            ("objects", "workflow"),
        ],
    )
    blank = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=[*_in_window(environment), ("objects", "")],
    )

    assert one.json()["totals"]["badCases"] == 3
    assert one.json()["totals"]["sessions"] == 3
    assert one.json()["objects"] == ["deep-research", "Explore", "workflow"]
    assert union.json()["totals"]["badCases"] == 4
    assert union.json()["totals"]["sources"] == 2
    assert blank.json()["totals"]["badCases"] == 6


async def test_summary_supports_comma_separated_and_deduplicated_objects(
    overview: OverviewEnvironment,
) -> None:
    """Comma-separated values are split, and duplicates collapse before counting."""
    environment = overview

    comma = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=[*_in_window(environment), ("objects", "deep-research, Explore")],
    )
    duplicates = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=[
            *_in_window(environment),
            ("objects", "deep-research,deep-research"),
            ("objects", " deep-research "),
        ],
    )

    assert comma.json()["totals"]["badCases"] == 5
    assert comma.json()["totals"]["sources"] == 2
    assert duplicates.json()["totals"]["badCases"] == 3


async def test_trend_day_buckets_are_continuous_and_zero_filled(
    overview: OverviewEnvironment,
) -> None:
    """A five-day window returns five day buckets, including untouched days."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/trend",
        environment.alice,
        params=_params(
            date_from=environment.today - timedelta(days=4),
            date_to=environment.day0,
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grain"] == "day"
    assert payload["window"] == {
        "from": (environment.today - timedelta(days=4)).isoformat(),
        "to": environment.day0.isoformat(),
    }
    offsets = [(environment.today - timedelta(days=days_ago)) for days_ago in (4, 3, 2, 1, 0)]
    assert payload["buckets"] == [
        {
            "bucket": day.isoformat(),
            "label": f"{day.month:02d}-{day.day:02d}",
            "self": self_count,
            "discovery": discovery_count,
            "total": self_count + discovery_count,
        }
        for day, self_count, discovery_count in zip(
            offsets,
            (0, 0, 2, 1, 1),
            (0, 0, 0, 1, 1),
            strict=True,
        )
    ]


async def test_trend_buckets_a_shanghai_midnight_case_on_the_local_day(
    overview: OverviewEnvironment,
) -> None:
    """00:30+08 belongs to its local day rather than the previous UTC day."""
    environment = overview
    params = _params(
        date_from=environment.day1,
        date_to=environment.day1,
        objects=("Explore",),
    )

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/trend",
        environment.alice,
        params=params,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["buckets"] == [
        {
            "bucket": environment.day1.isoformat(),
            "label": f"{environment.day1.month:02d}-{environment.day1.day:02d}",
            "self": 1,
            "discovery": 0,
            "total": 1,
        },
    ]


async def test_trend_week_buckets_use_iso_monday_boundaries(
    overview: OverviewEnvironment,
) -> None:
    """Week buckets start Monday and aggregate both contained days."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_g,
        "overview/trend",
        environment.alice,
        params=_params(
            date_from=date(2026, 1, 5),
            date_to=date(2026, 1, 18),
            grain="week",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grain"] == "week"
    assert payload["buckets"] == [
        {"bucket": "2026-01-05", "label": "01-05", "self": 0, "discovery": 1, "total": 1},
        {"bucket": "2026-01-12", "label": "01-12", "self": 1, "discovery": 0, "total": 1},
    ]


async def test_trend_month_buckets_cover_every_touched_month(
    overview: OverviewEnvironment,
) -> None:
    """Month buckets start on the 1st, fill gaps, and label YYYY-MM."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_g,
        "overview/trend",
        environment.alice,
        params=_params(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 4, 30),
            grain="month",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grain"] == "month"
    assert payload["buckets"] == [
        {"bucket": "2026-01-01", "label": "2026-01", "self": 1, "discovery": 1, "total": 2},
        {"bucket": "2026-02-01", "label": "2026-02", "self": 1, "discovery": 1, "total": 2},
        {"bucket": "2026-03-01", "label": "2026-03", "self": 1, "discovery": 0, "total": 1},
        {"bucket": "2026-04-01", "label": "2026-04", "self": 0, "discovery": 0, "total": 0},
    ]


async def test_trend_day_grain_downgrades_to_week_over_ninety_two_days(
    overview: OverviewEnvironment,
) -> None:
    """A 121-day day request is served as week and says so in the response."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_g,
        "overview/trend",
        environment.alice,
        params=_params(
            date_from=date(2025, 12, 1),
            date_to=date(2026, 3, 31),
            grain="day",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grain"] == "week"
    assert len(payload["buckets"]) == 18
    assert payload["buckets"][0]["bucket"] == "2025-12-01"
    assert payload["buckets"][-1]["bucket"] == "2026-03-30"
    assert sum(bucket["total"] for bucket in payload["buckets"]) == 6
    for bucket in payload["buckets"]:
        assert date.fromisoformat(bucket["bucket"]).weekday() == 0


async def test_trend_exactly_ninety_two_days_keeps_day_grain(
    overview: OverviewEnvironment,
) -> None:
    """92 inclusive days stay at day grain; 93 would downgrade."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_g,
        "overview/trend",
        environment.alice,
        params=_params(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 4, 2),
            grain="day",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grain"] == "day"
    assert len(payload["buckets"]) == 92


async def test_sources_are_sorted_by_total_then_object(
    overview: OverviewEnvironment,
) -> None:
    """Per-object totals, type split, and distinct sessions match the corpus."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/sources",
        environment.alice,
        params=_in_window(environment),
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "object": "deep-research",
                "total": 3,
                "self": 2,
                "discovery": 1,
                "sessions": 3,
            },
            {"object": "Explore", "total": 2, "self": 2, "discovery": 0, "sessions": 1},
            {"object": "workflow", "total": 1, "self": 0, "discovery": 1, "sessions": 1},
        ],
    }


async def test_sources_respect_the_object_union_filter(
    overview: OverviewEnvironment,
) -> None:
    """A multi-object selection returns exactly those objects, in total order."""
    environment = overview
    params = [
        *_in_window(environment),
        ("objects", "workflow,Explore"),
    ]

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/sources",
        environment.alice,
        params=params,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["object"] for item in payload["items"]] == ["Explore", "workflow"]
    assert [item["total"] for item in payload["items"]] == [2, 1]


async def test_sources_break_total_ties_by_object_name(
    overview: OverviewEnvironment,
) -> None:
    """Equal totals keep a deterministic object order in both directions."""
    environment = overview
    # Both objects have exactly one case in January, so only the name breaks the tie.
    response = await _get(
        environment,
        environment.workspace_g,
        "overview/sources",
        environment.alice,
        params=_params(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
        ),
    )

    assert response.status_code == 200
    assert [item["object"] for item in response.json()["items"]] == ["alpha", "beta"]


async def test_list_returns_the_full_window_with_labels_and_triggers(
    overview: OverviewEnvironment,
) -> None:
    """Defaults return every in-window case with labels and createdAt-based triggerAt."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=_in_window(environment),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 6
    assert payload["page"] == 1
    assert payload["pageSize"] == 8
    assert [item["badCaseId"] for item in payload["items"]] == [
        "a-deep-self-1",
        "a-deep-discovery-2",
        "a-workflow-discovery-4",
        "a-explore-self-3",
        "a-deep-self-5",
        "a-explore-self-6",
    ]
    first = payload["items"][0]
    assert first["objectName"] == "deep-research"
    assert first["badCaseType"] == "self"
    assert first["badCaseTypeLabel"] == SELF_LABEL
    assert first["sessionId"] == SESSION_1
    assert first["title"] == "Case a-deep-self-1"
    assert first["attributionCount"] == 0
    assert first["createdAt"] == _at(environment.day0, 15, 58).isoformat()
    assert first["triggerAt"] == first["createdAt"]
    discovery = payload["items"][2]
    assert discovery["badCaseType"] == "discovery"
    assert discovery["badCaseTypeLabel"] == DISCOVERY_LABEL


async def test_list_default_page_size_is_eight_and_pages_do_not_overlap(
    overview: OverviewEnvironment,
) -> None:
    """Ten in-window cases split into 8 + 2 with an authoritative total."""
    environment = overview
    async with environment.database.transaction() as session:
        await session.execute(
            insert(bad_cases),
            [
                _case(
                    case_id=f"a-extra-{index}",
                    workspace_id=environment.workspace_a,
                    session_id=SESSION_1,
                    bad_case_type="self",
                    object_name="extra",
                    created_at=_at(environment.day0, 18, index),
                )
                for index in range(1, 5)
            ],
        )

    first = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=_in_window(environment),
    )
    second = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("page", "2")],
    )

    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["total"] == second_payload["total"] == 10
    assert len(first_payload["items"]) == 8
    assert len(second_payload["items"]) == 2
    first_ids = {item["badCaseId"] for item in first_payload["items"]}
    second_ids = {item["badCaseId"] for item in second_payload["items"]}
    assert not first_ids & second_ids
    assert first_ids | second_ids == {
        "a-deep-self-1",
        "a-deep-discovery-2",
        "a-explore-self-3",
        "a-workflow-discovery-4",
        "a-deep-self-5",
        "a-explore-self-6",
        "a-extra-1",
        "a-extra-2",
        "a-extra-3",
        "a-extra-4",
    }


async def test_list_page_size_stays_within_bounds(
    overview: OverviewEnvironment,
) -> None:
    """An explicit pageSize of 2 is honoured and still reports the full total."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("pageSize", "2")],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pageSize"] == 2
    assert len(payload["items"]) == 2
    assert payload["total"] == 6


async def test_list_ties_break_by_bad_case_id_ascending(
    overview: OverviewEnvironment,
) -> None:
    """Rows sharing createdAt keep a stable bad_case_id ascending order."""
    environment = overview
    tied_at = _at(environment.day0, 12, 0)
    async with environment.database.transaction() as session:
        await session.execute(
            insert(bad_cases),
            [
                _case(
                    case_id="a-tie-zulu",
                    workspace_id=environment.workspace_a,
                    session_id=SESSION_1,
                    bad_case_type="self",
                    object_name="tie-object",
                    created_at=tied_at,
                ),
                _case(
                    case_id="a-tie-alpha",
                    workspace_id=environment.workspace_a,
                    session_id=SESSION_1,
                    bad_case_type="self",
                    object_name="tie-object",
                    created_at=tied_at,
                ),
            ],
        )

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("objects", "tie-object")],
    )

    assert response.status_code == 200
    assert [item["badCaseId"] for item in response.json()["items"]] == [
        "a-tie-alpha",
        "a-tie-zulu",
    ]


async def test_list_filters_compose(
    overview: OverviewEnvironment,
) -> None:
    """Type, objects, and window filters intersect without leaking other rows."""
    environment = overview
    base = _in_window(environment)

    self_only = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*base, ("badCaseType", "self")],
    )
    discovery_only = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*base, ("badCaseType", "discovery")],
    )
    explore = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*base, ("objects", "Explore")],
    )
    last_day = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*base, ("from", environment.day0.isoformat())],
    )

    assert self_only.json()["total"] == 4
    assert {item["badCaseType"] for item in self_only.json()["items"]} == {"self"}
    assert discovery_only.json()["total"] == 2
    assert [item["badCaseId"] for item in explore.json()["items"]] == [
        "a-explore-self-3",
        "a-explore-self-6",
    ]
    assert last_day.json()["total"] == 2


async def test_list_attribution_count_uses_distinct_object_version_triples(
    overview: OverviewEnvironment,
) -> None:
    """A linked probe counts once per case; unlinked and missing rows count zero."""
    environment = overview
    stamp = _at(environment.day0, 16, 0)
    async with environment.database.transaction() as session:
        await session.execute(
            insert(probe_reports),
            [
                _probe(probe_id="probe-v1", object_version="v1", created_at=stamp),
                _probe(probe_id="probe-v2", object_version="v2", created_at=stamp),
                _probe(probe_id="probe-null", object_version=None, created_at=stamp),
            ],
        )
        await session.execute(
            insert(bad_case_analysis),
            [
                _analysis(case_id="a-deep-self-1", probe_id="probe-v1", updated_at=stamp),
                _analysis(case_id="a-explore-self-3", probe_id="probe-v2", updated_at=stamp),
                _analysis(case_id="a-deep-discovery-2", probe_id="probe-null", updated_at=stamp),
            ],
        )

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=_in_window(environment),
    )

    assert response.status_code == 200
    counts = {item["badCaseId"]: item["attributionCount"] for item in response.json()["items"]}
    assert counts == {
        "a-deep-self-1": 1,
        "a-deep-discovery-2": 1,
        "a-explore-self-3": 1,
        "a-workflow-discovery-4": 0,
        "a-deep-self-5": 0,
        "a-explore-self-6": 0,
    }


async def test_empty_workspace_returns_zero_totals_and_zero_buckets(
    overview: OverviewEnvironment,
) -> None:
    """A workspace without cases reports only zeros and a single continuous series."""
    environment = overview
    params = _in_window(environment)

    summary = await _get(
        environment,
        environment.workspace_c,
        "overview/summary",
        environment.carol,
        params=params,
    )
    trend = await _get(
        environment,
        environment.workspace_c,
        "overview/trend",
        environment.carol,
        params=params,
    )
    sources = await _get(
        environment,
        environment.workspace_c,
        "overview/sources",
        environment.carol,
        params=params,
    )
    cases = await _get(
        environment,
        environment.workspace_c,
        "bad-cases",
        environment.carol,
        params=params,
    )

    assert summary.json()["totals"] == {
        "badCases": 0,
        "self": 0,
        "discovery": 0,
        "sessions": 0,
        "sources": 0,
        "quota": 10,
        "used": 0,
    }
    assert summary.json()["objects"] == []
    assert [bucket["total"] for bucket in trend.json()["buckets"]] == [0, 0, 0]
    assert sources.json() == {"items": []}
    assert cases.json() == {"items": [], "total": 0, "page": 1, "pageSize": 8}


async def test_cross_workspace_rows_never_leak(
    overview: OverviewEnvironment,
) -> None:
    """A workspace only ever sees its own rows, and an invisible space is a 404."""
    environment = overview
    params = _in_window(environment)

    own = await _get(
        environment,
        environment.workspace_b,
        "bad-cases",
        environment.bob,
        params=params,
    )
    remote_summary = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.bob,
        params=params,
    )
    stranger = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.dave,
        params=params,
    )
    missing = await _get(
        environment,
        "00000000-0000-4000-8000-000000000000",
        "overview/summary",
        environment.admin,
        params=params,
    )

    assert own.status_code == 200
    assert {item["badCaseId"] for item in own.json()["items"]} == {
        "b-deep-self-1",
        "b-explore-discovery-2",
    }
    assert remote_summary.status_code == 404
    assert _error_code(remote_summary) == "WORKSPACE_NOT_FOUND"
    assert stranger.status_code == 404
    assert _error_code(stranger) == "WORKSPACE_NOT_FOUND"
    assert missing.status_code == 404
    assert _error_code(missing) == "WORKSPACE_NOT_FOUND"


async def test_global_admin_reads_any_existing_workspace(
    overview: OverviewEnvironment,
) -> None:
    """A global administrator passes the viewer check on an existing workspace."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.admin,
        params=_in_window(environment),
    )

    assert response.status_code == 200
    assert response.json()["totals"]["badCases"] == 6


async def test_auth_is_required(overview: OverviewEnvironment) -> None:
    """Every overview route rejects an unauthenticated caller."""
    environment = overview

    for suffix in (
        "overview/summary",
        "overview/trend",
        "overview/sources",
        "bad-cases",
    ):
        response = await _get(environment, environment.workspace_a, suffix, {})

        assert response.status_code == 401
        assert _error_code(response) == "AUTH_REQUIRED"


@pytest.mark.parametrize(
    "params",
    [
        _params(date_from=date(2026, 11, 10), date_to=date(2026, 11, 9)),
        _params(date_from=date(2025, 1, 1), date_to=date(2026, 1, 2)),
        _params(date_from=date(2026, 11, 9)),
        _params(date_to=date(2026, 11, 9)),
        _params(range_days=14),
        _params(range_days=0),
    ],
)
async def test_invalid_windows_report_window_invalid(
    overview: OverviewEnvironment,
    params: list[tuple[str, str]],
) -> None:
    """Reversed, oversized, half-open, and unsupported windows share WINDOW_INVALID."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )

    assert response.status_code == 422
    assert _error_code(response) == "WINDOW_INVALID"


@pytest.mark.parametrize("grain", ["hour", "DAY", "weeks", ""])
async def test_invalid_grain_reports_grain_invalid(
    overview: OverviewEnvironment,
    grain: str,
) -> None:
    """An unsupported grain is a documented GRAIN_INVALID rather than a generic 422."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/trend",
        environment.alice,
        params=[*_in_window(environment), ("grain", grain)],
    )

    assert response.status_code == 422
    assert _error_code(response) == "GRAIN_INVALID"


async def test_more_than_fifty_objects_is_rejected(overview: OverviewEnvironment) -> None:
    """51 distinct object names exceed the documented filter ceiling."""
    environment = overview
    names = ",".join(f"object-{index:02d}" for index in range(51))

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("objects", names)],
    )

    assert response.status_code == 422
    assert _error_code(response) == "OBJECT_FILTER_TOO_LARGE"
    assert response.json()["error"]["details"] == {"count": 51, "max": 50}


async def test_fifty_distinct_objects_are_accepted_and_duplicates_collapse(
    overview: OverviewEnvironment,
) -> None:
    """Exactly 50 names pass; repeats across and inside parameters never inflate the count."""
    environment = overview
    names = ",".join(f"object-{index:02d}" for index in range(50))
    padded = ",".join([*(f"object-{index:02d}" for index in range(40)), "object-00"] * 3)

    exactly_fifty = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("objects", names)],
    )
    duplicates = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("objects", padded)],
    )

    assert exactly_fifty.status_code == 200
    assert exactly_fifty.json()["total"] == 0
    assert duplicates.status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        _params(page=0),
        _params(page_size=51),
        _params(page_size=0),
    ],
)
async def test_page_bounds_are_a_generic_validation_error(
    overview: OverviewEnvironment,
    params: list[tuple[str, str]],
) -> None:
    """page < 1 and pageSize outside 1..50 stay generic 422 VALIDATION_INVALID."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), *params],
    )

    assert response.status_code == 422
    assert _error_code(response) == "VALIDATION_INVALID"


async def test_bad_case_type_all_is_the_default_sentinel(
    overview: OverviewEnvironment,
) -> None:
    """badCaseType=all is accepted and behaves exactly like an omitted filter."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("badCaseType", "all")],
    )

    assert response.status_code == 200
    assert response.json()["total"] == 6


async def test_unknown_bad_case_type_is_rejected(overview: OverviewEnvironment) -> None:
    """Only self, discovery, and the all sentinel are valid list type filters."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=[*_in_window(environment), ("badCaseType", "unknown")],
    )

    assert response.status_code == 422
    assert _error_code(response) == "VALIDATION_INVALID"


async def test_missing_bad_case_table_degrades_to_zero(
    overview: OverviewEnvironment,
) -> None:
    """A fresh installation without bad_cases answers empty aggregates, never 500."""
    environment = overview
    params = _in_window(environment)
    async with environment.database.transaction() as session:
        await session.execute(text("DROP TABLE bad_cases"))

    summary = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )
    trend = await _get(
        environment,
        environment.workspace_a,
        "overview/trend",
        environment.alice,
        params=params,
    )
    sources = await _get(
        environment,
        environment.workspace_a,
        "overview/sources",
        environment.alice,
        params=params,
    )
    cases = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=params,
    )

    assert summary.status_code == 200
    assert summary.json()["totals"] == {
        "badCases": 0,
        "self": 0,
        "discovery": 0,
        "sessions": 0,
        "sources": 0,
        "quota": 60,
        "used": 0,
    }
    assert summary.json()["objects"] == []
    assert trend.status_code == 200
    assert [bucket["total"] for bucket in trend.json()["buckets"]] == [0, 0, 0]
    assert sources.json() == {"items": []}
    assert cases.json() == {"items": [], "total": 0, "page": 1, "pageSize": 8}


async def test_missing_attribution_tables_keep_the_list_working(
    overview: OverviewEnvironment,
) -> None:
    """Attribution tables are optional; their absence only zeroes attributionCount."""
    environment = overview
    async with environment.database.transaction() as session:
        await session.execute(text("DROP TABLE bad_case_analysis"))
        await session.execute(text("DROP TABLE probe_reports"))

    response = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=_in_window(environment),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 6
    assert {item["attributionCount"] for item in payload["items"]} == {0}


async def test_window_bounds_are_inclusive_on_both_ends(
    overview: OverviewEnvironment,
) -> None:
    """A case created at 00:30 on the last day and one on the first day both count."""
    environment = overview
    params = _params(date_from=environment.day1, date_to=environment.day1)

    summary = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )
    cases = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=params,
    )

    assert summary.json()["totals"]["badCases"] == 2
    assert {item["badCaseId"] for item in cases.json()["items"]} == {
        "a-explore-self-3",
        "a-workflow-discovery-4",
    }


async def test_object_options_are_isolated_per_workspace(
    overview: OverviewEnvironment,
) -> None:
    """Each workspace's options list only its own objects, even when names are shared."""
    environment = overview
    params = _in_window(environment)
    async with environment.database.transaction() as session:
        await session.execute(
            insert(bad_cases),
            [
                _case(
                    case_id="b-only-self-3",
                    workspace_id=environment.workspace_b,
                    session_id=REMOTE_SESSION_2,
                    bad_case_type="self",
                    object_name="b-only",
                    created_at=_at(environment.day0, 11, 0),
                ),
            ],
        )

    own = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )
    remote = await _get(
        environment,
        environment.workspace_b,
        "overview/summary",
        environment.bob,
        params=params,
    )

    assert own.json()["objects"] == ["deep-research", "Explore", "workflow"]
    assert own.json()["totals"]["badCases"] == 6
    assert remote.json()["objects"] == ["b-only", "deep-research", "Explore"]
    assert remote.json()["totals"]["badCases"] == 3


@pytest.mark.parametrize(
    "params",
    [
        [("from", "9999-12-31"), ("range", "7")],
        [("to", "0001-01-01"), ("range", "7")],
        [("from", "9999-01-01"), ("to", "9999-12-31")],
    ],
)
async def test_extreme_dates_report_window_invalid(
    overview: OverviewEnvironment,
    params: list[tuple[str, str]],
) -> None:
    """Unrepresentable boundaries are a documented 422 instead of an OverflowError 500."""
    environment = overview

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )

    assert response.status_code == 422
    assert _error_code(response) == "WINDOW_INVALID"


@pytest.mark.parametrize("range_days", [0, 7, 14])
async def test_explicit_boundaries_ignore_a_leftover_range(
    overview: OverviewEnvironment,
    range_days: int,
) -> None:
    """from/to fully define the window, so an ignored range is never validated."""
    environment = overview
    params = [
        *_params(date_from=environment.day2, date_to=environment.day0),
        ("range", str(range_days)),
    ]

    response = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )

    assert response.status_code == 200
    assert response.json()["totals"]["badCases"] == 6


async def test_unknown_bad_case_type_rows_are_excluded_consistently(
    overview: OverviewEnvironment,
) -> None:
    """A legacy out-of-contract type never desyncs summary, trend, sources, or list."""
    environment = overview
    params = _in_window(environment)
    async with environment.database.transaction() as session:
        await session.execute(
            insert(bad_cases),
            [
                _case(
                    case_id="a-regression-unknown-8",
                    workspace_id=environment.workspace_a,
                    session_id=SESSION_3,
                    bad_case_type="regression",
                    object_name="legacy-object",
                    created_at=_at(environment.day0, 11, 0),
                ),
            ],
        )

    summary = await _get(
        environment,
        environment.workspace_a,
        "overview/summary",
        environment.alice,
        params=params,
    )
    trend = await _get(
        environment,
        environment.workspace_a,
        "overview/trend",
        environment.alice,
        params=params,
    )
    sources = await _get(
        environment,
        environment.workspace_a,
        "overview/sources",
        environment.alice,
        params=params,
    )
    cases = await _get(
        environment,
        environment.workspace_a,
        "bad-cases",
        environment.alice,
        params=params,
    )

    assert summary.status_code == 200
    assert summary.json()["totals"] == {
        "badCases": 6,
        "self": 4,
        "discovery": 2,
        "sessions": 3,
        "sources": 3,
        "quota": 60,
        "used": 8,
    }
    assert summary.json()["objects"] == ["deep-research", "Explore", "workflow"]
    buckets = trend.json()["buckets"]
    assert [bucket["total"] for bucket in buckets] == [2, 2, 2]
    assert sum(bucket["self"] for bucket in buckets) == 4
    assert sum(bucket["discovery"] for bucket in buckets) == 2
    assert sum(row["total"] for row in sources.json()["items"]) == 6
    assert cases.status_code == 200
    assert cases.json()["total"] == 6
    assert "a-regression-unknown-8" not in {item["badCaseId"] for item in cases.json()["items"]}
