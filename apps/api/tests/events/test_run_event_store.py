"""SQL-backed evolution event replay and recovery recording contracts."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.run_events import EVOLUTION_RUN_EVENT_METADATA, evolution_run_events


@pytest_asyncio.fixture
async def event_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated database with the shared event projection."""
    database = create_database(
        Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path),
    )
    await database.start()
    await upgrade_database(database)
    async with database.engine.begin() as connection:
        await connection.run_sync(EVOLUTION_RUN_EVENT_METADATA.create_all)
    try:
        yield database
    finally:
        await database.dispose()


async def test_sql_replay_pages_and_records_interrupted_events(
    event_database: Database,
) -> None:
    """The adapter pages persisted history and allocates the next run sequence."""
    store = SqlRunEventStore(event_database)
    async with event_database.transaction() as session:
        await session.execute(
            insert(evolution_run_events),
            [
                {
                    "run_id": "r1",
                    "seq": 1,
                    "event_type": "prepare_started",
                    "level": "info",
                    "stage": "prepare",
                    "step_index": None,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-1",
                    "message": "first",
                    "payload": {"step": 1},
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": datetime(2026, 10, 25, 10, 0, tzinfo=UTC),
                },
                {
                    "run_id": "r1",
                    "seq": 2,
                    "event_type": "workspace_prepared",
                    "level": "info",
                    "stage": "prepare",
                    "step_index": None,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-1",
                    "message": "second",
                    "payload": None,
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": datetime(2026, 10, 25, 10, 0, 1, tzinfo=UTC),
                },
            ],
        )

    first = await store.read(("run:r1",), {"run:r1": 0}, 1)
    second = await store.read(("run:r1",), first.next_cursors, 1)
    interrupted_seq = await store.record_interrupted(
        run_id="r1",
        stage="prepare",
        message="job interrupted by process restart",
        job_id="job-1",
    )
    async with event_database.session() as session:
        interrupted = (
            (
                await session.execute(
                    select(evolution_run_events).where(
                        evolution_run_events.c.run_id == "r1",
                        evolution_run_events.c.seq == interrupted_seq,
                    ),
                )
            )
            .mappings()
            .one()
        )

    assert [event.event_id for event in first.events] == [1]
    assert first.has_more is True
    assert first.next_cursors == {"run:r1": 1}
    assert [event.event_id for event in second.events] == [2]
    assert second.has_more is False
    assert interrupted_seq == 3
    assert interrupted["stage"] == "prepare"
    assert interrupted["job_id"] == "job-1"


async def test_missing_future_owned_table_is_an_explicit_empty_capability(
    tmp_path: Path,
) -> None:
    """The store degrades explicitly if a deployment has not migrated its schema."""
    database = create_database(
        Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path),
    )
    await database.start()
    store = SqlRunEventStore(database)
    try:
        page = await store.read(("run:r1",), {"run:r1": 0}, 100)
        sequence = await store.record_interrupted(
            run_id="r1",
            stage="prepare",
            message="interrupted",
            job_id="job-1",
        )
    finally:
        await database.dispose()

    assert page.events == ()
    assert sequence is None
