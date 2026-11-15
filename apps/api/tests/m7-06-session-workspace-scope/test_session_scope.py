"""Cross-workspace contracts for Session and bad-case read paths."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import update

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import run_corpus_seed
from app.db.models.domain import bad_cases
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app
from app.utils.time import now_shanghai
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)
from tests.workspaces.scope_support import (
    CASE_S1_A,
    CASE_S1_B,
    CASE_S2_B,
    CASE_S3_A,
    CASE_S4_DEFAULT,
    SESSION_1,
    SESSION_2,
    SESSION_3,
    SESSION_4,
    ScopeEnvironment,
)

ROOT = Path(__file__).resolve().parents[4]


@pytest_asyncio.fixture
async def scope_environment(tmp_path: Path) -> AsyncIterator[ScopeEnvironment]:
    """Seed two workspaces that share one root Session plus one legacy-only Session."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("session-workspace-scope-test-secret"),
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
        workspace_a = await insert_workspace(database, name="scope-a")
        workspace_b = await insert_workspace(database, name="scope-b")
        alice_id = await create_user(database, username="scope-alice")
        bob_id = await create_user(database, username="scope-bob")
        carol_id = await create_user(database, username="scope-carol")
        dave_id = await create_user(database, username="scope-dave")
        await insert_member(database, workspace_id=workspace_a, user_id=alice_id, role="viewer")
        await insert_member(database, workspace_id=workspace_b, user_id=bob_id, role="viewer")
        await insert_member(database, workspace_id=workspace_a, user_id=carol_id, role="viewer")
        await insert_member(database, workspace_id=workspace_b, user_id=carol_id, role="viewer")

        async with database.transaction() as session:
            await session.execute(
                update(bad_cases)
                .where(bad_cases.c.bad_case_id.in_((CASE_S1_A, CASE_S3_A)))
                .values(workspace_id=workspace_a),
            )
            await session.execute(
                update(bad_cases)
                .where(bad_cases.c.bad_case_id == CASE_S2_B)
                .values(workspace_id=workspace_b),
            )
            await session.execute(
                bad_cases.insert().values(
                    bad_case_id=CASE_S1_B,
                    workspace_id=workspace_b,
                    bad_case_session_id=SESSION_1,
                    bad_case_type="discovery",
                    object_name="Explore",
                    object_type="agent",
                    object_version="synthetic-1",
                    bad_case_agent_id="agent-s1-review-0001",
                    title="另一空间的同会话问题",
                    bad_case_description="同一根会话被两个空间分别上报。",
                    meta_data={"fixture": True},
                    source="fixtures",
                    created_at=now_shanghai(),
                    updated_at=now_shanghai(),
                ),
            )

        yield ScopeEnvironment(
            client=client,
            database=database,
            admin=bearer(authenticated.json()["accessToken"]),
            alice=bearer(access_token(app, user_id=alice_id)),
            bob=bearer(access_token(app, user_id=bob_id)),
            carol=bearer(access_token(app, user_id=carol_id)),
            dave=bearer(access_token(app, user_id=dave_id)),
            workspace_a=workspace_a,
            workspace_b=workspace_b,
        )


def _ids(payload: dict[str, Any]) -> list[str]:
    return [item["id"] for item in payload["items"]]


def _workspace_sessions(
    environment: ScopeEnvironment, workspace: str, headers: dict[str, str]
) -> Any:
    return environment.client.get(
        f"/api/workspaces/{workspace}/sessions",
        headers=headers,
    )


async def test_workspace_session_list_is_projected_from_its_bad_cases(
    scope_environment: ScopeEnvironment,
) -> None:
    """Each workspace sees only the root sessions its own bad cases mention."""
    environment = scope_environment

    alice = await _workspace_sessions(environment, environment.workspace_a, environment.alice)
    assert alice.status_code == 200
    assert _ids(alice.json()) == [SESSION_3, SESSION_1]
    alice_counts = {item["id"]: item["stats"]["badCases"] for item in alice.json()["items"]}
    assert alice_counts == {SESSION_1: 1, SESSION_3: 1}

    bob = await _workspace_sessions(environment, environment.workspace_b, environment.bob)
    assert bob.status_code == 200
    assert _ids(bob.json()) == [SESSION_2, SESSION_1]
    bob_counts = {item["id"]: item["stats"]["badCases"] for item in bob.json()["items"]}
    assert bob_counts == {SESSION_1: 1, SESSION_2: 1}

    carol = await _workspace_sessions(environment, environment.workspace_a, environment.carol)
    assert carol.status_code == 200
    assert _ids(carol.json()) == [SESSION_3, SESSION_1]
    assert {item["id"]: item["stats"]["badCases"] for item in carol.json()["items"]} == {
        SESSION_1: 1,
        SESSION_3: 1,
    }

    carol_legacy = await environment.client.get("/api/sessions", headers=environment.carol)
    assert {item["id"]: item["stats"]["badCases"] for item in carol_legacy.json()["items"]} == {
        SESSION_1: 2,
        SESSION_2: 1,
        SESSION_3: 1,
    }


