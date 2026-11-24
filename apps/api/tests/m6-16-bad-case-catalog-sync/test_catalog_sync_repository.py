"""Single-row catalog cursor, owner-scoped page writes, and progress counts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_catalog_sync import (
    _UPDATE_COLUMNS,
    BadCaseCatalogSyncRepository,
    CatalogCaseRow,
    PageCounts,
)
from app.db.crud.bad_cases import BadCaseRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    BAD_CASE_ORIGIN_CATALOG,
    BAD_CASE_ORIGIN_REPORT,
    bad_case_analysis,
    bad_cases,
)
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.utils.time import as_shanghai, now_shanghai


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


def _case(
    case_id: int,
    *,
    title: str = "case title",
    description: str = "description",
    meta_data: Any = None,
    source: str = "test",
    object_version: str | None = "v1",
    bad_case_agent_id: str | None = None,
    trigger_line: int | None = None,
    timestamp: datetime | None = None,
) -> CatalogCaseRow:
    now = timestamp or now_shanghai()
    return CatalogCaseRow(
        bad_case_id=case_id,
        bad_case_session_id=f"session-{case_id}",
        bad_case_type="self",
        object_name="deep-research",
        object_type="skill",
        object_version=object_version,
        bad_case_agent_id=bad_case_agent_id,
        title=title,
        description=description,
        meta_data=meta_data,
        source=source,
        created_at=now,
        updated_at=now,
        trigger_line=trigger_line,
    )


def _columns(row: CatalogCaseRow) -> dict[str, Any]:
    """Return the column values one catalog page row writes."""
    return {
        "bad_case_session_id": row.bad_case_session_id,
        "bad_case_type": row.bad_case_type,
        "object_name": row.object_name,
        "object_type": row.object_type,
        "object_version": row.object_version,
        "bad_case_agent_id": row.bad_case_agent_id,
        "trigger_line": row.trigger_line,
        "title": row.title,
        "bad_case_description": row.description,
        "meta_data": row.meta_data,
        "source": row.source,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _value(value: Any) -> Any:
    """Normalize a stored timestamp so SQLite round-trips compare equal."""
    return as_shanghai(value) if isinstance(value, datetime) else value


async def _seed_case(
    database: Database,
    case_id: int,
    *,
    origin: str,
    title: str,
    description: str,
    meta_data: Any,
    source: str,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    session_source: Any = None,
    timestamp: datetime | None = None,
) -> None:
    """Insert one already-owned row without going through a page commit."""
    now = timestamp or now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=str(case_id),
                workspace_id=workspace_id,
                origin=origin,
                bad_case_session_id=f"session-{case_id}",
                bad_case_type="self",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title=title,
                bad_case_description=description,
                meta_data=meta_data,
                source=source,
                session_source=session_source,
                created_at=now,
                updated_at=now,
            ),
        )


async def _stored(database: Database) -> dict[str, dict[str, Any]]:
    """Return every stored bad case keyed by id."""
    async with database.session() as session:
        rows = (await session.execute(select(bad_cases))).mappings().all()
    return {str(row["bad_case_id"]): dict(row) for row in rows}


class _BlindFirstOriginsRepository(BadCaseCatalogSyncRepository):
    """Hide the first ownership read so an insert meets a committed row.

    SQLite takes the write lock before the ownership read, so a real
    two-connection interleaving cannot happen locally; hiding one read reaches
    the same primary-key race the savepoint retry exists for.
    """

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self._blind = True

    async def _origins(
        self,
        session: AsyncSession,
        bad_case_ids: Sequence[str],
        *,
        current: bool = False,
    ) -> dict[str, str]:
        """Return an empty map once, then delegate to the real ownership read."""
        if self._blind and not current:
            self._blind = False
            return {}
        return await super()._origins(session, bad_case_ids, current=current)


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
async def test_commit_page_persists_non_object_metadata(database: Database) -> None:
    """upstream meta_data may be any JSON value, not only an object."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)

    await repository.commit_page(
        [_case(1, meta_data=["tag", 1])],
        last_bad_case_id=1,
        pending_count=0,
        now=now,
    )

    async with database.session() as session:
        row = (await session.execute(select(bad_cases))).mappings().one()
    assert row["meta_data"] == ["tag", 1]


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


