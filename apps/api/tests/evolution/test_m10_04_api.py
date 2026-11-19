"""Seven-step HTTP contract: snapshots, readiness, pagination, and errors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any, cast

import httpx
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import CandidateWrite, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.main import create_app
from app.service.evolution.state import STEP_KEYS
from tests.six_step_seed import (
    CASE_ID,
    NOW,
    SESSION_ID,
    load_fixture,
    seed_external_corpus,
    seed_fixture,
)

ADMIN_TEMP_PASSWORD = "seven-step-admin-temp-password"
ADMIN_PASSWORD = "seven-step-admin-password"


@pytest_asyncio.fixture
async def steps_api(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an authenticated admin client over a migrated application."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("seven-step-api-signing-secret-sufficient-length"),
            admin_username="admin",
            admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            login = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": ADMIN_TEMP_PASSWORD},
            )
            assert login.status_code == 200
            changed = await client.post(
                "/api/auth/change-password",
                headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
                json={"oldPassword": ADMIN_TEMP_PASSWORD, "newPassword": ADMIN_PASSWORD},
            )
            assert changed.status_code == 204
            relogin = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": ADMIN_PASSWORD},
            )
            assert relogin.status_code == 200
            client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"
            yield client
    finally:
        await client.aclose()


def _app_of(client: httpx.AsyncClient) -> Any:
    """Return the composed test application behind an ASGI transport."""
    return cast(Any, client._transport).app


async def _database(client: httpx.AsyncClient) -> Database:
    """Return the application database through the composed app state."""
    return cast(Database, _app_of(client).state.database)


def _step_url(run_id: str, key: str) -> str:
    """Build one seven-step endpoint path."""
    return f"/api/evolution/runs/{run_id}/steps/{key}"


async def test_step_endpoints_require_authentication(
    steps_api: httpx.AsyncClient,
) -> None:
    """Step payloads are only readable for authenticated users."""
    steps_api.headers.pop("Authorization", None)
    for key in STEP_KEYS:
        response = await steps_api.get(_step_url("evo-20261023-02", key))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_legacy_run_serves_seven_steps_through_one_builder(
    steps_api: httpx.AsyncClient,
) -> None:
    """A legacy run maps onto the same seven-step envelope as a V2 run."""
    database = await _database(steps_api)
    await seed_external_corpus(database)
    data = load_fixture("clusters")
    await seed_fixture(database, data)
    run_id = data["run"]["id"]

    seen: list[str] = []
    for key in STEP_KEYS[:-1]:
        response = await steps_api.get(_step_url(run_id, key))
        assert response.status_code == 200
        body = response.json()
        seen.append(body["key"])
        assert body["index"] == STEP_KEYS.index(key)
        assert body["title"]
        assert body["status"] in {"done", "active"}

    assert seen == list(STEP_KEYS[:-1])
    final = await steps_api.get(_step_url(run_id, "final"))
    assert final.status_code == 404
    assert final.json()["error"]["code"] == "STEP_NOT_READY"

    clusters = await steps_api.get(_step_url(run_id, "clusters"))
    cluster = clusters.json()["payload"]["clusters"][0]
    assert cluster["category"] == "error"
    assert cluster["caseCount"] >= 1
    assert cluster["cases"]

    sessions = await steps_api.get(
        _step_url(run_id, "sessions"),
        params={"page": 1, "pageSize": 4},
    )
    assert sessions.status_code == 200
    assert sessions.json()["payload"]["pageSize"] == 4


async def test_cluster_only_hides_iteration_and_final(
    steps_api: httpx.AsyncClient,
) -> None:
    """Cluster-only runs stop reading after the cluster step."""
    database = await _database(steps_api)
    await seed_external_corpus(database)
    data = load_fixture("clusters")
    data["run"]["mode"] = "cluster_only"
    data["run"]["status"] = "completed"
    await seed_fixture(database, data)
    run_id = data["run"]["id"]

    assert (await steps_api.get(_step_url(run_id, "clusters"))).status_code == 200
    for key in ("iteration", "final"):
        response = await steps_api.get(_step_url(run_id, key))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "STEP_NOT_READY"


async def test_unknown_run_returns_not_found(steps_api: httpx.AsyncClient) -> None:
    """An unknown run uses the shared not-found error."""
    response = await steps_api.get(_step_url("missing-run", "range"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


async def test_step_range_and_potential_expose_revision_and_anchor_source(
    steps_api: httpx.AsyncClient,
) -> None:
    """Step 1 carries targetRevision and step 3 carries the audited anchorSource."""
    database = await _database(steps_api)
    await seed_external_corpus(database)
    runs = EvolutionRepository(database)
    candidates = EvolutionRunCandidateRepository(database)
    present_revision = "digest:" + "a" * 64
    await runs.create_run(
        {
            "id": "run-m13-step-present",
            "title": "deep-research v2.0.0 自进化",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "potential_policy": {"preset": "default"},
            "cache_enabled": False,
            "attribution_engine": "rule-v1",
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "target_revision": present_revision,
            "repo_url": "https://example.invalid/repo.git",
            "sub_dir": "skills/deep-research",
            "window_from": date(2026, 11, 1),
            "window_to": date(2026, 11, 30),
            "status": "running",
            "progress_unit": 5,
            "stats": {},
        },
    )
    await candidates.upsert(
        CandidateWrite(
            id="candidate-m13-step-present",
            run_id="run-m13-step-present",
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_id=SESSION_ID,
            bad_case_id=CASE_ID,
            order_state="comparable",
            included=True,
            included_reason="after_object",
            created_at=NOW,
            case_trigger_at=NOW,
            case_trigger_event_index=2_147_483_647,
            case_anchor_kind="post_process",
        ),
    )
    await runs.create_run(
        {
            "id": "run-m13-step-legacy",
            "title": "deep-research v1.0.0 自进化",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "potential_policy": {"preset": "default"},
            "cache_enabled": False,
            "attribution_engine": "legacy-probe-import",
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v1.0.0",
            "target_revision": None,
            "repo_url": "https://example.invalid/repo.git",
            "sub_dir": "skills/deep-research",
            "window_from": date(2026, 11, 1),
            "window_to": date(2026, 11, 30),
            "status": "completed",
            "progress_unit": 5,
            "stats": {},
        },
    )

    range_body = (await steps_api.get(_step_url("run-m13-step-present", "range"))).json()
    assert range_body["payload"]["condition"]["targetRevision"] == present_revision
    legacy_range = (await steps_api.get(_step_url("run-m13-step-legacy", "range"))).json()
    assert legacy_range["payload"]["condition"]["targetRevision"] is None

    potential_body = (await steps_api.get(_step_url("run-m13-step-present", "potential"))).json()
    assert potential_body["payload"]["rows"][0]["anchorSource"] == "post_process"
