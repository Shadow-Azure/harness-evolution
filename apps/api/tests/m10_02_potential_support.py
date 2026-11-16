"""Seeding helpers and harness for the m10-02 matcher and preview tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import Table, func, insert, select
from sqlalchemy.engine import CursorResult

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import attribution_cache_key
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.crud.potential import ObjectType, PotentialRepository, window_day_boundaries
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    evolution_targets,
    probe_reports,
    session_families,
    source_records,
)
from app.db.models.workspace import workspaces
from app.main import create_app
from app.service.evolution.potential import (
    ATTRIBUTION_ENGINE,
    POLICY_VERSION,
    MatchCondition,
    PotentialMatcher,
    resolve_target_revision,
)
from app.utils.time import SHANGHAI, now_shanghai
from tests.identity.helpers import identity_settings
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
)

WORKSPACE_A = "ws-m10-02-a"
WORKSPACE_B = "ws-m10-02-b"
TARGET_NAME = "deep-research"
TARGET_VERSION = "v2.0.0"
TARGET_REVISION = f"tag:{TARGET_VERSION}"
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)


@dataclass(frozen=True, slots=True)
class PreviewApi:
    """One app, client, database, viewer header, and seeded workspace."""

    app: FastAPI
    client: httpx.AsyncClient
    database: Database
    workspace_id: str
    reader: dict[str, str]
    admin: dict[str, str]


@dataclass(frozen=True, slots=True)
class Harness:
    """One migrated SQLite database with the shared matcher wired."""

    database: Database
    repository: PotentialRepository
    matcher: PotentialMatcher

    def condition(
        self,
        *,
        workspace_id: str = WORKSPACE_A,
        target_type: ObjectType = "skill",
        target_name: str = TARGET_NAME,
        target_version: str = TARGET_VERSION,
        window_from: date | None = None,
        window_to: date | None = None,
    ) -> MatchCondition:
        """Build a match condition with the same day boundaries as production."""
        start, end = window_day_boundaries(
            window_from or date(2026, 11, 1),
            window_to or date(2026, 11, 30),
        )
        resolved_version, resolved_revision = resolve_target_revision(target_version)
        return MatchCondition(
            workspace_id=workspace_id,
            target_type=target_type,
            target_name=target_name,
            target_version=resolved_version,
            target_revision=resolved_revision,
            window_start=start,
            window_end=end,
        )


@pytest_asyncio.fixture
async def harness(tmp_path: Path) -> AsyncIterator[Harness]:
    """Provide a fresh migrated database with two workspaces and one target."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'm10-02.db'}",
        ),
    )
    await database.start()
    await upgrade_database(database)
    await seed_workspace(database, WORKSPACE_A)
    await seed_workspace(database, WORKSPACE_B)
    await seed_target(database)
    repository = PotentialRepository(database)
    try:
        yield Harness(
            database=database,
            repository=repository,
            matcher=PotentialMatcher(repository),
        )
    finally:
        await database.dispose()


async def seed_workspace(database: Database, workspace_id: str) -> None:
    """Insert one active workspace row."""
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(workspaces).values(
                id=workspace_id,
                name=workspace_id,
                mark=workspace_id[-4:].upper(),
                quota=100,
                status="active",
                created_at=now,
                updated_at=now,
            ),
        )


async def seed_target(
    database: Database,
    *,
    workspace_id: str = WORKSPACE_A,
    target_id: str = "target-m10-02",
    object_type: str = "skill",
    object_name: str = TARGET_NAME,
    default_ref: str = TARGET_VERSION,
    enabled: bool = True,
) -> None:
    """Insert one workspace target."""
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(evolution_targets).values(
                id=target_id,
                workspace_id=workspace_id,
                object_type=object_type,
                object_name=object_name,
                repo_url=f"https://example.invalid/{object_name}.git",
                sub_dir=f"{object_type}s/{object_name}",
                default_ref=default_ref,
                validation_project_id="validation-project",
                test_project_id="test-project",
                enabled=enabled,
                created_at=now,
                updated_at=now,
            ),
        )


async def seed_session(
    database: Database,
    *,
    session_id: str,
    started_at: datetime = NOW,
    title: str = "Synthetic session",
    main_agent_id: str | None = None,
    tree_index: int = 0,
) -> str:
    """Insert one normalized session with its main Agent and return the Agent id."""
    main_id = main_agent_id or f"agent-main-{session_id[-8:]}"
    async with database.transaction() as session:
        inserted = await session.execute(
            insert(source_records).values(
                root_session_id=session_id,
                agent_id=main_id,
                kind="main",
                source_type="synthetic",
                line_count=1,
                received_at=started_at,
            ),
        )
        primary_key = cast(CursorResult[object], inserted).inserted_primary_key
        if primary_key is None:
            raise RuntimeError("source record insert returned no primary key")
        record_id = int(primary_key[0])
        await session.execute(
            insert(session_families).values(
                id=session_id,
                short_title=title,
                title=title,
                search_text=title,
                repo_name="example/repo",
                project_path="/workspace/repo",
                model="glm-5.3",
                models=["glm-5.3"],
                started_at=started_at,
                ended_at=started_at,
                duration_seconds=1,
                status="completed",
                skill_names=[],
                user_turns_count=1,
                messages_count=1,
                tools_count=1,
                errors_count=0,
                agents_count=1,
                tokens_total=10,
                source_type="synthetic",
                main_record_id=record_id,
                imported_at=started_at,
                updated_at=started_at,
            ),
        )
        await session.execute(
            insert(agents).values(
                id=main_id,
                root_session_id=session_id,
                kind="main",
                tree_index=tree_index,
                spawn_depth=0,
                lines=1,
                messages_count=1,
                tokens_total=10,
                tools_count=1,
                errors_count=0,
                sort_key=0.0,
            ),
        )
    return main_id


