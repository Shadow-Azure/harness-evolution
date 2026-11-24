"""Writer ownership: catalog sync updates only its own rows."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
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
    BadCaseCatalogSyncRepository,
    CatalogCaseRow,
    PageCounts,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases
from app.utils.time import now_shanghai


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("writer-ownership-test-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


def _case(case_id: int, *, title: str) -> CatalogCaseRow:
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


async def _insert_report(database: Database, *, case_id: int, title: str) -> None:
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=str(case_id),
                workspace_id="ws-other",
                origin="report",
                bad_case_session_id=f"session-{case_id}",
                bad_case_type="self",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title=title,
                bad_case_description="reported description",
                meta_data=None,
                source="report",
                session_source={
                    "runtime": "claude-code",
                    "sessionUrlTemplate": "https://trace.test/{sessionId}",
                },
                created_at=now,
                updated_at=now,
            ),
        )


async def _rows(database: Database) -> dict[str, dict[str, Any]]:
    async with database.session() as session:
        rows = (await session.execute(select(bad_cases))).mappings().all()
    return {str(row["bad_case_id"]): dict(row) for row in rows}


@pytest.mark.asyncio
async def test_reported_rows_are_skipped_and_catalog_rows_updated(
    database: Database,
) -> None:
    """A page inserts new ids, refreshes owned ids, and protects reported ids."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)
    first = await repository.commit_page(
        [_case(2, title="catalog v1")],
        last_bad_case_id=2,
        pending_count=0,
        now=now,
    )
    assert first == PageCounts(inserted=1, updated=0, skipped=0)

    await _insert_report(database, case_id=3, title="reporter title")

    second = await repository.commit_page(
        [
            _case(1, title="new case"),
            _case(2, title="catalog v2"),
            _case(3, title="upstream overwrite"),
        ],
        last_bad_case_id=3,
        pending_count=0,
        now=now,
    )

    assert second == PageCounts(inserted=1, updated=1, skipped=1)
    rows = await _rows(database)
    assert rows["1"]["origin"] == "catalog"
    assert rows["2"]["origin"] == "catalog"
    assert rows["2"]["title"] == "catalog v2"
    assert rows["3"]["origin"] == "report"
    assert rows["3"]["title"] == "reporter title"
    assert rows["3"]["bad_case_description"] == "reported description"
    state = await repository.get_state()
    assert state is not None
    assert state.last_bad_case_id == 3


class _RacingRepository(BadCaseCatalogSyncRepository):
    """Hide a winner on the first ownership read to force an insert race."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.ownership_reads = 0

    async def _ownership(
        self,
        session: AsyncSession,
        values: Sequence[dict[str, Any]],
    ) -> dict[str, str]:
        self.ownership_reads += 1
        ownership = await super()._ownership(session, values)
        if self.ownership_reads == 1:
            return {key: value for key, value in ownership.items() if key != "3"}
        return ownership


@pytest.mark.asyncio
async def test_insert_race_reclassifies_the_winner_as_skipped(
    database: Database,
) -> None:
    """A concurrent reported insert is retried through a savepoint and skipped."""
    repository = _RacingRepository(database)
    now = now_shanghai()
    await repository.initialize(now)
    await _insert_report(database, case_id=3, title="reporter title")

    counts = await repository.commit_page(
        [_case(1, title="one"), _case(3, title="upstream overwrite")],
        last_bad_case_id=3,
        pending_count=0,
        now=now,
    )

    assert counts == PageCounts(inserted=1, updated=0, skipped=1)
    assert repository.ownership_reads == 2
    rows = await _rows(database)
    assert rows["1"]["origin"] == "catalog"
    assert rows["3"]["title"] == "reporter title"
