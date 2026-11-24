"""Durable cursor state and ownership-aware page writes for the catalog sync."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.models.domain import bad_case_catalog_sync, bad_cases
from app.db.models.workspace import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)

STATE_ID = "bad_cases"
CATALOG_ORIGIN = "catalog"

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
    """Inserted, updated, and owner-protected row counts for one page."""

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
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "origin": CATALOG_ORIGIN,
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
        """Split one page by writer ownership and advance the cursor atomically.

        Catalog sync owns only rows it inserted first. A reported row with the
        same id is left untouched and counted as skipped, so a later upstream
        edit can never replace reporter-authored title or description.
        """
        values = [_values(item) for item in items]
        async with self._database.transaction() as session:
            ownership = await self._ownership(session, values)
            pending = [value for value in values if value["bad_case_id"] not in ownership]
            inserted_ids: set[str] = set()
            for attempt in range(2):
                if not pending:
                    break
                try:
                    async with session.begin_nested():
                        await session.execute(insert(bad_cases).values(pending))
                except IntegrityError:
                    if attempt == 1:
                        raise
                    ownership = await self._ownership(session, values)
                    pending = [value for value in pending if value["bad_case_id"] not in ownership]
                    continue
                inserted_ids.update(value["bad_case_id"] for value in pending)
                pending = []
            updated_ids = {
                bad_case_id for bad_case_id, origin in ownership.items() if origin == CATALOG_ORIGIN
            }
            for value in values:
                if value["bad_case_id"] not in updated_ids:
                    continue
                await session.execute(
                    update(bad_cases)
                    .where(
                        bad_cases.c.bad_case_id == value["bad_case_id"],
                        bad_cases.c.origin == CATALOG_ORIGIN,
                    )
                    .values(**{column: value[column] for column in _UPDATE_COLUMNS}),
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
            inserted=len(inserted_ids),
            updated=len(updated_ids),
            skipped=len(values) - len(inserted_ids) - len(updated_ids),
        )

    async def _ownership(
        self,
        session: AsyncSession,
        values: Sequence[dict[str, Any]],
    ) -> dict[str, str]:
        """Return the current writer origin of every existing page id."""
        if not values:
            return {}
        rows = (
            (
                await session.execute(
                    select(bad_cases.c.bad_case_id, bad_cases.c.origin).where(
                        bad_cases.c.bad_case_id.in_(
                            [value["bad_case_id"] for value in values],
                        ),
                    ),
                )
            )
            .mappings()
            .all()
        )
        return {str(row["bad_case_id"]): str(row["origin"]) for row in rows}

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
