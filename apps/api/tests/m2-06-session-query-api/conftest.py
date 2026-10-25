"""Fixtures for the session query API contracts."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.fixtures import run_corpus_seed
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app

ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class SessionQueryEnvironment:
    """Authenticated client plus its live, seeded database."""

    client: httpx.AsyncClient
    database: Database
    authorization: dict[str, str]


@pytest_asyncio.fixture
async def session_query(
    tmp_path: Path,
) -> AsyncIterator[SessionQueryEnvironment]:
    """Seed the synthetic corpus and authenticate a completed admin login."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("session-query-test-signing-secret-with-length"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
    )
    corpus = load_fixture_corpus(ROOT / "fixtures" / "m2-synthetic" / "corpus.json")
    await run_corpus_seed(settings, corpus)

    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "initial-password"},
        )
        assert login.status_code == 200
        initial_token = login.json()["accessToken"]
        changed = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {initial_token}"},
            json={
                "oldPassword": "initial-password",
                "newPassword": "replacement-password",
            },
        )
        assert changed.status_code == 204
        authenticated = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "replacement-password"},
        )
        assert authenticated.status_code == 200
        yield SessionQueryEnvironment(
            client=client,
            database=app.state.database,
            authorization={
                "Authorization": f"Bearer {authenticated.json()['accessToken']}",
            },
        )
