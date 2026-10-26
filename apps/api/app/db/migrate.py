"""Programmatic Alembic migration entry point."""

import asyncio
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.db.base import Database


def _alembic_config(database: Database) -> Config:
    """Build Alembic configuration for the exact application database target."""
    api_root = Path(__file__).resolve().parents[2]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


async def upgrade_database(
    database: Database,
    *,
    bootstrap_external_tables: bool = True,
) -> None:
    """Upgrade the selected database in a worker thread.

    External problem/attribution/probe tables are owned outside this service.
    Development fixtures may request their bootstrap schema explicitly; the
    application runtime upgrades only internal tables.
    """
    config = _alembic_config(database)
    config.attributes["bootstrap_external_tables"] = bootstrap_external_tables
    await asyncio.to_thread(command.upgrade, config, "head")
