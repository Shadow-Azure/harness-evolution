"""Legacy probe and analysis reads remain deterministic with multiple attributions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest_asyncio
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_cases import BadCaseRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 9, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 10, tzinfo=SHANGHAI)
SESSION_ID = "96000000-0000-4000-8000-000000000001"
CASE_ID = "bc-legacy-read"
OLDER_PROBE_ID = "probe-read-older"
NEWER_PROBE_ID = "probe-read-newer"
V2_PROBE_ID = "probe-read-v2"


@pytest_asyncio.fixture
async def legacy_repository(tmp_path: Path) -> AsyncIterator[tuple[Database, BadCaseRepository]]:
    """Provide a migrated SQLite database with multiple attribution rows."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'legacy-reads.db'}",
        ),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=CASE_ID,
                bad_case_session_id=SESSION_ID,
                bad_case_type="self",
                object_name="deep-research",
                object_type="skill",
                object_version="v2.0.0",
                bad_case_agent_id=None,
                title=CASE_ID,
                bad_case_description="reason",
                meta_data=None,
                source="fixtures",
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        for probe_id, updated_at in (
            (OLDER_PROBE_ID, NOW),
            (NEWER_PROBE_ID, LATER),
            (V2_PROBE_ID, NOW),
        ):
            await session.execute(
                insert(probe_reports).values(
                    probe_id=probe_id,
                    workspace_id="ws-default",
                    session_id=SESSION_ID,
                    probe_type="skill",
                    probe_object="deep-research",
                    object_version="v2.0.0",
                    attribute_type=None,
                    conclusion="attributed",
                    confidence=0.8,
                    probe_description="description",
                    probe_analysis="analysis",
                    policy_version="v1",
                    attribution_engine="legacy-probe-import",
                    cache_key=f"{probe_id:0<64}"[:64],
                    created_run_id=None,
                    last_reused_run_id=None,
                    reused_count=0,
                    created_at=NOW,
                    updated_at=updated_at,
                ),
            )
        await session.execute(
            insert(bad_case_analysis),
            [
                {
                    "bad_case_id": CASE_ID,
                    "analysis_status": "analyzed_issue",
                    "probe_id": OLDER_PROBE_ID,
                    "analysis_result": {"summary": "older"},
                    "updated_at": NOW,
                },
                {
                    "bad_case_id": CASE_ID,
                    "analysis_status": "analyzed_nonissue",
                    "probe_id": NEWER_PROBE_ID,
                    "analysis_result": None,
                    "updated_at": LATER,
                },
                {
                    "bad_case_id": CASE_ID,
                    "analysis_status": None,
                    "probe_id": V2_PROBE_ID,
                    "analysis_result": None,
                    "updated_at": NOW,
                },
            ],
        )
    try:
        yield database, BadCaseRepository(database)
    finally:
        await database.dispose()


async def test_get_analysis_returns_the_latest_row_instead_of_raising(
    legacy_repository: tuple[Database, BadCaseRepository],
) -> None:
    """A case with several attributions no longer raises MultipleResultsFound."""
    _database, repository = legacy_repository

    analysis = await repository.get_analysis(CASE_ID)
    assert analysis is not None
    assert analysis.bad_case_id == CASE_ID
    assert analysis.probe_id == NEWER_PROBE_ID
    assert analysis.analysis_status == "analyzed_nonissue"
    assert analysis.updated_at.tzinfo is not None


async def test_list_snapshot_keeps_every_attribution_in_stable_order(
    legacy_repository: tuple[Database, BadCaseRepository],
) -> None:
    """Snapshots keep all rows ordered so the legacy map keeps the newest one."""
    _database, repository = legacy_repository

    snapshot = await repository.list_snapshot(SESSION_ID)
    assert [row.probe_id for row in snapshot.analyses] == [
        OLDER_PROBE_ID,
        V2_PROBE_ID,
        NEWER_PROBE_ID,
    ]
    assert {row.probe_id for row in snapshot.probes} == {
        OLDER_PROBE_ID,
        NEWER_PROBE_ID,
        V2_PROBE_ID,
    }
    assert snapshot.analyses[1].analysis_status is None
    case_snapshot = await repository.get_case_snapshot(CASE_ID)
    assert [row.probe_id for row in case_snapshot.analyses] == [
        OLDER_PROBE_ID,
        V2_PROBE_ID,
        NEWER_PROBE_ID,
    ]
    batch = await repository.analyses_by_case_ids((CASE_ID,))
    assert [row.probe_id for row in batch] == [
        OLDER_PROBE_ID,
        V2_PROBE_ID,
        NEWER_PROBE_ID,
    ]


async def test_legacy_probe_reverse_links_still_resolve(
    legacy_repository: tuple[Database, BadCaseRepository],
) -> None:
    """Reverse probe links keep working after the multi-row migration."""
    _database, repository = legacy_repository

    sources = await repository.probe_source_candidates(NEWER_PROBE_ID)
    assert [source.case_id for source in sources] == [CASE_ID]
    assert sources[0].case_session_id == SESSION_ID
    assert sources[0].probe_session_id == SESSION_ID
    snapshot = await repository.get_probe_snapshot(NEWER_PROBE_ID)
    assert snapshot.probe is not None
    assert snapshot.probe.probe_id == NEWER_PROBE_ID
    assert [source.case_id for source in snapshot.sources] == [CASE_ID]
    assert await repository.get_analysis("bc-missing") is None


async def test_missing_case_returns_an_empty_snapshot(
    legacy_repository: tuple[Database, BadCaseRepository],
) -> None:
    """Absent cases still produce empty snapshots instead of errors."""
    _database, repository = legacy_repository

    snapshot = await repository.get_case_snapshot("bc-missing")
    assert snapshot.cases == ()
    assert snapshot.analyses == ()
    assert snapshot.probes == ()
    assert await repository.probes_by_ids(()) == ()
    assert await repository.analyses_by_case_ids(()) == ()


async def test_database_serialization_keeps_analysis_ids_ordered(
    legacy_repository: tuple[Database, BadCaseRepository],
) -> None:
    """The fallback ordering stays deterministic even with equal timestamps."""
    _database, repository = legacy_repository
    await asyncio.sleep(0)
    first = await repository.get_analysis(CASE_ID)
    second = await repository.get_analysis(CASE_ID)
    assert first == second
