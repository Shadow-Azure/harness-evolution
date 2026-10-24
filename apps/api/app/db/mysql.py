"""MySQL adapter used by production and MySQL integration tests."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.db.database import SqlAlchemyDatabase


class MySqlDatabase(SqlAlchemyDatabase):
    """SQLAlchemy database adapter configured for asyncmy."""

    def __init__(self, settings: Settings) -> None:
        """Create a MySQL adapter from environment-backed settings."""
        super().__init__(dialect="mysql", url=settings.effective_db_url, echo=settings.db_echo)
        self._pool_size = settings.db_pool_size
        self._max_overflow = settings.db_max_overflow

    def _build_engine(self) -> AsyncEngine:
        """Create an asyncmy engine with pool health and Shanghai time."""
        engine = create_async_engine(
            self._url,
            echo=self._echo,
            pool_size=self._pool_size,
            max_overflow=self._max_overflow,
            pool_recycle=1800,
            pool_pre_ping=True,
        )

        @event.listens_for(engine.sync_engine, "connect")
        def configure_mysql(dbapi_connection: Any, _record: object) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SET time_zone = '+08:00'")
            finally:
                cursor.close()

        return engine
