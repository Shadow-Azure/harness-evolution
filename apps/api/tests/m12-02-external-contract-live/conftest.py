"""Fixtures for the m12-02 external-contract suite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.fixtures import run_corpus_seed
from app.db.factory import create_database
from app.db.models.domain import (
    DOMAIN_METADATA,
    bad_case_analysis,
    bad_cases,
    probe_reports,
)
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app
from tests.m12_02_support import FIXTURE_CORPUS


@dataclass(frozen=True, slots=True)
class SeededEnvironment:
    """Authenticated client plus the seeded application database."""

    client: httpx.AsyncClient
    app: Any
    database: Database
    authorization: dict[str, str]
    workspace_id: str


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("m12-02-external-contract-test-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
        bad_case_sync_interval_seconds=0,
        bad_case_catalog_sync_interval_seconds=0,
    )


@pytest_asyncio.fixture
async def external_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide only the three externally owned tables for schema checks."""
    database = create_database(_settings(tmp_path))
    await database.start()
    async with database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: DOMAIN_METADATA.create_all(
                sync_connection,
                tables=[bad_cases, probe_reports, bad_case_analysis],
            ),
        )
    try:
        yield database
    finally:
        await database.dispose()


@pytest_asyncio.fixture
async def seeded_environment(tmp_path: Path) -> AsyncIterator[SeededEnvironment]:
    """Seed external fixtures and authenticate as a completed admin."""
    settings = _settings(tmp_path)
    corpus = load_fixture_corpus(FIXTURE_CORPUS)
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
        changed = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
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
        authorization = {
            "Authorization": f"Bearer {authenticated.json()['accessToken']}",
        }
        session = await client.get("/api/auth/session", headers=authorization)
        assert session.status_code == 200
        yield SeededEnvironment(
            client=client,
            app=app,
            database=app.state.database,
            authorization=authorization,
            workspace_id=session.json()["workspaces"][0]["id"],
        )
