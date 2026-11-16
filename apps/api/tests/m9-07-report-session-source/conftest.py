"""Shared migrated SQLite database for m9-07 root-sync tests."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.main import create_app
from tests.identity.helpers import identity_settings


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide one migrated SQLite database isolated per test."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("m9-07-source-test-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
async def ingest_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    """Provide a migrated API plus an unauthenticated HTTP client."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        await ensure_fixture_external_tables(app.state.database)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield app, client
