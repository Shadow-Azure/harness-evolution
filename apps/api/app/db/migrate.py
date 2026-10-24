"""Programmatic Alembic migration entry point."""

import asyncio
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.config import Settings
from app.db.base import Database


def _alembic_config(settings: Settings) -> Config:
    """Build Alembic configuration for the selected database URL."""
    api_root = Path(__file__).resolve().parents[2]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.effective_db_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


async def upgrade_database(_database: Database, settings: Settings) -> None:
    """Upgrade the selected database in a worker thread."""
    config = _alembic_config(settings)
    await asyncio.to_thread(command.upgrade, config, "head")
