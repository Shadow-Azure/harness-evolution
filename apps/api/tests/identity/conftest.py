"""Shared application fixtures for identity behavior tests."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.db.factory import create_database
from app.main import create_app
from tests.identity.helpers import identity_settings


@pytest.fixture
async def identity_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Provide a migrated identity API without a seeded administrator."""
    settings = identity_settings(tmp_path)
    app = create_app(settings, database=create_database(settings))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client
