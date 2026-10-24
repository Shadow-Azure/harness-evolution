"""The sole database adapter selection point."""

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.mysql import MySqlDatabase
from app.db.sqlite import SqliteDatabase


def create_database(settings: Settings) -> Database:
    """Create the adapter selected by ``HE_DB_DIALECT``."""
    if settings.db_dialect is DatabaseDialect.SQLITE:
        return SqliteDatabase(settings)
    return MySqlDatabase(settings)
