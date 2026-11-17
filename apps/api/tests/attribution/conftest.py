"""Fixtures for the m10-03 attribution engine, cache, and runner tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from app.config import DatabaseDialect, Settings
from app.db.crud.attributions import AttributionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from tests.attribution.support import (
    CASE_ID,
    ORPHAN_CASE_ID,
    OTHER_CASE_ID,
    OTHER_RUN_ID,
    RUN_ID,
    Harness,
    seed_candidate,
    seed_case,
    seed_knowledge_event,
    seed_run,
    seed_session,
)


@pytest_asyncio.fixture
async def attribution_harness(tmp_path: Path) -> AsyncIterator[Harness]:
    """Provide a migrated database with two runs, three cases, and knowledge evidence."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'm10-03-attribution.db'}",
        ),
    )
    await database.start()
    await upgrade_database(database)
    main_agent_id = await seed_session(database)
    await seed_knowledge_event(database, main_agent_id)
    await seed_case(database, CASE_ID, metadata={"error": "ENOENT", "file": "index.ts"})
    await seed_case(database, OTHER_CASE_ID, case_type="discovery")
    await seed_case(database, ORPHAN_CASE_ID)
    for run_id in (RUN_ID, OTHER_RUN_ID):
        await seed_run(database, run_id)
        await seed_candidate(database, run_id, CASE_ID)
        if run_id == RUN_ID:
            await seed_candidate(database, run_id, OTHER_CASE_ID)
    try:
        yield Harness(database=database)
    finally:
        await database.dispose()


@pytest_asyncio.fixture
async def attribution_repository(
    attribution_harness: Harness,
) -> AttributionRepository:
    """Bind the attribution repository to the shared harness database."""
    return AttributionRepository(attribution_harness.database)
