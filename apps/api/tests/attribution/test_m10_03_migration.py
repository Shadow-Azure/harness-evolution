"""Revision 0021 run attribution snapshots and revision-width contracts."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 9, tzinfo=SHANGHAI)
RUN_ID = "run-migration-0021"
ATTRIBUTION_COLUMNS = {"potential_policy", "cache_enabled", "attribution_engine"}


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'attribution-0021.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def reflected(connection: AsyncConnection, table: str) -> dict[str, Any]:
    """Return the reflected columns of one table."""

    def read(sync: Connection) -> dict[str, Any]:
        inspector = inspect(sync)
        return {column["name"]: column for column in inspector.get_columns(table)}

    return await connection.run_sync(read)


async def test_0021_adds_run_snapshot_columns_and_widens_object_version(
    tmp_path: Path,
) -> None:
    """A pre-0021 run keeps working and digest-length revisions fit probe_reports."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0020")
        async with database.transaction() as session:
            await session.execute(
                text(
                    "INSERT INTO evolution_runs ("
                    "id, workspace_id, title, mode, engine_key, eval_config, target_type, "
                    "target_name, target_version, repo_url, sub_dir, status, created_at"
                    ") VALUES ("
                    ":run_id, 'ws-default', 'legacy run', 'full', 'full', '{}', 'skill', "
                    "'deep-research', 'v2.0.0', 'https://example.invalid/skills.git', "
                    "'skills/deep-research', 'running', :now"
                    ")",
                ),
                {"run_id": RUN_ID, "now": NOW},
            )

        await upgrade_database(database)

        async with database.engine.connect() as connection:
            run_columns = await reflected(connection, "evolution_runs")
            probe_columns = await reflected(connection, "probe_reports")
        assert set(run_columns) >= ATTRIBUTION_COLUMNS
        assert run_columns["attribution_engine"]["nullable"] is False
        assert run_columns["cache_enabled"]["nullable"] is False
        assert run_columns["potential_policy"]["nullable"] is True
        object_version_type = probe_columns["object_version"]["type"]
        assert getattr(object_version_type, "length", 0) >= 96

        async with database.session() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT potential_policy, cache_enabled, attribution_engine "
                            "FROM evolution_runs WHERE id = :run_id",
                        ),
                        {"run_id": RUN_ID},
                    )
                )
                .mappings()
                .one()
            )
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
        assert row["potential_policy"] is None
        assert bool(row["cache_enabled"]) is False
        assert row["attribution_engine"] == "legacy-probe-import"
        assert revision == "0026"
        assert {
            "report_schema_version",
            "report_payload",
            "execution_manifest",
            "execution_manifest_hash",
        } <= set(probe_columns)

        await upgrade_database(database)
        async with database.session() as session:
            still_there = int(
                (
                    await session.execute(
                        text("SELECT COUNT(*) FROM evolution_runs WHERE id = :run_id"),
                        {"run_id": RUN_ID},
                    )
                ).scalar_one(),
            )
        assert still_there == 1
    finally:
        await database.dispose()