@pytest.mark.asyncio
async def test_commit_page_inserts_updates_or_skips_by_writer_origin(
    database: Database,
) -> None:
    """One page routes a new id, a catalog row, and a reported row three ways."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    old = now - timedelta(days=1)
    report_source = {
        "runtime": "claude-code",
        "sessionUrlTemplate": "https://trace.test/api/sessions/{sessionId}",
    }
    await _seed_case(
        database,
        1202,
        origin=BAD_CASE_ORIGIN_CATALOG,
        title="旧目录标题",
        description="旧目录描述",
        meta_data={"old": True},
        source="old-source",
        timestamp=old,
    )
    await _seed_case(
        database,
        1203,
        origin=BAD_CASE_ORIGIN_REPORT,
        title="上报时的标题",
        description="上报时的描述",
        meta_data={"report": True},
        source="report-source",
        workspace_id="ws-reported",
        session_source=report_source,
        timestamp=old,
    )
    await repository.initialize(old)
    update_row = _case(
        1202,
        title="目录新标题",
        description="目录新描述",
        meta_data={"new": True},
        source="new-source",
        object_version="v9",
        bad_case_agent_id="agent-9",
        trigger_line=77,
        timestamp=now,
    )

    counts = await repository.commit_page(
        [_case(1201, title="新目录行"), update_row, _case(1203, title="目录越权覆盖")],
        last_bad_case_id=1203,
        pending_count=0,
        now=now,
    )

    assert counts == PageCounts(inserted=1, updated=1, skipped=1)
    stored = await _stored(database)
    inserted = stored["1201"]
    assert inserted["origin"] == BAD_CASE_ORIGIN_CATALOG
    assert inserted["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert inserted["title"] == "新目录行"
    expected = _columns(update_row)
    for column in _UPDATE_COLUMNS:
        assert _value(stored["1202"][column]) == _value(expected[column]), column
    assert stored["1202"]["origin"] == BAD_CASE_ORIGIN_CATALOG
    assert stored["1202"]["workspace_id"] == DEFAULT_WORKSPACE_ID
    protected = stored["1203"]
    assert protected["origin"] == BAD_CASE_ORIGIN_REPORT
    assert protected["workspace_id"] == "ws-reported"
    assert protected["title"] == "上报时的标题"
    assert protected["bad_case_description"] == "上报时的描述"
    assert protected["meta_data"] == {"report": True}
    assert protected["source"] == "report-source"
    assert protected["session_source"] == report_source
    assert _value(protected["created_at"]) == _value(old)


@pytest.mark.asyncio
async def test_reported_rows_stay_protected_across_pages_and_synced_count_is_real(
    database: Database,
) -> None:
    """A later page also skips the reported id while the row counter stays truthful."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)
    await _seed_case(
        database,
        1203,
        origin=BAD_CASE_ORIGIN_REPORT,
        title="上报时的标题",
        description="上报时的描述",
        meta_data={"report": True},
        source="report-source",
        workspace_id="ws-reported",
    )

    first = await repository.commit_page(
        [_case(1201), _case(1203, title="第一页越权")],
        last_bad_case_id=1203,
        pending_count=2,
        now=now,
    )
    second = await repository.commit_page(
        [_case(1202), _case(1203, title="第二页越权")],
        last_bad_case_id=1204,
        pending_count=0,
        now=now,
    )

    assert (first.inserted, first.updated, first.skipped) == (1, 0, 1)
    assert (second.inserted, second.updated, second.skipped) == (1, 0, 1)
    stored = await _stored(database)
    assert set(stored) == {"1201", "1202", "1203"}
    assert stored["1203"]["title"] == "上报时的标题"
    state = await repository.get_state()
    assert state is not None
    assert state.last_bad_case_id == 1204
    assert state.synced_count == 3


@pytest.mark.parametrize(
    ("origin", "expected_counts", "expected_title"),
    [
        pytest.param(
            BAD_CASE_ORIGIN_CATALOG,
            PageCounts(inserted=0, updated=1, skipped=0),
            "竞争后的目录标题",
            id="catalog-owned",
        ),
        pytest.param(
            BAD_CASE_ORIGIN_REPORT,
            PageCounts(inserted=0, updated=0, skipped=1),
            "上报时的标题",
            id="report-owned",
        ),
    ],
)
@pytest.mark.asyncio
async def test_commit_page_recovers_from_a_primary_key_race_by_real_origin(
    database: Database,
    origin: str,
    expected_counts: PageCounts,
    expected_title: str,
) -> None:
    """A stale ownership read degrades to update or skip instead of IntegrityError."""
    repository = _BlindFirstOriginsRepository(database)
    now = now_shanghai()
    await _seed_case(
        database,
        1202,
        origin=origin,
        title="上报时的标题" if origin == BAD_CASE_ORIGIN_REPORT else "旧目录标题",
        description="description",
        meta_data=None,
        source="existing-source",
    )
    await repository.initialize(now)

    counts = await repository.commit_page(
        [_case(1202, title="竞争后的目录标题")],
        last_bad_case_id=1202,
        pending_count=0,
        now=now,
    )

    assert counts == expected_counts
    stored = await _stored(database)
    assert stored["1202"]["origin"] == origin
    assert stored["1202"]["title"] == expected_title
    state = await repository.get_state()
    assert state is not None
    assert state.last_bad_case_id == 1202
    assert state.synced_count == 1
