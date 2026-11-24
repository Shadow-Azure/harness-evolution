"""Alembic upgrades expose the catalog cursor and the bad-case writer origin."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import String, inspect, text

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database

EXPECTED_COLUMNS = {
    "id",
    "last_bad_case_id",
    "synced_count",
    "pending_count",
    "status",
    "attempts",
    "last_error",
    "last_run_at",
    "last_success_at",
    "updated_at",
}

LEGACY_CASES = (
    ("BC-LEGACY-OTHER", "ws-other", None, "report"),
    ("BC-LEGACY-SOURCE", "ws-default", {"kind": "report"}, "report"),
    ("BC-LEGACY-CATALOG", "ws-default", None, "catalog"),
)


def _settings(tmp_path: Path) -> Settings:
    """Return an isolated SQLite target for migration tests."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("catalog-sync-migration-secret"),
    )


def _alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path upgrades."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def _normalized_default(column: Mapping[str, Any]) -> str | None:
    """Normalize dialect-specific quoting around a reflected server default."""
    default = column["default"]
    if default is None:
        return None
    return str(default).strip().strip("'\"").lower()


async def _bad_case_columns(database: Database) -> dict[str, Any]:
    """Return the reflected bad-case columns keyed by name."""
    async with database.engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_columns("bad_cases"),
        )
    return {str(column["name"]): column for column in columns}


@pytest.mark.asyncio
async def test_upgrade_creates_catalog_sync_table(tmp_path: Path) -> None:
    """Head migration exposes the cursor table and the non-null writer origin."""
    database = create_database(_settings(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)

        async with database.engine.connect() as connection:
            exists, columns, primary_key = await connection.run_sync(
                lambda sync_connection: (
                    inspect(sync_connection).has_table("bad_case_catalog_sync"),
                    {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "bad_case_catalog_sync",
                        )
                    },
                    inspect(sync_connection).get_pk_constraint("bad_case_catalog_sync")[
                        "constrained_columns"
                    ],
                ),
            )
        async with database.session() as session:
            revision: str = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
        origin = (await _bad_case_columns(database))["origin"]

        assert exists is True
        assert columns == EXPECTED_COLUMNS
        assert primary_key == ["id"]
        assert revision == "0032"
        assert origin["nullable"] is False
        assert cast(String, origin["type"]).length == 16
        assert _normalized_default(origin) == "catalog"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_origin_upgrade_backfills_the_first_writer(tmp_path: Path) -> None:
    """0032 defaults catalog rows and marks the rows submitted through credentials."""
    database = create_database(_settings(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, _alembic_config(database), "0031")
        now = datetime(2026, 11, 24, 9, tzinfo=UTC)
        async with database.transaction() as session:
            for case_id, workspace_id, session_source, _origin in LEGACY_CASES:
                await session.execute(
                    text(
                        "INSERT INTO bad_cases ("
                        "bad_case_id, bad_case_session_id, bad_case_type, object_name, "
                        "object_type, title, bad_case_description, workspace_id, "
                        "session_source, created_at, updated_at"
                        ") VALUES ("
                        ":case_id, :session_id, 'self', 'deep-research', 'skill', "
                        ":case_id, 'legacy reason', :workspace_id, :session_source, "
                        ":now, :now)"
                    ),
                    {
                        "case_id": case_id,
                        "session_id": f"session-{case_id}",
                        "workspace_id": workspace_id,
                        "session_source": (
                            json.dumps(session_source) if session_source is not None else None
                        ),
                        "now": now,
                    },
                )

        await upgrade_database(database)

        async with database.session() as session:
            rows = (
                (
                    await session.execute(
                        text("SELECT bad_case_id, origin FROM bad_cases"),
                    )
                )
                .mappings()
                .all()
            )

        assert {str(row["bad_case_id"]): str(row["origin"]) for row in rows} == {
            case_id: expected for case_id, _workspace, _source, expected in LEGACY_CASES
        }
    finally:
        await database.dispose()
