"""Durable cursor state and owner-scoped page writes for the bad-case catalog sync."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, func, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.crud.integrity import is_unique_violation
from app.db.models.domain import (
    BAD_CASE_ORIGIN_CATALOG,
    bad_case_catalog_sync,
    bad_cases,
)
from app.db.models.workspace import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)

STATE_ID = "bad_cases"

_UPDATE_COLUMNS = (
    "bad_case_session_id",
    "bad_case_type",
    "object_name",
    "object_type",
    "object_version",
    "bad_case_agent_id",
    "trigger_line",
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
    trigger_line: int | None = None


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
class PageCounts:
    """Inserted, updated, and owner-protected counts for one committed page."""

    inserted: int
    updated: int
    skipped: int


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
        "trigger_line": row.trigger_line,
        "title": row.title,
        "bad_case_description": row.description,
        "meta_data": row.meta_data,
        "source": row.source,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _insert_values(row: CatalogCaseRow) -> dict[str, Any]:
    """Return the full insert payload for a row the catalog is about to own."""
    return {
        **_values(row),
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "origin": BAD_CASE_ORIGIN_CATALOG,
    }


def _update_parameters(row: CatalogCaseRow) -> dict[str, Any]:
    """Return the executemany parameters of one owner-guarded row update."""
    values = _values(row)
    return {
        "row_id": str(row.bad_case_id),
        **{column: values[column] for column in _UPDATE_COLUMNS},
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
    ) -> PageCounts:
        """Apply one page under writer ownership and advance the cursor together.

        Rows absent locally are inserted as catalog-owned, rows the catalog
        already owns are updated, and rows a report wrote first stay untouched
        and are counted as skipped. A concurrent insert can win the primary-key
        race after the ownership read; the failed statement also rolls back its
        savepoint, the ids are re-read as a current read, and each loser is
        routed to update or skip so the page transaction still commits.
        """
        rows = list(items)
        by_id = {str(row.bad_case_id): row for row in rows}
        async with self._database.transaction() as session:
            origins = await self._origins(session, tuple(by_id))
            to_insert = [row for case_id, row in by_id.items() if case_id not in origins]
            to_update = [
                row
                for case_id, row in by_id.items()
                if origins.get(case_id) == BAD_CASE_ORIGIN_CATALOG
            ]
            skipped = len(by_id) - len(to_insert) - len(to_update)
            inserted = 0
            if to_insert:
                raced = await self._insert_catalog_rows(
                    session,
                    [_insert_values(row) for row in to_insert],
                )
                inserted = len(to_insert) - len(raced)
                late_origins = await self._origins(session, raced, current=True)
                for case_id in raced:
                    if late_origins.get(case_id) == BAD_CASE_ORIGIN_CATALOG:
                        to_update.append(by_id[case_id])
                    else:
                        skipped += 1
            if to_update:
                await session.execute(
                    self._owned_update_statement(),
                    [_update_parameters(row) for row in to_update],
                )
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
        return PageCounts(
            inserted=inserted,
            updated=len(to_update),
            skipped=skipped,
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

    async def _origins(
        self,
        session: AsyncSession,
        bad_case_ids: Sequence[str],
        *,
        current: bool = False,
    ) -> dict[str, str]:
        """Return the writer origin of the ids that already exist.

        MySQL REPEATABLE READ answers a plain re-read from the snapshot opened
        before a competitor committed, so the post-race read is a locking read:
        it waits for the winner and returns the committed origin.
        """
        if not bad_case_ids:
            return {}
        statement = select(bad_cases.c.bad_case_id, bad_cases.c.origin).where(
            bad_cases.c.bad_case_id.in_(tuple(bad_case_ids)),
        )
        if current:
            statement = statement.with_for_update()
        rows = (await session.execute(statement)).mappings()
        return {str(row["bad_case_id"]): str(row["origin"]) for row in rows}

    async def _insert_catalog_rows(
        self,
        session: AsyncSession,
        values: Sequence[dict[str, Any]],
    ) -> tuple[str, ...]:
        """Insert catalog-owned rows and return the ids that lost a primary-key race.

        The batch insert runs inside a savepoint so a duplicate id leaves the
        page transaction usable. The savepoint also rolls back the whole batch,
        so losing rows are retried one by one in their own savepoints; only the
        ids that still violate the primary key are reported back to the caller.
        """
        if not values:
            return ()
        try:
            async with session.begin_nested():
                await session.execute(insert(bad_cases), values)
        except IntegrityError as exc:
            if not is_unique_violation(exc):
                raise
            logger.warning(
                "catalog page insert lost a primary-key race; retrying rows one by one",
                extra={"bad_case_ids": [str(value["bad_case_id"]) for value in values]},
            )
        else:
            return ()
        raced: list[str] = []
        for value in values:
            try:
                async with session.begin_nested():
                    await session.execute(insert(bad_cases).values(**value))
            except IntegrityError as row_error:
                if not is_unique_violation(row_error):
                    raise
                raced.append(str(value["bad_case_id"]))
        return tuple(raced)

    def _owned_update_statement(self) -> Any:
        """Build the per-row update that only touches catalog-owned rows."""
        return (
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == bindparam("row_id"))
            .where(bad_cases.c.origin == BAD_CASE_ORIGIN_CATALOG)
            .values({column: bindparam(column) for column in _UPDATE_COLUMNS})
        )