async def test_global_admin_reads_any_workspace_without_membership(
    scope_environment: ScopeEnvironment,
) -> None:
    """A global administrator passes through every existing workspace."""
    environment = scope_environment

    response = await _workspace_sessions(
        environment,
        environment.workspace_b,
        environment.admin,
    )

    assert response.status_code == 200
    assert _ids(response.json()) == [SESSION_2, SESSION_1]


async def test_invisible_workspace_and_session_share_one_404(
    scope_environment: ScopeEnvironment,
) -> None:
    """A workspace the caller cannot see and a session outside it both answer 404."""
    environment = scope_environment

    hidden = await _workspace_sessions(
        environment,
        environment.workspace_b,
        environment.alice,
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"

    outsider = await _workspace_sessions(
        environment,
        environment.workspace_a,
        environment.dave,
    )
    assert outsider.status_code == 404
    assert outsider.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"

    for suffix in ("", "/tree", "/bad-cases"):
        response = await environment.client.get(
            f"/api/workspaces/{environment.workspace_a}/sessions/{SESSION_2}{suffix}",
            headers=environment.alice,
        )
        assert response.status_code == 404, suffix
        assert response.json()["error"]["code"] == "SESSION_NOT_FOUND", suffix

    default_only = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/sessions/{SESSION_4}",
        headers=environment.alice,
    )
    assert default_only.status_code == 404
    assert default_only.json()["error"]["code"] == "SESSION_NOT_FOUND"


async def test_same_session_reported_by_two_workspaces_stays_partitioned(
    scope_environment: ScopeEnvironment,
) -> None:
    """One shared root Session shows each workspace only its own bad cases."""
    environment = scope_environment

    alice_tree = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/sessions/{SESSION_1}/tree",
        headers=environment.alice,
    )
    assert alice_tree.status_code == 200
    assert [case["badCaseId"] for case in alice_tree.json()["badCases"]] == [CASE_S1_A]

    bob_tree = await environment.client.get(
        f"/api/workspaces/{environment.workspace_b}/sessions/{SESSION_1}/tree",
        headers=environment.bob,
    )
    assert bob_tree.status_code == 200
    assert [case["badCaseId"] for case in bob_tree.json()["badCases"]] == [CASE_S1_B]

    carol_tree = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/sessions/{SESSION_1}/tree",
        headers=environment.carol,
    )
    assert carol_tree.status_code == 200
    assert [case["badCaseId"] for case in carol_tree.json()["badCases"]] == [CASE_S1_A]

    carol_legacy_tree = await environment.client.get(
        f"/api/sessions/{SESSION_1}/tree",
        headers=environment.carol,
    )
    assert [case["badCaseId"] for case in carol_legacy_tree.json()["badCases"]] == [
        CASE_S1_A,
        CASE_S1_B,
    ]

    alice_cases = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/sessions/{SESSION_1}/bad-cases",
        headers=environment.alice,
    )
    assert alice_cases.status_code == 200
    assert [case["badCaseId"] for case in alice_cases.json()["items"]] == [CASE_S1_A]


async def test_workspace_bad_case_route_rejects_foreign_cases(
    scope_environment: ScopeEnvironment,
) -> None:
    """A bad case in another workspace answers BAD_CASE_NOT_FOUND, never 403."""
    environment = scope_environment

    own = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/bad-cases/{CASE_S1_A}",
        headers=environment.alice,
    )
    assert own.status_code == 200
    assert own.json()["badCaseId"] == CASE_S1_A

    foreign = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/bad-cases/{CASE_S1_B}",
        headers=environment.alice,
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"

    bob_foreign = await environment.client.get(
        f"/api/workspaces/{environment.workspace_b}/bad-cases/{CASE_S1_A}",
        headers=environment.bob,
    )
    assert bob_foreign.status_code == 404
    assert bob_foreign.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"


