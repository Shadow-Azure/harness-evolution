"""Shared job service fixtures."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.jobs import JobRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.service.events import EventBus
from app.service.jobs import JobRunner


@pytest_asyncio.fixture
async def job_environment(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, JobRepository, EventBus, JobRunner]]:
    """Provide a migrated database and an unstarted serial job runner."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    repository = JobRepository(database)
    bus = EventBus(queue_capacity=100)
    runner = JobRunner(repository, bus)
    try:
        yield database, repository, bus, runner
    finally:
        await runner.close()
        await bus.close()
        await database.dispose()
