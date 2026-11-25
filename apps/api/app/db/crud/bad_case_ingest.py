"""Transactional bad-case ingest, quota, conflict, and root-sync marking."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.crud.bad_case_sync import insert_pending_root
from app.db.crud.integrity import is_unique_violation
from app.db.models.domain import bad_cases, workspace_bad_cases
from app.db.models.workspace import workspaces
from app.utils.time import as_shanghai, now_shanghai

logger = logging.getLogger(__name__)

_UPSTREAM_COLUMNS = (
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
    "session_source",
    "created_at",
)


@dataclass(frozen=True, slots=True)
class BadCaseIngestRow:
    """One validated report normalized to local column names."""

    bad_case_id: str
    session_id: str
    bad_case_type: str
    object_name: str
    object_type: str
    object_version: str | None
    bad_case_agent_id: str | None
    title: str
    reason: str
    meta_data: Mapping[str, Any] | None
    source: str | None
    session_source: Mapping[str, Any] | None
    created_at: datetime
    trigger_line: int | None = None


@dataclass(frozen=True, slots=True)
class BadCaseIngestWrite:
    """Committed outcome of one ingest transaction."""

    bad_case_id: str
    created: bool
    workspace_used: int


@dataclass(frozen=True, slots=True)
class StoredBadCase:
    """Minimal persisted view used by ingest tests and diagnostics."""

    bad_case_id: str
    workspace_id: str
    title: str


class WorkspaceMissing(Exception):
    """The path workspace row disappeared before the write transaction."""


class BadCaseIdConflict(Exception):
    """The reported badCaseId already belongs to a different workspace."""


class QuotaExceeded(Exception):
    """The workspace reached its bad-case quota before a new insert."""

    def __init__(self, *, quota: int, used: int) -> None:
        """Carry the quota context needed by the API error details."""
        super().__init__(f"workspace quota exceeded: {used} of {quota} used")
        self.quota = quota
        self.used = used


def _values(row: BadCaseIngestRow) -> dict[str, Any]:
    """Map one ingest row onto the `bad_cases` column names."""
    return {
        "bad_case_id": row.bad_case_id,
        "origin": "report",
        "bad_case_session_id": row.session_id,
        "bad_case_type": row.bad_case_type,
        "object_name": row.object_name,
        "object_type": row.object_type,
        "object_version": row.object_version,
        "bad_case_agent_id": row.bad_case_agent_id,
        "trigger_line": row.trigger_line,
        "title": row.title,
        "bad_case_description": row.reason,
        "meta_data": dict(row.meta_data) if row.meta_data is not None else None,
        "source": row.source,
        "session_source": (dict(row.session_source) if row.session_source is not None else None),
        "created_at": as_shanghai(row.created_at),
    }


class BadCaseIngestRepository:
    """Write reported bad cases under one workspace quota boundary."""

    def __init__(self, database: Database) -> None:
        """Bind the ingest transaction to the application database."""
        self._database = database

    async def workspace_exists(self, workspace_id: str) -> bool:
        """Return whether the path workspace still exists."""
        async with self._database.session() as session:
            row = (
                await session.execute(
                    select(workspaces.c.id).where(workspaces.c.id == workspace_id),
                )
            ).scalar_one_or_none()
        return row is not None

    async def read(self, bad_case_id: str) -> StoredBadCase | None:
        """Return one persisted case without exposing the write transaction."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(
                            bad_cases.c.bad_case_id,
                            bad_cases.c.workspace_id,
                            bad_cases.c.title,
                        ).where(bad_cases.c.bad_case_id == bad_case_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return StoredBadCase(
            bad_case_id=str(row["bad_case_id"]),
            workspace_id=str(row["workspace_id"]),
            title=str(row["title"]),
        )

    async def ingest(self, workspace_id: str, row: BadCaseIngestRow) -> BadCaseIngestWrite:
        """Upsert one report inside a single quota-checked transaction.

        The workspace row is locked first so concurrent distinct ids in one
        workspace serialize their quota decision. SQLite has no row locks, so a
        no-op row write takes the database write lock instead. The bad-case row
        is read second, keeping the lock order workspace → case stable.
        """
        values = _values(row)
        now = now_shanghai()
        async with self._database.transaction() as session:
            quota = await self._lock_workspace(session, workspace_id)
            existing = await self._existing_owner(session, row.bad_case_id)
            if existing is not None and existing != workspace_id:
                raise BadCaseIdConflict(row.bad_case_id)
            already_assigned = await self._workspace_has_case(
                session,
                workspace_id,
                row.bad_case_id,
            )
            if not already_assigned:
                used = await self._used(session, workspace_id)
                if used >= quota:
                    raise QuotaExceeded(quota=quota, used=used)
            if existing is None:
                created = await self._insert(session, workspace_id, values, now=now)
            else:
                created = False
                await self._update(session, row.bad_case_id, values, now=now)
            await self._assign_direct(session, workspace_id, row.bad_case_id, now=now)
            workspace_used = await self._used(session, workspace_id)
            await insert_pending_root(
                session,
                row.session_id,
                now=now,
                rearm_from_source=row.session_source is not None,
            )
        logger.info(
            "workspace bad case ingested",
            extra={
                "workspace_id": workspace_id,
                "bad_case_id": row.bad_case_id,
                "inserted": created,
            },
        )
        return BadCaseIngestWrite(
            bad_case_id=row.bad_case_id,
            created=created,
            workspace_used=workspace_used,
        )

    async def _lock_workspace(self, session: AsyncSession, workspace_id: str) -> int:
        """Serialize the quota decision and return the locked workspace quota."""
        if self._database.dialect == "sqlite":
            await session.execute(
                update(workspaces)
                .where(workspaces.c.id == workspace_id)
                .values(updated_at=workspaces.c.updated_at),
            )
        row = (
            (
                await session.execute(
                    select(workspaces.c.quota)
                    .where(workspaces.c.id == workspace_id)
                    .with_for_update(),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise WorkspaceMissing(workspace_id)
        return int(row["quota"])

    async def _existing_owner(self, session: AsyncSession, bad_case_id: str) -> str | None:
        """Return the workspace that already owns this id, if any."""
        return (
            await session.execute(
                select(bad_cases.c.workspace_id).where(bad_cases.c.bad_case_id == bad_case_id),
            )
        ).scalar_one_or_none()

    async def _reload_owner(self, session: AsyncSession, bad_case_id: str) -> str | None:
        """Re-read the owner as a current read after a primary-key race.

        MySQL's default REPEATABLE READ answers the pre-insert ownership read
        from the snapshot opened before the winner committed, so a plain re-read
        can still miss it. A locking read is a current read: it waits for the
        winner and returns the committed row instead of the stale snapshot.
        """
        return (
            await session.execute(
                select(bad_cases.c.workspace_id)
                .where(bad_cases.c.bad_case_id == bad_case_id)
                .with_for_update(),
            )
        ).scalar_one_or_none()

    async def _insert(
        self,
        session: AsyncSession,
        workspace_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> bool:
        """Insert a new case, degrading a primary-key race to an upsert.

        A concurrent report of the same id can win between the ownership read
        and this insert. Both supported drivers keep the transaction usable
        after a constraint violation, so the loser re-reads the winner as a
        locking read and either updates it or refuses a foreign workspace.
        """
        try:
            await session.execute(
                insert(bad_cases).values(
                    **values,
                    workspace_id=workspace_id,
                    updated_at=now,
                ),
            )
        except IntegrityError as exc:
            if not is_unique_violation(exc):
                raise
            owner = await self._reload_owner(session, str(values["bad_case_id"]))
            if owner is None:
                raise
            if owner != workspace_id:
                raise BadCaseIdConflict(str(values["bad_case_id"])) from exc
            await self._update(session, str(values["bad_case_id"]), values, now=now)
            return False
        return True

    async def _update(
        self,
        session: AsyncSession,
        bad_case_id: str,
        values: dict[str, Any],
        *,
        now: datetime,
    ) -> None:
        """Replace every upstream field of one owned case; never move its workspace."""
        upstream = {column: values[column] for column in _UPSTREAM_COLUMNS}
        await session.execute(
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == bad_case_id)
            .values(**upstream, updated_at=now),
        )

    async def _used(self, session: AsyncSession, workspace_id: str) -> int:
        """Return the distinct live assignment count for one workspace."""
        return int(
            (
                await session.execute(
                    select(func.count(func.distinct(workspace_bad_cases.c.bad_case_id))).where(
                        workspace_bad_cases.c.workspace_id == workspace_id,
                    ),
                )
            ).scalar_one(),
        )

    async def _workspace_has_case(
        self,
        session: AsyncSession,
        workspace_id: str,
        bad_case_id: str,
    ) -> bool:
        """Return whether any assignment source already exposes this case."""
        return (
            await session.execute(
                select(workspace_bad_cases.c.bad_case_id)
                .where(
                    workspace_bad_cases.c.workspace_id == workspace_id,
                    workspace_bad_cases.c.bad_case_id == bad_case_id,
                )
                .limit(1),
            )
        ).scalar_one_or_none() is not None

    async def _assign_direct(
        self,
        session: AsyncSession,
        workspace_id: str,
        bad_case_id: str,
        *,
        now: datetime,
    ) -> None:
        """Converge legacy ownership to direct ingest without touching catalog rows."""
        await session.execute(
            delete(workspace_bad_cases).where(
                workspace_bad_cases.c.workspace_id == workspace_id,
                workspace_bad_cases.c.bad_case_id == bad_case_id,
                workspace_bad_cases.c.assignment_source == "legacy_owner",
            ),
        )
        direct_exists = (
            await session.execute(
                select(workspace_bad_cases.c.bad_case_id).where(
                    workspace_bad_cases.c.workspace_id == workspace_id,
                    workspace_bad_cases.c.bad_case_id == bad_case_id,
                    workspace_bad_cases.c.assignment_source == "direct_ingest",
                ),
            )
        ).scalar_one_or_none()
        if direct_exists is None:
            await session.execute(
                insert(workspace_bad_cases).values(
                    workspace_id=workspace_id,
                    bad_case_id=bad_case_id,
                    assignment_source="direct_ingest",
                    label=None,
                    assigned_at=now,
                ),
            )
