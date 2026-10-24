"""Shared SQLAlchemy database implementation."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.db.base import DBHealth

logger = logging.getLogger(__name__)


class SqlAlchemyDatabase:
    """Own one async SQLAlchemy engine and its session factories."""

    dialect: str

    def __init__(self, *, dialect: str, url: str, echo: bool) -> None:
        """Create an unstarted database adapter."""
        self.dialect = dialect
        self._url = url
        self._echo = echo
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Return the started engine."""
        if self._engine is None:
            raise RuntimeError("database has not been started")
        return self._engine

    @property
    def url(self) -> str:
        """Return the configured target without creating an engine."""
        return self._url

    def _build_engine(self) -> AsyncEngine:
        """Create the dialect-specific engine."""
        raise NotImplementedError

    async def start(self) -> None:
        """Create the engine; connectivity failure remains a health concern."""
        if self._engine is not None:
            return
        self._engine = self._build_engine()
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def dispose(self) -> None:
        """Dispose the engine and forget its factories."""
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        """Return a started session factory."""
        if self._session_factory is None:
            raise RuntimeError("database has not been started")
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a closing session without an implicit commit."""
        async with self._factory()() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Commit successful writes and roll back every exception."""
        async with self._factory()() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def health(self) -> DBHealth:
        """Run a minimal query and report latency without leaking credentials."""
        started = perf_counter()
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:
            logger.error(
                "database health check failed",
                extra={
                    "dialect": self.dialect,
                    "error_type": type(exc).__name__,
                },
            )
            return DBHealth(
                ok=False,
                dialect=self.dialect,
                latency_ms=round((perf_counter() - started) * 1000, 3),
                error=f"{type(exc).__name__}: database is unavailable",
            )
        return DBHealth(
            ok=True,
            dialect=self.dialect,
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )
