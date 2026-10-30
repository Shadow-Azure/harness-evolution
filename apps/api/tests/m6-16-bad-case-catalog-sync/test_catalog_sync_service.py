"""Cursor paging, transactional commits, and failure isolation for catalog sync."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_catalog_sync import BadCaseCatalogSyncRepository
from app.db.crud.bad_cases import BadCaseRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases
from app.errors import AppError, ErrorCode
from app.service.acquisition.bad_case_catalog_sync import (
    BadCaseCatalogSyncService,
)
from app.third_party_api.bad_case_query.models import BadCaseItem, BadCasePage
from app.utils.time import now_shanghai


class FakeSource:
    """In-memory paginated source that mirrors the upstream cursor contract."""

    def __init__(self, items: list[BadCaseItem]) -> None:
        self.items = sorted(items, key=lambda item: item.bad_case_id)
        self.calls: list[tuple[int, int, int]] = []
        self.fail_on_call: int | None = None
        self.failure: Exception | None = None

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        self.calls.append((after_id, offset, limit))
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            assert self.failure is not None
            raise self.failure
        remaining = [item for item in self.items if item.bad_case_id > after_id]
        return BadCasePage(
            total=len(remaining),
            offset=offset,
            limit=limit,
            items=tuple(remaining[offset : offset + limit]),
        )

    async def close(self) -> None:
        return None


def _item(
    case_id: int,
    *,
    title: str | None = None,
    object_name: str | None = "deep-research",
    object_type: str | None = "skill",
    source: str | None = "test",
) -> BadCaseItem:
    return BadCaseItem(
        bad_case_id=case_id,
        bad_case_session_id=f"session-{case_id}",
        bad_case_type="self",
        object_name=object_name,
        object_type=object_type,
        object_version="v1",
        bad_case_agent_id=None,
        bad_case_title=title or f"case {case_id}",
        bad_case_description="description",
        meta_data=None,
        source=source,
        created_at=datetime.fromisoformat("2026-10-30T10:00:00+08:00"),
        updated_at=datetime.fromisoformat("2026-10-30T10:00:00+08:00"),
    )


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated SQLite database for service-level tests."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("catalog-sync-service-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


def _service(database: Database, source: FakeSource | None) -> BadCaseCatalogSyncService:
    return BadCaseCatalogSyncService(
        BadCaseCatalogSyncRepository(database),
        source,
        page_size=2,
        max_pages=10,
        time_budget_seconds=30,
    )


async def _titles(database: Database) -> dict[str, str]:
    async with database.session() as session:
        rows = (await session.execute(select(bad_cases))).mappings().all()
    return {str(row["bad_case_id"]): str(row["title"]) for row in rows}


@pytest.mark.asyncio
async def test_three_pages_commit_and_finish_idle(database: Database) -> None:
    """Five rows across three pages commit each cursor and finish idle."""
    source = FakeSource([_item(case_id) for case_id in range(1, 6)])
    service = _service(database, source)

    result = await service.run(owner="job-1")

    assert result.pages == 3
    assert result.inserted == 5
    assert result.updated == 0
    assert result.last_bad_case_id == 5
    assert result.pending == 0
    assert result.exhausted is True
    assert len(await _titles(database)) == 5
    assert [call[0] for call in source.calls] == [0, 2, 4]
    state = await BadCaseCatalogSyncRepository(database).get_state()
    assert state is not None
    assert state.status == "idle"
    assert state.last_bad_case_id == 5
    assert state.synced_count == 5
    assert state.pending_count == 0


@pytest.mark.asyncio
async def test_second_run_only_fetches_new_ids(database: Database) -> None:
    """A later run resumes at the stored cursor and inserts only new rows."""
    source = FakeSource([_item(case_id) for case_id in range(1, 4)])
    service = _service(database, source)
    await service.run(owner="job-1")
    source.items.append(_item(4))

    result = await service.run(owner="job-2")

    assert result.inserted == 1
    assert result.updated == 0
    assert result.last_bad_case_id == 4
    assert len(await _titles(database)) == 4
    assert source.calls[-1][0] == 3


async def _insert_case(
    database: Database,
    case_id: int,
    *,
    title: str,
    now: datetime,
) -> None:
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=str(case_id),
                bad_case_session_id=f"session-{case_id}",
                bad_case_type="self",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title=title,
                bad_case_description="description",
                meta_data=None,
                source="test",
                created_at=now,
                updated_at=now,
            ),
        )


@pytest.mark.asyncio
async def test_existing_row_is_updated_on_cold_start(database: Database) -> None:
    """Cold start from zero updates an existing row without duplicating it."""
    now = now_shanghai()
    await _insert_case(database, 1, title="old title", now=now)

    source = FakeSource([_item(1, title="new title"), _item(2)])
    service = _service(database, source)
    result = await service.run(owner="job-1")

    assert result.updated == 1
    assert result.inserted == 1
    assert (await _titles(database))["1"] == "new title"
    assert len(await _titles(database)) == 2


@pytest.mark.asyncio
async def test_page_failure_rolls_back_and_marks_failed(database: Database) -> None:
    """A failed page keeps the previous cursor and leaves no partial rows."""
    source = FakeSource([_item(case_id) for case_id in range(1, 6)])
    source.fail_on_call = 2
    source.failure = AppError(
        status_code=502,
        code=ErrorCode.BAD_CASE_QUERY_TIMEOUT,
        message="timeout",
    )
    service = _service(database, source)

    with pytest.raises(AppError):
        await service.run(owner="job-1")

    assert set(await _titles(database)) == {"1", "2"}
    state = await BadCaseCatalogSyncRepository(database).get_state()
    assert state is not None
    assert state.status == "failed"
    assert state.last_bad_case_id == 2
    assert state.last_error == "BAD_CASE_QUERY_TIMEOUT"
    assert state.attempts == 1


@pytest.mark.asyncio
async def test_max_pages_stops_without_failure(database: Database) -> None:
    """A page budget stops a run cleanly and leaves the remaining cursor."""
    source = FakeSource([_item(case_id) for case_id in range(1, 6)])
    service = BadCaseCatalogSyncService(
        BadCaseCatalogSyncRepository(database),
        source,
        page_size=2,
        max_pages=1,
        time_budget_seconds=30,
    )

    result = await service.run(owner="job-1")

    assert result.pages == 1
    assert result.exhausted is False
    assert result.last_bad_case_id == 2
    assert result.pending == 3
    state = await BadCaseCatalogSyncRepository(database).get_state()
    assert state is not None
    assert state.status == "idle"
    assert state.pending_count == 3


@pytest.mark.asyncio
async def test_missing_source_marks_failed(database: Database) -> None:
    """An unconfigured source fails with the stable unavailable code."""
    service = _service(database, None)

    with pytest.raises(AppError) as failure:
        await service.run(owner="job-1")

    assert failure.value.code is ErrorCode.BAD_CASE_QUERY_UNAVAILABLE
    state = await BadCaseCatalogSyncRepository(database).get_state()
    assert state is not None
    assert state.status == "failed"
    assert state.last_error == "BAD_CASE_QUERY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_null_object_fields_fall_back_to_source_and_skill(
    database: Database,
) -> None:
    """A null object_name uses source and a null object_type uses skill."""
    source = FakeSource(
        [_item(1, object_name=None, object_type=None, source="upstream-src")],
    )
    service = _service(database, source)

    await service.run(owner="job-1")

    async with database.session() as session:
        row = (await session.execute(select(bad_cases))).mappings().one()
    assert row["object_name"] == "upstream-src"
    assert row["object_type"] == "skill"


@pytest.mark.asyncio
@pytest.mark.parametrize("source_value", ["code_reivew", "code_review"])
async def test_code_review_source_maps_object_name_to_code_review(
    database: Database,
    source_value: str,
) -> None:
    """A code-review source gets the canonical hyphenated object name."""
    source = FakeSource(
        [_item(1, object_name=None, object_type=None, source=source_value)],
    )
    service = _service(database, source)

    await service.run(owner="job-1")

    async with database.session() as session:
        row = (await session.execute(select(bad_cases))).mappings().one()
    assert row["object_name"] == "code-review"
    assert row["object_type"] == "skill"


@pytest.mark.asyncio
async def test_code_review_source_keeps_explicit_object_name(
    database: Database,
) -> None:
    """The special source mapping never overwrites an upstream object_name."""
    source = FakeSource(
        [_item(1, object_name="custom-object", source="code_reivew")],
    )
    service = _service(database, source)

    await service.run(owner="job-1")

    async with database.session() as session:
        row = (await session.execute(select(bad_cases))).mappings().one()
    assert row["object_name"] == "custom-object"


@pytest.mark.asyncio
async def test_missing_object_name_and_source_fall_back_to_unknown(
    database: Database,
) -> None:
    """Empty object fields degrade to unknown and skill instead of failing."""
    source = FakeSource(
        [_item(1, object_name="", object_type="", source=None)],
    )
    service = _service(database, source)

    await service.run(owner="job-1")

    async with database.session() as session:
        row = (await session.execute(select(bad_cases))).mappings().one()
    assert row["object_name"] == "unknown"
    assert row["object_type"] == "skill"


@pytest.mark.asyncio
async def test_analysis_rows_survive_upsert(database: Database) -> None:
    """Updating a case never touches its attribution row."""
    now = now_shanghai()
    await _insert_case(database, 1, title="old", now=now)
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

    await _service(database, FakeSource([_item(1, title="new")])).run(
        owner="job-1",
    )

    progress = await BadCaseRepository(database).analysis_progress()
    assert progress.total == 1
    assert progress.analyzed == 1
