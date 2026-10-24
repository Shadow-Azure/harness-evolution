"""SQLite adapter used for tests and local development."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.db.database import SqlAlchemyDatabase


class SqliteDatabase(SqlAlchemyDatabase):
    """SQLAlchemy database adapter configured for aiosqlite."""

    def __init__(self, settings: Settings) -> None:
        """Create a SQLite adapter and ensure its data directory exists."""
        if not settings.db_url:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(dialect="sqlite", url=settings.effective_db_url, echo=settings.db_echo)

    def _build_engine(self) -> AsyncEngine:
        """Create an aiosqlite engine with deterministic connection pragmas."""
        engine = create_async_engine(
            self._url,
            echo=self._echo,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(dbapi_connection: Any, _record: object) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
            finally:
                cursor.close()

        return engine
