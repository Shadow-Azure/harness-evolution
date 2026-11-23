"""Step 6 reads round patch bundles, not the raw stored dictionary.

The candidate writer persists ``files[]``/``note``/``intent``/``report`` (and
the legacy single-file keys when there is one file). This regression feeds the
writer's real output through ``GET /steps/iteration`` so a future read model
cannot silently drift from the stored shape again.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.main import create_app
from app.service.evolution.git_candidate import _stored_patch
from app.service.evolution.patch_source import PatchBundle
from app.third_party_api.git.workspace import Patch
from tests.six_step_seed import load_fixture, seed_fixture

ADMIN_TEMP_PASSWORD = "iteration-round-patch-admin-temp-password"
ADMIN_PASSWORD = "iteration-round-patch-admin-password"


@pytest_asyncio.fixture
async def iteration_api(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an authenticated admin client over a migrated application."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("iteration-round-patch-signing-secret-sufficient-length"),
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


def _database(client: httpx.AsyncClient) -> Database:
    """Return the application database behind one ASGI transport."""
    app = cast(Any, client._transport).app
    return cast(Database, app.state.database)


def _round(
    round_id: str,
    seq: int,
    patch: dict[str, object],
    *,
    cluster_id: str = "C1",
) -> dict[str, Any]:
    """Build one round fixture entry around an exact stored patch payload."""
    return {
        "id": round_id,
        "probeClusterId": cluster_id,
        "seq": seq,
        "status": "accepted",
        "patch": patch,
        "candidate": {
            "ref": f"evo/iteration-patch/candidate/r{seq}",
            "commit": f"{seq}" * 40,
            "message": "evolve(deep-research@v2.0.0): 候选变更",
        },
        "push": {"status": "succeeded", "attempts": 1, "error": None},
        "eval": {
            "status": "completed",
            "current": 84.0,
            "candidate": 85.0 + seq,
            "nextPollAt": None,
        },
        "accepted": True,
        "finalCommit": {
            "hash": f"{seq + 1}" * 40,
            "message": "evolve(deep-research@v2.0.0): 已接纳",
        },
    }


async def test_iteration_projects_single_and_multi_file_stored_bundles(
    iteration_api: httpx.AsyncClient,
) -> None:
    """Writer-shaped bundles from one and two files return 200 with files[]."""
    single = PatchBundle(
        files=(
            Patch(
                file="SKILL.md",
                lines=("@@ -1 +1 @@", "- 读取索引", "+ 读取索引前校验快照字段"),
            ),
        ),
        note="启用快照字段校验",
    )
    multi = PatchBundle(
        files=(
            Patch(
                file="SKILL.md",
                lines=("@@ -1 +1 @@", "- 读取索引", "+ 读取索引前校验快照字段"),
            ),
            Patch(
                file="config/synthetic-review.json",
                lines=('  "requestTimeoutSeconds": 60,',),
                overwrite=True,
            ),
        ),
        note="多文件修复",
    )
    data = load_fixture("iteration")
    data["run"]["progressUnit"] = 7
    data["rounds"] = [
        _round("round-single", 1, _stored_patch(single)),
        _round("round-multi", 2, _stored_patch(multi)),
        _round(
            "round-legacy",
            3,
            {"file": "SKILL.md", "lines": ["@@ -8 +8 @@", "- 引用可选"]},
        ),
    ]
    await seed_fixture(_database(iteration_api), data)

    response = await iteration_api.get(
        f"/api/evolution/runs/{data['run']['id']}/steps/iteration",
    )

    assert response.status_code == 200, response.text
    rounds = response.json()["payload"]["rounds"]
    assert [round_["roundId"] for round_ in rounds] == [
        "round-single",
        "round-multi",
        "round-legacy",
    ]

    single_patch = rounds[0]["patch"]
    assert single_patch["note"] == "启用快照字段校验"
    assert single_patch["files"] == [
        {
            "file": "SKILL.md",
            "lines": ["@@ -1 +1 @@", "- 读取索引", "+ 读取索引前校验快照字段"],
            "overwrite": False,
        },
    ]

    multi_patch = rounds[1]["patch"]
    assert multi_patch["note"] == "多文件修复"
    assert [file["file"] for file in multi_patch["files"]] == [
        "SKILL.md",
        "config/synthetic-review.json",
    ]
    assert multi_patch["files"][1]["overwrite"] is True

    legacy_patch = rounds[2]["patch"]
    assert legacy_patch["note"] is None
    assert legacy_patch["files"] == [
        {
            "file": "SKILL.md",
            "lines": ["@@ -8 +8 @@", "- 引用可选"],
            "overwrite": False,
        },
    ]
