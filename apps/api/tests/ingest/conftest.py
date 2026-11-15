"""Shared fixtures for the workspace bad-case ingest tests."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.db.crud.fixtures import ensure_fixture_external_tables
from app.main import create_app
from tests.identity.helpers import identity_settings


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
