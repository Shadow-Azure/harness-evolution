"""V2 workspace session projection: latest ten, exact root-ID query, totals."""

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select, text, update

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import run_corpus_seed
from app.db.models.domain import bad_cases, session_families
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)
from tests.workspaces.latest_ten_support import (
    LATEST_TEN,
    PENDING_ROOT,
    REMOTE_ROOT,
    SESSION_IDS,
    LatestTenEnvironment,
    bad_case_values,
    extra_session_values,
)

ROOT = Path(__file__).resolve().parents[4]


@pytest_asyncio.fixture
async def latest_ten(tmp_path: Path) -> AsyncIterator[LatestTenEnvironment]:
    """Seed twelve workspace roots, one remote root, and one pending root."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("session-latest-ten-test-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
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
        initial_token = login.json()["accessToken"]
        changed = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {initial_token}"},
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
        workspace_a = await insert_workspace(database, name="latest-ten-a")
        workspace_b = await insert_workspace(database, name="latest-ten-b")
        alice_id = await create_user(database, username="latest-alice")
        bob_id = await create_user(database, username="latest-bob")
        await insert_member(database, workspace_id=workspace_a, user_id=alice_id, role="viewer")
        await insert_member(database, workspace_id=workspace_b, user_id=bob_id, role="viewer")

        async with database.transaction() as session:
            base = (
                (
                    await session.execute(
                        select(session_families).where(session_families.c.id == SESSION_IDS[3])
                    )
                )
                .mappings()
                .one()
            )
            base_values = dict(base)
            await session.execute(
                update(bad_cases).values(workspace_id=workspace_a),
            )
            for index in range(5, 13):
                status = "partial" if index == 11 else "fail" if index == 12 else "ok"
                await session.execute(
                    insert(session_families).values(
                        **extra_session_values(base_values, index=index, status=status)
                    ),
                )
                await session.execute(
                    insert(bad_cases).values(
                        **bad_case_values(
                            bad_case_id=f"latest-case-{index:02d}",
                            workspace_id=workspace_a,
                            session_id=SESSION_IDS[index - 1],
                        )
                    ),
                )
            await session.execute(
                insert(session_families).values(
                    **extra_session_values(base_values, index=13, status="ok")
                ),
            )
            await session.execute(
                insert(bad_cases).values(
                    **bad_case_values(
                        bad_case_id="latest-case-13",
                        workspace_id=workspace_b,
                        session_id=REMOTE_ROOT,
                    )
                ),
            )
            await session.execute(
                insert(bad_cases).values(
                    **bad_case_values(
                        bad_case_id="latest-case-pending",
                        workspace_id=workspace_a,
                        session_id=PENDING_ROOT,
                    )
                ),
            )
            await session.execute(
                insert(bad_cases).values(
                    **bad_case_values(
                        bad_case_id="latest-case-pending-second",
                        workspace_id=workspace_a,
                        session_id=PENDING_ROOT,
                    )
                ),
            )

        yield LatestTenEnvironment(
            client=client,
            database=database,
            admin=bearer(authenticated.json()["accessToken"]),
            alice=bearer(access_token(app, user_id=alice_id)),
            bob=bearer(access_token(app, user_id=bob_id)),
            workspace_a=workspace_a,
            workspace_b=workspace_b,
        )


def _workspace_sessions(
    environment: LatestTenEnvironment,
    workspace: str,
    headers: dict[str, str],
    **params: Any,
) -> Any:
    return environment.client.get(
        f"/api/workspaces/{workspace}/sessions",
        headers=headers,
        params=params,
    )


async def test_default_returns_latest_ten_with_authoritative_total(
    latest_ten: LatestTenEnvironment,
) -> None:
    """No query means the ten most recent roots plus the unpaged total."""
    environment = latest_ten

    response = await _workspace_sessions(environment, environment.workspace_a, environment.alice)

    assert response.status_code == 200
    payload = response.json()
    ids = [item["id"] for item in payload["items"]]
    assert ids == LATEST_TEN
    assert payload["total"] == 12
    assert payload["pendingSessions"] == 1
    assert PENDING_ROOT not in ids
    started_at = [item["startedAt"] for item in payload["items"]]
    assert started_at == sorted(started_at, reverse=True)


async def test_smaller_limit_does_not_shrink_total(
    latest_ten: LatestTenEnvironment,
) -> None:
    """The page size only bounds items; total counts every match."""
    environment = latest_ten

    response = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        limit=5,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == LATEST_TEN[:5]
    assert payload["total"] == 12


async def test_full_root_id_hits_outside_latest_ten_case_insensitively(
    latest_ten: LatestTenEnvironment,
) -> None:
    """An exact full ID finds an old root, trimmed and case-insensitive."""
    environment = latest_ten
    oldest = SESSION_IDS[0]
    assert oldest not in LATEST_TEN

    response = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=f"  {oldest.upper()}  ",
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [oldest]
    assert payload["total"] == 1
    assert payload["pendingSessions"] == 1


async def test_partial_id_and_title_queries_are_not_fuzzy(
    latest_ten: LatestTenEnvironment,
) -> None:
    """V2 treats q as an exact root ID, so substrings never match."""
    environment = latest_ten

    partial = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=SESSION_IDS[0][:24],
    )
    title = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q="示例会话",
    )

    for response in (partial, title):
        assert response.status_code == 200
        payload = response.json()
        assert payload["items"] == []
        assert payload["total"] == 0
        assert payload["pendingSessions"] == 1


async def test_cross_workspace_root_is_invisible(
    latest_ten: LatestTenEnvironment,
) -> None:
    """A root projected only into another workspace never leaks through q."""
    environment = latest_ten

    leaked = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=REMOTE_ROOT,
    )
    own = await _workspace_sessions(
        environment,
        environment.workspace_b,
        environment.bob,
        q=REMOTE_ROOT,
    )
    bob_default = await _workspace_sessions(
        environment,
        environment.workspace_b,
        environment.bob,
    )

    assert leaked.json()["items"] == []
    assert leaked.json()["total"] == 0
    assert leaked.json()["pendingSessions"] == 1
    assert [item["id"] for item in own.json()["items"]] == [REMOTE_ROOT]
    assert own.json()["total"] == 1
    assert own.json()["pendingSessions"] == 0
    assert [item["id"] for item in bob_default.json()["items"]] == [REMOTE_ROOT]


async def test_exact_query_composes_with_status(
    latest_ten: LatestTenEnvironment,
) -> None:
    """q and status intersect; problem covers partial and fail."""
    environment = latest_ten
    partial_root = SESSION_IDS[10]

    ok = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=partial_root,
        status="ok",
    )
    partial = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=partial_root,
        status="partial",
    )
    problem = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=partial_root,
        status="problem",
    )
    fail = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=partial_root,
        status="fail",
    )

    assert ok.json()["items"] == []
    assert ok.json()["total"] == 0
    assert [item["id"] for item in partial.json()["items"]] == [partial_root]
    assert partial.json()["total"] == 1
    assert [item["id"] for item in problem.json()["items"]] == [partial_root]
    assert problem.json()["total"] == 1
    assert fail.json()["items"] == []
    assert fail.json()["total"] == 0


async def test_pending_root_is_counted_but_never_listed(
    latest_ten: LatestTenEnvironment,
) -> None:
    """A bad-case root without a family row only contributes pendingSessions."""
    environment = latest_ten

    response = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q=PENDING_ROOT,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["pendingSessions"] == 1


async def test_pending_root_with_two_bad_cases_counts_once(
    latest_ten: LatestTenEnvironment,
) -> None:
    """pendingSessions counts distinct roots, never scoped bad-case rows."""
    environment = latest_ten

    response = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pendingSessions"] == 1
    assert PENDING_ROOT not in [item["id"] for item in payload["items"]]


async def test_empty_workspace_returns_zero_counters(
    latest_ten: LatestTenEnvironment,
) -> None:
    """A workspace with the table present but no cases reports only zeros."""
    environment = latest_ten

    empty_workspace = await insert_workspace(environment.database, name="latest-ten-empty")
    response = await _workspace_sessions(
        environment,
        empty_workspace,
        environment.admin,
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "pendingSessions": 0}


async def test_whitespace_query_behaves_like_no_query(
    latest_ten: LatestTenEnvironment,
) -> None:
    """Trimming an all-whitespace q keeps the default latest-ten page."""
    environment = latest_ten

    response = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        q="   ",
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == LATEST_TEN
    assert payload["total"] == 12
    assert payload["pendingSessions"] == 1


async def test_ordering_breaks_started_at_ties_by_id_ascending(
    latest_ten: LatestTenEnvironment,
) -> None:
    """started_at DESC then id ASC is stable when timestamps collide."""
    environment = latest_ten
    tied_at = datetime.fromisoformat("2026-11-20T09:00:00+08:00")

    async with environment.database.transaction() as session:
        await session.execute(
            update(session_families)
            .where(session_families.c.id.in_((SESSION_IDS[10], SESSION_IDS[11])))
            .values(started_at=tied_at),
        )

    response = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.alice,
        status="problem",
    )

    assert [item["id"] for item in response.json()["items"]] == [
        SESSION_IDS[10],
        SESSION_IDS[11],
        SESSION_IDS[2],
    ]


async def test_missing_external_table_degrades_to_zero(
    latest_ten: LatestTenEnvironment,
) -> None:
    """An installation without bad_cases shows an empty projection, not 500."""
    environment = latest_ten

    async with environment.database.transaction() as session:
        await session.execute(text("DROP TABLE bad_cases"))

    response = await _workspace_sessions(environment, environment.workspace_a, environment.alice)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "pendingSessions": 0}


async def test_v1_keeps_fuzzy_search_and_default_hundred(
    latest_ten: LatestTenEnvironment,
) -> None:
    """The legacy endpoint stays fuzzy and additive-only for the new fields."""
    environment = latest_ten

    default = await environment.client.get("/api/sessions", headers=environment.admin)
    fuzzy_title = await environment.client.get(
        "/api/sessions",
        headers=environment.admin,
        params={"q": "示例会话"},
    )
    fuzzy_id = await environment.client.get(
        "/api/sessions",
        headers=environment.admin,
        params={"q": SESSION_IDS[0][:24]},
    )
    limited = await environment.client.get(
        "/api/sessions",
        headers=environment.admin,
        params={"limit": 2},
    )

    assert default.status_code == 200
    payload = default.json()
    assert len(payload["items"]) == 13
    assert payload["total"] == 13
    assert payload["pendingSessions"] == 1

    assert [item["id"] for item in fuzzy_title.json()["items"]] == list(SESSION_IDS[:4][::-1])
    assert fuzzy_title.json()["total"] == 4

    fuzzy_ids = [item["id"] for item in fuzzy_id.json()["items"]]
    assert len(fuzzy_ids) == 13
    assert SESSION_IDS[0] in fuzzy_ids

    assert len(limited.json()["items"]) == 2
    assert limited.json()["total"] == 13


def test_openapi_exposes_v2_shape_and_defaults() -> None:
    """The contract names both counters and the V2 default page size."""
    schema = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()
    components = schema["components"]["schemas"]

    assert set(components["SessionListResponse"]["properties"]) == {
        "items",
        "total",
        "pendingSessions",
    }
    assert set(components["SessionListResponse"]["required"]) == {
        "items",
        "total",
        "pendingSessions",
    }

    v1 = {
        parameter["name"]: parameter
        for parameter in schema["paths"]["/api/sessions"]["get"]["parameters"]
    }
    v2 = {
        parameter["name"]: parameter
        for parameter in schema["paths"]["/api/workspaces/{wid}/sessions"]["get"]["parameters"]
    }
    assert v1["limit"]["schema"]["default"] == 100
    assert v2["limit"]["schema"]["default"] == 10
    assert v2["q"]["schema"]["maxLength"] == 512
