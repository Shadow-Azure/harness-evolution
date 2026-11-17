"""Shared helpers for the m12-02 external-contract slice."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.db.base import Database

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_CORPUS = ROOT / "fixtures" / "m2-synthetic" / "corpus.json"

SESSION_1 = "10000000-0000-4000-8000-000000000001"
CASE_1 = "badcase-synthetic-0001"
PROBE_1 = "probe-synthetic-0001"

_READ_PREFIXES = ("select", "pragma", "with", "show", "explain", "describe")


def permission_error() -> OperationalError:
    """Build one MySQL read-privilege failure."""
    original = Exception(
        1142,
        "SELECT command denied to user 'reader'@'localhost' for table 'bad_cases'",
    )
    return OperationalError("SELECT * FROM bad_cases", {}, original)


def missing_column_error() -> OperationalError:
    """Build one MySQL missing-column failure."""
    original = Exception(1054, "Unknown column 'bad_case_description' in 'field list'")
    return OperationalError("SELECT * FROM bad_cases", {}, original)


def generic_database_error() -> OperationalError:
    """Build one database failure that is neither permission nor schema drift."""
    original = Exception(2013, "Lost connection to MySQL server during query")
    return OperationalError("SELECT * FROM bad_cases", {}, original)


@contextlib.contextmanager
def record_statements(database: Database) -> Iterator[list[str]]:
    """Record every SQL statement the app sends through one engine."""
    statements: list[str] = []

    def before(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(sync_engine, "before_cursor_execute", before)


def assert_read_only(statements: list[str]) -> None:
    """Assert every recorded statement is a read, never a write or DDL."""
    assert statements, "the read path emitted no SQL"
    for statement in statements:
        normalized = " ".join(statement.strip().lower().split())
        assert normalized.startswith(_READ_PREFIXES), statement


class FailingDatabase:
    """Minimal Database double whose connection or session always fails."""

    dialect = "mysql"

    def __init__(self, error: BaseException) -> None:
        """Bind the failure every access should raise."""
        self._error = error

    @property
    def engine(self) -> Any:
        """Expose an engine whose connect call raises the configured failure."""
        raise self._error

    def session(self) -> Any:
        """Expose a session context manager that fails on entry."""
        return _FailingSession(self._error)

    def transaction(self) -> Any:
        """The read path never uses write transactions."""
        return _FailingSession(self._error)


class _FailingSession:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    async def __aenter__(self) -> Any:
        raise self._error

    async def __aexit__(self, *args: object) -> bool:
        return False


def as_database(value: object) -> Database:
    """Cast a test double to the structural Database protocol."""
    return cast(Database, value)
