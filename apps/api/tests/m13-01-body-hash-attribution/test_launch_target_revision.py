"""Launch resolves and persists the body-hash target revision on the run."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select

from app.config import Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.evolution import evolution_runs
from app.main import create_app
from app.service.evolution.target_content import ResolvedTargetVersion
from tests.identity.helpers import identity_settings
from tests.m10_02_potential_support import (
    NOW,
    FakeGitRemote,
    seed_case,
    seed_event,
    seed_session,
    seed_target,
    seed_workspace,
)
from tests.v2_acceptance_support import seed_identity

WORKSPACE_ID = "ws-m13-launch"
TARGET_NAME = "deep-research"
TARGET_VERSION = "v2.0.0"


class DigestTargetResolver:
    """Return the deterministic body-hash revision a real content read would produce."""

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Resolve a bare version to one stable digest revision."""
        del object_type, repo_url, sub_dir
        digest = hashlib.sha256(version.encode("utf-8")).hexdigest()
        return ResolvedTargetVersion(version, f"digest:{digest}")


@pytest_asyncio.fixture
async def launch_client(tmp_path: Path) -> AsyncIterator[Any]:
    """Provide an authenticated space administrator and one associated Session."""
    settings: Settings = identity_settings(tmp_path)
    app = create_app(
        settings,
        git_remote=FakeGitRemote(),
        target_version_resolver=DigestTargetResolver(),
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        database = app.state.database
        await ensure_fixture_external_tables(database)
        await seed_workspace(database, WORKSPACE_ID)
        await seed_target(database, workspace_id=WORKSPACE_ID, default_ref=TARGET_VERSION)
        identity = await seed_identity(
            app,
            database,
            username="m13-launch-admin",
            workspace_id=WORKSPACE_ID,
            workspace_role="space_admin",
        )
        main_id = await seed_session(database, session_id="session-m13-launch", started_at=NOW)
        await seed_event(
            database,
            agent_id=main_id,
            event_index=0,
            kind="skill",
            name=TARGET_NAME,
            object_version=TARGET_VERSION,
            triggered_at=NOW,
        )
        await seed_case(
            database,
            case_id="case-m13-launch",
            session_id="session-m13-launch",
            workspace_id=WORKSPACE_ID,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=NOW,
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, identity.headers, database


async def test_launch_persists_target_revision_and_returns_it_on_the_run_card(
    launch_client: Any,
) -> None:
    """A bare tag is resolved before the run snapshot and cache keys are built."""
    client, headers, database = launch_client
    response = await client.post(
        f"/api/workspaces/{WORKSPACE_ID}/evolution/cluster-previews",
        headers=headers,
        json={
            "targetType": "skill",
            "targetName": TARGET_NAME,
            "targetVersion": TARGET_VERSION,
            "mode": "cluster_only",
            "cacheEnabled": False,
        },
    )

    assert response.status_code == 202
    run_id = response.json()["runId"]
    expected_revision = f"digest:{hashlib.sha256(TARGET_VERSION.encode()).hexdigest()}"
    async with database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_runs).where(evolution_runs.c.id == run_id),
                )
            )
            .mappings()
            .one()
        )
    assert row["target_version"] == TARGET_VERSION
    assert row["target_revision"] == expected_revision

    detail = await client.get(
        f"/api/workspaces/{WORKSPACE_ID}/evolution/runs/{run_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    target = detail.json()["target"]
    assert target["version"] == TARGET_VERSION
    assert target["targetRevision"] == expected_revision
