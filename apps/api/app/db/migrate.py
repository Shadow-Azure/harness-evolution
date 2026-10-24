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


async def upgrade_database(database: Database) -> None:
    """Upgrade the selected database in a worker thread."""
    config = _alembic_config(database)
    await asyncio.to_thread(command.upgrade, config, "head")