async def test_legacy_session_endpoints_filter_by_all_visible_workspaces(
    scope_environment: ScopeEnvironment,
) -> None:
    """The V1 endpoints keep working with the union of the caller's spaces."""
    environment = scope_environment

    alice = await environment.client.get("/api/sessions", headers=environment.alice)
    assert alice.status_code == 200
    assert _ids(alice.json()) == [SESSION_3, SESSION_1]

    bob = await environment.client.get("/api/sessions", headers=environment.bob)
    assert _ids(bob.json()) == [SESSION_2, SESSION_1]

    carol = await environment.client.get("/api/sessions", headers=environment.carol)
    assert _ids(carol.json()) == [SESSION_3, SESSION_2, SESSION_1]
    carol_session = await environment.client.get(
        f"/api/sessions/{SESSION_1}",
        headers=environment.carol,
    )
    assert carol_session.status_code == 200
    assert carol_session.json()["stats"]["badCases"] == 2

    dave = await environment.client.get("/api/sessions", headers=environment.dave)
    assert dave.status_code == 200
    assert dave.json()["items"] == []

    admin = await environment.client.get("/api/sessions", headers=environment.admin)
    assert _ids(admin.json()) == [SESSION_4, SESSION_3, SESSION_2, SESSION_1]


async def test_legacy_detail_tree_and_case_routes_enforce_visibility(
    scope_environment: ScopeEnvironment,
) -> None:
    """Legacy deep links cannot read a Session or case outside visible spaces."""
    environment = scope_environment

    for suffix in ("", "/tree", "/bad-cases"):
        hidden = await environment.client.get(
            f"/api/sessions/{SESSION_2}{suffix}",
            headers=environment.alice,
        )
        assert hidden.status_code == 404, suffix
        assert hidden.json()["error"]["code"] == "SESSION_NOT_FOUND", suffix

    outsider = await environment.client.get(
        f"/api/sessions/{SESSION_1}",
        headers=environment.dave,
    )
    assert outsider.status_code == 404
    assert outsider.json()["error"]["code"] == "SESSION_NOT_FOUND"

    alice_tree = await environment.client.get(
        f"/api/sessions/{SESSION_1}/tree",
        headers=environment.alice,
    )
    assert [case["badCaseId"] for case in alice_tree.json()["badCases"]] == [CASE_S1_A]

    alice_own = await environment.client.get(
        f"/api/bad-cases/{CASE_S1_A}",
        headers=environment.alice,
    )
    assert alice_own.status_code == 200

    alice_foreign = await environment.client.get(
        f"/api/bad-cases/{CASE_S1_B}",
        headers=environment.alice,
    )
    assert alice_foreign.status_code == 404
    assert alice_foreign.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"

    bob_foreign = await environment.client.get(
        f"/api/bad-cases/{CASE_S1_A}",
        headers=environment.bob,
    )
    assert bob_foreign.status_code == 404
    assert bob_foreign.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"

    admin_foreign = await environment.client.get(
        f"/api/bad-cases/{CASE_S1_B}",
        headers=environment.admin,
    )
    assert admin_foreign.status_code == 200
    assert admin_foreign.json()["badCaseId"] == CASE_S1_B

    default_case = await environment.client.get(
        f"/api/bad-cases/{CASE_S4_DEFAULT}",
        headers=environment.alice,
    )
    assert default_case.status_code == 404
    assert default_case.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"


async def test_legacy_session_scoped_cases_merge_visible_workspaces(
    scope_environment: ScopeEnvironment,
) -> None:
    """The legacy Session case list unions every visible space."""
    environment = scope_environment

    carol = await environment.client.get(
        f"/api/sessions/{SESSION_1}/bad-cases",
        headers=environment.carol,
    )
    assert carol.status_code == 200
    assert [case["badCaseId"] for case in carol.json()["items"]] == [
        CASE_S1_A,
        CASE_S1_B,
    ]

    alice_other = await environment.client.get(
        f"/api/sessions/{SESSION_2}/bad-cases",
        headers=environment.alice,
    )
    assert alice_other.status_code == 404
    assert alice_other.json()["error"]["code"] == "SESSION_NOT_FOUND"

    bob_other = await environment.client.get(
        f"/api/sessions/{SESSION_3}/bad-cases",
        headers=environment.bob,
    )
    assert bob_other.status_code == 404
    assert bob_other.json()["error"]["code"] == "SESSION_NOT_FOUND"

    bob_own = await environment.client.get(
        f"/api/sessions/{SESSION_2}/bad-cases",
        headers=environment.bob,
    )
    assert [case["badCaseId"] for case in bob_own.json()["items"]] == [CASE_S2_B]

    alice_own = await environment.client.get(
        f"/api/sessions/{SESSION_3}/bad-cases",
        headers=environment.alice,
    )
    assert [case["badCaseId"] for case in alice_own.json()["items"]] == [CASE_S3_A]


