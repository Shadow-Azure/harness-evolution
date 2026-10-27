"""Durable evolution event pagination, filtering, and relationship contracts."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
from sqlalchemy import delete, func, insert, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_runs
from app.db.models.run_events import evolution_run_events

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)


def _run_values(run_id: str) -> dict[str, object]:
    """Build the complete persisted run snapshot required by the event FK."""
    return {
        "id": run_id,
        "title": "event fixture",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": None,
        "base_ref": "v2.0.0",
        "base_commit": None,
        "branch_name": f"evo/{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "pending",
        "pushed_at": None,
        "push_error": None,
        "window_from": None,
        "window_to": None,
        "models": [],
        "status": "running",
        "blocked_stage": None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": None,
        "error_message": None,
        "error_at": None,
        "progress_unit": 0,
        "stats": {},
        "created_by": None,
        "created_at": NOW,
        "finished_at": None,
    }


@pytest_asyncio.fixture
async def event_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a fully migrated database with the evolution parent table."""
    database = create_database(
        Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        await session.execute(insert(evolution_runs).values(**_run_values("run-events")))
    try:
        yield database
    finally:
        await database.dispose()


async def test_store_allocates_sequences_and_pages_stably(
    event_database: Database,
) -> None:
    """Append assigns increasing sequences and pagination never duplicates a row."""
    store = SqlRunEventStore(event_database)

    first = await store.append(
        run_id="run-events",
        event_type="run_created",
        level="info",
        stage="prepare",
        message="created",
        payload={"source": "test"},
    )
    second = await store.append(
        run_id="run-events",
        event_type="prepare_started",
        level="warn",
        stage="prepare",
        message="preparing",
    )
    third = await store.append(
        run_id="run-events",
        event_type="run_failed",
        level="error",
        stage="prepare",
        message="failed",
        error_type="RuntimeError",
        error_message="boom",
        error_detail="traceback",
    )

    page = await store.read_page(
        "run-events",
        after_seq=1,
        limit=1,
        level=None,
    )
    errors = await store.read_page(
        "run-events",
        after_seq=0,
        limit=100,
        level="error",
    )

    assert [first.seq, second.seq, third.seq] == [1, 2, 3]
    assert [item.seq for item in page.items] == [2]
    assert page.has_more is True
    assert [item.event_type for item in errors.items] == ["run_failed"]
    assert await store.max_seq("run-events") == 3


async def test_run_event_parent_delete_cascades_history(
    event_database: Database,
) -> None:
    """The run relationship prevents orphan history and follows run cleanup."""
    store = SqlRunEventStore(event_database)
    await store.append(
        run_id="run-events",
        event_type="run_created",
        level="info",
        stage="prepare",
        message="created",
    )

    async with event_database.transaction() as session:
        await session.execute(
            delete(evolution_runs).where(evolution_runs.c.id == "run-events"),
        )
    async with event_database.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(evolution_run_events))
        ).scalar_one()

    assert count == 0


async def test_history_survives_database_reopen(tmp_path: Path) -> None:
    """A process restart reads the same ordered durable sequence from disk."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    first_database = create_database(settings)
    await first_database.start()
    await upgrade_database(first_database)
    async with first_database.transaction() as session:
        await session.execute(
            insert(evolution_runs).values(**_run_values("run-restart")),
        )
    first_store = SqlRunEventStore(first_database)
    await first_store.append(
        run_id="run-restart",
        event_type="run_created",
        level="info",
        stage="prepare",
        message="created",
    )
    await first_store.append(
        run_id="run-restart",
        event_type="prepare_started",
        level="info",
        stage="prepare",
        message="preparing",
    )
    await first_database.dispose()

    reopened = create_database(settings)
    await reopened.start()
    try:
        page = await SqlRunEventStore(reopened).read_page(
            "run-restart",
            after_seq=0,
            limit=100,
            level=None,
        )
    finally:
        await reopened.dispose()

    assert [item.seq for item in page.items] == [1, 2]
    assert [item.event_type for item in page.items] == [
        "run_created",
        "prepare_started",
    ]
