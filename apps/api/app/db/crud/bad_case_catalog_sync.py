"""Durable cursor state and page upserts for the bad-case catalog sync."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.db.base import Database
from app.db.models.domain import bad_case_catalog_sync, bad_cases

logger = logging.getLogger(__name__)

STATE_ID = "bad_cases"

_UPDATE_COLUMNS = (
    "bad_case_session_id",
    "bad_case_type",
    "object_name",
    "object_type",
    "object_version",
    "bad_case_agent_id",
    "title",
    "bad_case_description",
    "meta_data",
    "source",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True, slots=True)
class CatalogCaseRow:
    """One upstream bad case normalized to the local column names."""

    bad_case_id: int
    bad_case_session_id: str
    bad_case_type: str
    object_name: str
    object_type: str
    object_version: str | None
    bad_case_agent_id: str | None
    title: str
    description: str
    meta_data: Any | None
    source: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CatalogSyncState:
    """Durable single-row cursor and counters."""

    last_bad_case_id: int
    synced_count: int
    pending_count: int
    status: str
    attempts: int
    last_error: str | None
    last_run_at: datetime | None
    last_success_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UpsertCounts:
    """Inserted and updated row counts for one committed page."""

    inserted: int
    updated: int


def _state(row: RowMapping) -> CatalogSyncState:
    return CatalogSyncState(
        last_bad_case_id=int(row["last_bad_case_id"]),
        synced_count=int(row["synced_count"]),
        pending_count=int(row["pending_count"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        last_error=(str(row["last_error"]) if row["last_error"] is not None else None),
        last_run_at=row["last_run_at"],
        last_success_at=row["last_success_at"],
        updated_at=row["updated_at"],
    )


def _values(row: CatalogCaseRow) -> dict[str, Any]:
    return {
        "bad_case_id": str(row.bad_case_id),
        "bad_case_session_id": row.bad_case_session_id,
        "bad_case_type": row.bad_case_type,
        "object_name": row.object_name,
        "object_type": row.object_type,
        "object_version": row.object_version,
        "bad_case_agent_id": row.bad_case_agent_id,
        "title": row.title,
        "bad_case_description": row.description,
        "meta_data": row.meta_data,
        "source": row.source,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class BadCaseCatalogSyncRepository:
    """Own the catalog cursor row and transactional page writes."""

    def __init__(self, database: Database) -> None:
        """Bind the storage boundary used by the sync service."""
        self._database = database

    async def get_state(self) -> CatalogSyncState | None:
        """Return the single cursor row, or None before the first initialization."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(bad_case_catalog_sync).where(
                            bad_case_catalog_sync.c.id == STATE_ID,
                        ),
                    )
                )
                .mappings()
                .first()
            )
        return _state(row) if row is not None else None

    async def initialize(self, now: datetime) -> CatalogSyncState:
        """Create the cursor row at zero when absent and return the stored state."""
        async with self._database.transaction() as session:
            row = (
                (
                    await session.execute(
                        select(bad_case_catalog_sync).where(
                            bad_case_catalog_sync.c.id == STATE_ID,
                        ),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                await session.execute(
                    insert(bad_case_catalog_sync).values(
                        id=STATE_ID,
                        last_bad_case_id=0,
                        synced_count=0,
                        pending_count=0,
                        status="idle",
                        attempts=0,
                        last_error=None,
                        last_run_at=None,
                        last_success_at=None,
                        updated_at=now,
                    ),
                )
                row = (
                    (
                        await session.execute(
                            select(bad_case_catalog_sync).where(
                                bad_case_catalog_sync.c.id == STATE_ID,
                            ),
                        )
                    )
                    .mappings()
                    .one()
                )
        return _state(row)

    async def mark_running(self, now: datetime) -> None:
        """Mark the run active and clear the previous failure."""
        async with self._database.transaction() as session:
            await session.execute(
                update(bad_case_catalog_sync)
                .where(bad_case_catalog_sync.c.id == STATE_ID)
                .values(
                    status="running",
                    last_run_at=now,
                    last_error=None,
                    updated_at=now,
                ),
            )

    async def mark_failed(self, error: str, now: datetime) -> None:
        """Record one stable failure code and increment the attempt counter."""
        async with self._database.transaction() as session:
            await session.execute(
                update(bad_case_catalog_sync)
                .where(bad_case_catalog_sync.c.id == STATE_ID)
                .values(
                    status="failed",
                    attempts=bad_case_catalog_sync.c.attempts + 1,
                    last_error=error,
                    updated_at=now,
                ),
            )

    async def mark_idle(self, now: datetime, *, pending: int | None = None) -> None:
        """Finish a run without failure, optionally pinning the remaining count."""
        values: dict[str, Any] = {
            "status": "idle",
            "attempts": 0,
            "last_error": None,
            "last_success_at": now,
            "updated_at": now,
        }
        if pending is not None:
            values["pending_count"] = pending
        async with self._database.transaction() as session:
            await session.execute(
                update(bad_case_catalog_sync)
                .where(bad_case_catalog_sync.c.id == STATE_ID)
                .values(**values),
            )

    async def commit_page(
        self,
        items: Sequence[CatalogCaseRow],
        *,
        last_bad_case_id: int,
        pending_count: int,
        now: datetime,
    ) -> UpsertCounts:
        """Upsert one page and advance the cursor in the same transaction."""
        values = [_values(item) for item in items]
        ids = [value["bad_case_id"] for value in values]
        async with self._database.transaction() as session:
            existing: set[str] = set()
            if ids:
                existing = set(
                    (
                        await session.execute(
                            select(bad_cases.c.bad_case_id).where(
                                bad_cases.c.bad_case_id.in_(ids),
                            ),
                        )
                    ).scalars(),
                )
            if values:
                await session.execute(self._upsert_statement(values))
            synced = int(
                (
                    await session.execute(
                        select(func.count()).select_from(bad_cases),
                    )
                ).scalar_one(),
            )
            await session.execute(
                update(bad_case_catalog_sync)
                .where(bad_case_catalog_sync.c.id == STATE_ID)
                .values(
                    last_bad_case_id=last_bad_case_id,
                    synced_count=synced,
                    pending_count=pending_count,
                    status="running",
                    updated_at=now,
                ),
            )
        return UpsertCounts(
            inserted=len(values) - len(existing),
            updated=len(existing),
        )

    async def count_bad_cases(self) -> int:
        """Return the current local bad-case row count, or zero when unprovisioned."""
        try:
            async with self._database.session() as session:
                return int(
                    (
                        await session.execute(
                            select(func.count()).select_from(bad_cases),
                        )
                    ).scalar_one(),
                )
        except (OperationalError, ProgrammingError) as exc:
            if "bad_cases" in str(exc).lower():
                logger.warning(
                    "bad_cases is not provisioned; reporting zero catalog rows",
                )
                return 0
            raise

    def _upsert_statement(self, values: list[dict[str, Any]]) -> Any:
        if self._database.dialect == "mysql":
            mysql_statement = mysql_insert(bad_cases).values(values)
            return mysql_statement.on_duplicate_key_update(
                {column: mysql_statement.inserted[column] for column in _UPDATE_COLUMNS},
            )
        sqlite_statement = sqlite_insert(bad_cases).values(values)
        return sqlite_statement.on_conflict_do_update(
            index_elements=[bad_cases.c.bad_case_id],
            set_={column: sqlite_statement.excluded[column] for column in _UPDATE_COLUMNS},
        )
