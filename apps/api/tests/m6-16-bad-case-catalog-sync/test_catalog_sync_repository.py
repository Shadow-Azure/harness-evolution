"""Single-row catalog cursor, page upserts, and attribution progress counts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_catalog_sync import (
    BadCaseCatalogSyncRepository,
    CatalogCaseRow,
)
from app.db.crud.bad_cases import BadCaseRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases
from app.utils.time import now_shanghai


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated SQLite database with the external fixture tables."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("catalog-sync-repository-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


def _case(case_id: int, *, title: str = "case title") -> CatalogCaseRow:
    now = now_shanghai()
    return CatalogCaseRow(
        bad_case_id=case_id,
        bad_case_session_id=f"session-{case_id}",
        bad_case_type="self",
        object_name="deep-research",
        object_type="skill",
        object_version="v1",
        bad_case_agent_id=None,
        title=title,
        description="description",
        meta_data=None,
        source="test",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_state_initializes_at_cursor_zero(database: Database) -> None:
    """A missing state row is created with cursor zero and idle counters."""
    repository = BadCaseCatalogSyncRepository(database)
    assert await repository.get_state() is None

    state = await repository.initialize(now_shanghai())

    assert state.last_bad_case_id == 0
    assert state.synced_count == 0
    assert state.pending_count == 0
    assert state.status == "idle"
    assert state.attempts == 0
    assert state.last_error is None


@pytest.mark.asyncio
async def test_commit_page_inserts_then_updates(database: Database) -> None:
    """A repeated id updates the row instead of inserting and keeps analysis links."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)

    first = await repository.commit_page(
        [_case(1, title="old title")],
        last_bad_case_id=1,
        pending_count=2,
        now=now,
    )
    assert (first.inserted, first.updated) == (1, 0)

    async with database.transaction() as session:
        await session.execute(
            bad_case_analysis.insert().values(
                bad_case_id="1",
                analysis_status="analyzed_nonissue",
                probe_id=None,
                analysis_result=None,
                updated_at=now,
            ),
        )

    second = await repository.commit_page(
        [_case(1, title="new title")],
        last_bad_case_id=1,
        pending_count=0,
        now=now,
    )
    assert (second.inserted, second.updated) == (0, 1)

    async with database.session() as session:
        rows = (await session.execute(select(bad_cases))).mappings().all()
        analyses = (await session.execute(select(bad_case_analysis))).mappings().all()

    assert len(rows) == 1
    assert rows[0]["title"] == "new title"
    assert len(analyses) == 1


@pytest.mark.asyncio
async def test_commit_page_advances_cursor_and_counts(database: Database) -> None:
    """Each page commits its cursor, row count, and upstream remainder together."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)

    await repository.commit_page(
        [_case(1), _case(2)],
        last_bad_case_id=2,
        pending_count=3,
        now=now,
    )
    await repository.commit_page(
        [_case(3)],
        last_bad_case_id=3,
        pending_count=0,
        now=now,
    )

    state = await repository.get_state()
    assert state is not None
    assert state.last_bad_case_id == 3
    assert state.synced_count == 3
    assert state.pending_count == 0
    assert state.status == "running"


@pytest.mark.asyncio
async def test_mark_failed_and_idle_update_state(database: Database) -> None:
    """Failure increments attempts and idle clears the error with a success stamp."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)
    await repository.mark_running(now)
    await repository.mark_failed("BAD_CASE_QUERY_TIMEOUT", now)

    failed = await repository.get_state()
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.last_error == "BAD_CASE_QUERY_TIMEOUT"

    await repository.mark_idle(now, pending=0)
    idle = await repository.get_state()
    assert idle is not None
    assert idle.status == "idle"
    assert idle.attempts == 0
    assert idle.last_error is None
    assert idle.pending_count == 0
    assert idle.last_success_at is not None


@pytest.mark.asyncio
async def test_analysis_progress_counts_statuses(database: Database) -> None:
    """Analyzed, pending, issue, and non-issue counts follow analysis_status."""
    catalog = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await catalog.initialize(now)
    await catalog.commit_page(
        [_case(1), _case(2), _case(3), _case(4)],
        last_bad_case_id=4,
        pending_count=0,
        now=now,
    )
    async with database.transaction() as session:
        await session.execute(
            bad_case_analysis.insert(),
            [
                {
                    "bad_case_id": "1",
                    "analysis_status": "analyzed_issue",
                    "probe_id": None,
                    "analysis_result": None,
                    "updated_at": now,
                },
                {
                    "bad_case_id": "2",
                    "analysis_status": "analyzed_nonissue",
                    "probe_id": None,
                    "analysis_result": None,
                    "updated_at": now,
                },
                {
                    "bad_case_id": "3",
                    "analysis_status": "unanalyzed",
                    "probe_id": None,
                    "analysis_result": None,
                    "updated_at": now,
                },
            ],
        )

    progress = await BadCaseRepository(database).analysis_progress()

    assert progress.total == 4
    assert progress.analyzed == 2
    assert progress.pending == 2
    assert progress.issue == 1
    assert progress.non_issue == 1
