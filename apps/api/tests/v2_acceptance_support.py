"""Shared fixtures and helpers for the m11-05 V2 cross-stack acceptance tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest_asyncio
from fastapi import FastAPI

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import (
    AttributionRepository,
    EvolutionRunCandidateRepository,
)
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.crud.potential import PotentialRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import EvolutionRunRecord
from app.db.models.jobs import JobRunRecord
from app.main import create_app
from app.service.evolution.attribution import (
    AttributionEngine,
    AttributionRunner,
    RuleBasedEngine,
)
from app.service.evolution.potential import PotentialMatcher
from app.service.evolution.prepare import EvolutionPrepareService
from app.third_party_api.git.workspace import PreparedWorkspace
from app.utils.time import SHANGHAI
from tests.identity.helpers import identity_settings
from tests.m10_02_potential_support import FakeGitRemote
from tests.target_content_support import FakeTargetVersionResolver
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
)

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
"""Deterministic instant shared by the acceptance fixtures."""


@dataclass(frozen=True, slots=True)
class AcceptanceApi:
    """One migrated app, HTTP client, and database shared by a test."""

    app: FastAPI
    client: httpx.AsyncClient
    database: Database


@dataclass(frozen=True, slots=True)
class Identity:
    """One seeded user together with its bearer header."""

    user_id: str
    headers: dict[str, str]


class FakeWorkspacePreparer:
    """Return one deterministic prepared workspace without touching git."""

    async def prepare(self, run: EvolutionRunRecord) -> PreparedWorkspace:
        """Return stable paths for the prepared run."""
        return PreparedWorkspace(
            repo_path=Path("/var/lib/harness-evolution/repo"),
            path=Path("/var/lib/harness-evolution/run"),
            ref=run.target_version,
            base_commit="a" * 40,
            branch=f"evo/{run.id}",
        )


@pytest_asyncio.fixture
async def acceptance_api(tmp_path: Path) -> AsyncIterator[AcceptanceApi]:
    """Provide a migrated app with the external fixture tables bootstrapped."""
    settings = identity_settings(tmp_path)
    app = create_app(
        settings,
        git_remote=FakeGitRemote(),
        target_version_resolver=FakeTargetVersionResolver(),
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        database = app.state.database
        await ensure_fixture_external_tables(database)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield AcceptanceApi(app=app, client=client, database=database)


async def seed_identity(
    app: FastAPI,
    database: Database,
    *,
    username: str,
    workspace_id: str | None = None,
    workspace_role: str = "viewer",
    global_role: str = "member",
) -> Identity:
    """Insert one user, optionally join a workspace, and mint its bearer header."""
    user_id = await create_user(
        database,
        username=username,
        role=global_role,
    )
    if workspace_id is not None:
        await insert_member(
            database,
            workspace_id=workspace_id,
            user_id=user_id,
            role=workspace_role,
        )
    token = access_token(app, user_id=user_id, role=global_role)
    return Identity(user_id=user_id, headers=bearer(token))


async def seed_run(
    database: Database,
    *,
    run_id: str,
    workspace_id: str,
    target_type: str = "skill",
    target_name: str = "deep-research",
    target_version: str = "v2.0.0",
    window_from: date = date(2026, 11, 1),
    window_to: date = date(2026, 11, 30),
    mode: str = "cluster_only",
    status: str = "preparing",
    cache_enabled: bool = True,
    potential_policy: dict[str, object] | None = None,
) -> None:
    """Insert one V2 run snapshot through the production run repository."""
    await EvolutionRepository(database).create_run(
        {
            "id": run_id,
            "title": f"{target_name} {target_version} 自进化",
            "workspace_id": workspace_id,
            "mode": mode,
            "engine_key": "full" if mode == "full" else "cluster_only",
            "eval_config": {},
            "potential_policy": potential_policy or {"preset": "default"},
            "cache_enabled": cache_enabled,
            "attribution_engine": "rule-v1",
            "target_config_id": None,
            "target_type": target_type,
            "target_name": target_name,
            "target_version": target_version,
            "repo_url": f"https://example.invalid/{target_name}.git",
            "sub_dir": f"{target_type}s/{target_name}",
            "validation_project_id": "validation-project",
            "test_project_id": "test-project",
            "window_from": window_from,
            "window_to": window_to,
            "models": ["glm-5.3"],
            "status": status,
        },
    )


def prepare_job(run_id: str) -> JobRunRecord:
    """Build one ``evolution_prepare`` job row for the service under test."""
    return JobRunRecord(
        id=f"job-{run_id}",
        kind="evolution_prepare",
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="test",
        external_job_id=None,
        attempt=1,
        payload={"runId": run_id},
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


def prepare_service(
    database: Database,
    *,
    engine_factory: Callable[[str], AttributionEngine] | None = None,
) -> EvolutionPrepareService:
    """Compose the M10-04 prepare service over one migrated test database."""
    matcher = PotentialMatcher(PotentialRepository(database))
    attributions = AttributionRepository(database)
    runner = AttributionRunner(
        attributions,
        engine_factory=engine_factory or (lambda _key: RuleBasedEngine()),
    )
    return EvolutionPrepareService(
        EvolutionRepository(database),
        EvolutionRunCandidateRepository(database),
        attributions,
        matcher,
        runner,
        FakeWorkspacePreparer(),
    )


async def migrated_database(tmp_path: Path, name: str) -> Database:
    """Create, start, and migrate one isolated SQLite database."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / name}",
        ),
    )
    await database.start()
    try:
        await upgrade_database(database)
    except Exception:
        await database.dispose()
        raise
    return database