async def test_probe_reads_require_a_visible_problem_link(
    scope_environment: ScopeEnvironment,
) -> None:
    """A probe from another workspace's case cannot leak through a shared Session."""
    environment = scope_environment

    alice = await environment.client.get(
        "/api/probes/probe-synthetic-0001",
        headers=environment.alice,
    )
    assert alice.status_code == 200

    bob_shared_session = await environment.client.get(
        "/api/probes/probe-synthetic-0001",
        headers=environment.bob,
    )
    assert bob_shared_session.status_code == 404
    assert bob_shared_session.json()["error"]["code"] == "PROBE_NOT_FOUND"

    alice_other_case = await environment.client.get(
        "/api/probes/probe-synthetic-0003",
        headers=environment.alice,
    )
    assert alice_other_case.status_code == 404
    assert alice_other_case.json()["error"]["code"] == "PROBE_NOT_FOUND"

    admin_other_case = await environment.client.get(
        "/api/probes/probe-synthetic-0003",
        headers=environment.admin,
    )
    assert admin_other_case.status_code == 200

    bob_hidden = await environment.client.get(
        "/api/probes/probe-synthetic-0002",
        headers=environment.bob,
    )
    assert bob_hidden.status_code == 404
    assert bob_hidden.json()["error"]["code"] == "PROBE_NOT_FOUND"

    outsider = await environment.client.get(
        "/api/probes/probe-synthetic-0001",
        headers=environment.dave,
    )
    assert outsider.status_code == 404
    assert outsider.json()["error"]["code"] == "PROBE_NOT_FOUND"

    alice_list = await environment.client.get(
        f"/api/sessions/{SESSION_1}/probes",
        headers=environment.alice,
    )
    assert alice_list.status_code == 200
    assert [item["probeId"] for item in alice_list.json()["items"]] == [
        "probe-synthetic-0001",
    ]

    admin_list = await environment.client.get(
        f"/api/sessions/{SESSION_1}/probes",
        headers=environment.admin,
    )
    assert [item["probeId"] for item in admin_list.json()["items"]] == [
        "probe-synthetic-0001",
        "probe-synthetic-0003",
    ]

    hidden_session = await environment.client.get(
        f"/api/sessions/{SESSION_3}/probes",
        headers=environment.bob,
    )
    assert hidden_session.status_code == 404
    assert hidden_session.json()["error"]["code"] == "SESSION_NOT_FOUND"


async def test_workspace_routes_require_authentication(
    scope_environment: ScopeEnvironment,
) -> None:
    """Workspace-scoped reads stay behind the bearer boundary."""
    environment = scope_environment

    missing = await environment.client.get(
        f"/api/workspaces/{environment.workspace_a}/sessions",
    )
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_missing_external_bad_case_table_degrades_to_empty(
    tmp_path: Path,
) -> None:
    """A fresh database without bad_cases answers empty reads instead of 500."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("session-workspace-no-external-tables-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
    )
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
        token = login.json()["accessToken"]
        changed = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
        )
        assert changed.status_code == 204
        authenticated = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "replacement-password"},
        )
        headers = bearer(authenticated.json()["accessToken"])

        listed = await client.get("/api/sessions", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["items"] == []

        detail = await client.get(f"/api/sessions/{SESSION_1}", headers=headers)
        assert detail.status_code == 404
        assert detail.json()["error"]["code"] == "SESSION_NOT_FOUND"

        workspace = await client.get("/api/workspaces/ws-default/sessions", headers=headers)
        assert workspace.status_code == 200
        assert workspace.json()["items"] == []

        case = await client.get(
            "/api/workspaces/ws-default/bad-cases/missing-case",
            headers=headers,
        )
        assert case.status_code == 404
        assert case.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"