async def seed_agent(
    database: Database,
    *,
    session_id: str,
    agent_id: str,
    kind: str = "subagent",
    parent_agent_id: str | None = None,
    tool_use_id: str | None = None,
    tree_index: int = 1,
) -> None:
    """Insert one non-main Agent node."""
    async with database.transaction() as session:
        await session.execute(
            insert(agents).values(
                id=agent_id,
                root_session_id=session_id,
                parent_agent_id=parent_agent_id,
                kind=kind,
                tool_use_id=tool_use_id,
                tree_index=tree_index,
                spawn_depth=1,
                lines=1,
                messages_count=1,
                tokens_total=1,
                tools_count=0,
                errors_count=0,
                sort_key=float(tree_index),
            ),
        )


async def seed_event(
    database: Database,
    *,
    agent_id: str,
    event_index: int,
    kind: str,
    name: str | None = None,
    object_version: str | None = None,
    object_revision: str | None = None,
    triggered_at: datetime | None = NOW,
    tool_use_id: str | None = None,
) -> None:
    """Insert one trigger event with explicit coordinates."""
    async with database.transaction() as session:
        await session.execute(
            insert(agent_events).values(
                agent_id=agent_id,
                event_index=event_index,
                line_no=event_index + 1,
                message_offset=event_index,
                kind=kind,
                name=name,
                object_version=object_version,
                object_revision=object_revision,
                triggered_at=triggered_at,
                tool_use_id=tool_use_id,
            ),
        )


async def seed_case(
    database: Database,
    *,
    case_id: str,
    session_id: str,
    workspace_id: str = WORKSPACE_A,
    case_type: str = "discovery",
    object_name: str = TARGET_NAME,
    object_type: str = "skill",
    object_version: str | None = TARGET_VERSION,
    agent_id: str | None = None,
    created_at: datetime = NOW,
) -> None:
    """Insert one reported bad case."""
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=case_id,
                workspace_id=workspace_id,
                bad_case_session_id=session_id,
                bad_case_type=case_type,
                object_name=object_name,
                object_type=object_type,
                object_version=object_version,
                bad_case_agent_id=agent_id,
                title=f"case {case_id}",
                bad_case_description=f"reason {case_id}",
                created_at=created_at,
                updated_at=created_at,
            ),
        )


async def seed_probe(
    database: Database,
    *,
    case_id: str,
    session_id: str,
    workspace_id: str = WORKSPACE_A,
    probe_type: str = "skill",
    probe_object: str = TARGET_NAME,
    object_version: str = TARGET_REVISION,
    conclusion: str = "attributed",
    engine: str = ATTRIBUTION_ENGINE,
    policy: str = POLICY_VERSION,
) -> str:
    """Insert one attributed/non-target probe and its case link; return its key."""
    probe_id = f"probe-{case_id}"
    cache_key = attribution_cache_key(
        workspace_id,
        case_id,
        probe_type,
        probe_object,
        object_version,
        policy,
        engine,
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_reports).values(
                probe_id=probe_id,
                workspace_id=workspace_id,
                session_id=session_id,
                probe_type=probe_type,
                probe_object=probe_object,
                object_version=object_version,
                attribute_type="error" if conclusion == "attributed" else None,
                conclusion=conclusion,
                confidence=0.8,
                probe_description=f"probe {case_id}",
                probe_analysis=f"analysis {case_id}",
                policy_version=policy,
                attribution_engine=engine,
                cache_key=cache_key,
                created_at=now_shanghai(),
                updated_at=now_shanghai(),
            ),
        )
        await session.execute(
            insert(bad_case_analysis).values(
                bad_case_id=case_id,
                probe_id=probe_id,
                analysis_status=None,
                updated_at=now_shanghai(),
            ),
        )
    return cache_key


async def table_count(database: Database, table: Table) -> int:
    """Count all rows of one table for read-only assertions."""
    async with database.session() as session:
        count = (await session.execute(select(func.count()).select_from(table))).scalar_one()
    return int(count)


class FakeGitRemote:
    """Accept every configured remote without network access."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Accept any non-empty pair; target validation is covered elsewhere."""
        del repo_url, ref

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Return no tags; preview tests never call the version endpoint."""
        del repo_url
        return ()


@pytest_asyncio.fixture
async def preview_api(tmp_path: Path) -> AsyncIterator[PreviewApi]:
    """Provide a migrated app with a viewer, a space admin, and one target."""
    settings = identity_settings(tmp_path)
    app = create_app(settings, git_remote=FakeGitRemote())
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        database = app.state.database
        await ensure_fixture_external_tables(database)
        await seed_workspace(database, WORKSPACE_A)
        await seed_target(database)
        viewer_id = await create_user(database, username="preview-viewer", role="member")
        await insert_member(
            database,
            workspace_id=WORKSPACE_A,
            user_id=viewer_id,
            role="viewer",
        )
        admin_id = await create_user(database, username="preview-admin", role="member")
        await insert_member(
            database,
            workspace_id=WORKSPACE_A,
            user_id=admin_id,
            role="space_admin",
        )
        token = access_token(app, user_id=viewer_id)
        admin_token = access_token(app, user_id=admin_id)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield PreviewApi(
                app=app,
                client=client,
                database=database,
                workspace_id=WORKSPACE_A,
                reader=bearer(token),
                admin=bearer(admin_token),
            )
