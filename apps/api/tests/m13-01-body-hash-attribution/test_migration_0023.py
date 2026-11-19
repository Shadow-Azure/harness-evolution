"""Revision 0023: target_revision and case_anchor_kind migrations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from alembic.config import Config
from sqlalchemy import String, inspect

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'm13-migration.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def _columns(database: Database, table: str) -> set[str]:
    """Return the reflected column names of one table."""
    async with database.engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: {
                str(column["name"]) for column in inspect(sync_connection).get_columns(table)
            },
        )


async def _target_version_length(database: Database) -> int:
    """Return the reflected ``evolution_runs.target_version`` width."""
    async with database.engine.connect() as connection:
        column = await connection.run_sync(
            lambda sync_connection: {
                str(item["name"]): item
                for item in inspect(sync_connection).get_columns("evolution_runs")
            }["target_version"],
        )
    length = cast(String, column["type"]).length
    assert length is not None
    return int(length)


async def test_migration_adds_and_removes_both_columns(tmp_path: Path) -> None:
    """0023 is additive, nullable, and reversible on an isolated database."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await upgrade_database(database)

        assert "target_revision" in await _columns(database, "evolution_runs")
        assert "case_anchor_kind" in await _columns(database, "evolution_run_candidates")
        assert await _target_version_length(database) == 96

        await asyncio.to_thread(command.downgrade, alembic_config(database), "0022")

        assert "target_revision" not in await _columns(database, "evolution_runs")
        assert "case_anchor_kind" not in await _columns(database, "evolution_run_candidates")
        assert await _target_version_length(database) == 96

        await upgrade_database(database)

        assert "target_revision" in await _columns(database, "evolution_runs")
        assert "case_anchor_kind" in await _columns(database, "evolution_run_candidates")
    finally:
        await database.dispose()
