"""Dialect-neutral database protocol and health model."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@dataclass(frozen=True, slots=True)
class DBHealth:
    """Sanitized result of a database connectivity check."""

    ok: bool
    dialect: str
    latency_ms: float
    error: str | None = None


class Database(Protocol):
    """Storage lifecycle and transaction boundary used by application code."""

    dialect: str

    @property
    def engine(self) -> AsyncEngine:
        """Return the started SQLAlchemy engine."""

    async def start(self) -> None:
        """Create the engine without blocking application startup."""

    async def dispose(self) -> None:
        """Release all pooled database connections."""

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Open a read session that closes without an implicit write."""

    def transaction(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Open a write transaction with commit and rollback semantics."""

    async def health(self) -> DBHealth:
        """Measure database connectivity and return a sanitized result."""
