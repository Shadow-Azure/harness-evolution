"""Durable per-root bad-case trajectory sync state and statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, column, func, insert, or_, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.db.base import Database
from app.db.models.domain import bad_case_root_sync, bad_cases
from app.utils.time import as_shanghai

logger = logging.getLogger(__name__)

_SYNCED = "synced"
_SYNCING = "syncing"
_FAILED = "failed"
_PENDING = "pending"


@dataclass(frozen=True, slots=True)
class BadCaseRootSyncRow:
    """One root's durable sync state."""

    root_session_id: str
    status: str
    attempts: int
    last_error: str | None
    agent_count: int
    started_at: datetime | None
    synced_at: datetime | None
    next_retry_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BadCaseRootSyncStats:
    """Counts used by the acquisition status response."""

    total: int
    synced: int
    syncing: int
    failed: int

    @property
    def unsynced(self) -> int:
        """Return every current root that is not successfully synced."""
        return max(0, self.total - self.synced)


def _to_row(values: RowMapping) -> BadCaseRootSyncRow:
    return BadCaseRootSyncRow(
        root_session_id=str(values["root_session_id"]),
        status=str(values["status"]),
        attempts=int(values["attempts"]),
        last_error=values["last_error"] if isinstance(values["last_error"], str) else None,
        agent_count=int(values["agent_count"]),
        started_at=(
            as_shanghai(values["started_at"])
            if isinstance(values["started_at"], datetime)
            else None
        ),
        synced_at=(
            as_shanghai(values["synced_at"]) if isinstance(values["synced_at"], datetime) else None
        ),
        next_retry_at=(
            as_shanghai(values["next_retry_at"])
            if isinstance(values["next_retry_at"], datetime)
            else None
        ),
        lease_owner=values["lease_owner"] if isinstance(values["lease_owner"], str) else None,
        lease_expires_at=(
            as_shanghai(values["lease_expires_at"])
            if isinstance(values["lease_expires_at"], datetime)
            else None
        ),
        updated_at=as_shanghai(values["updated_at"]),
    )


def _candidate_condition(now: datetime) -> ColumnElement[bool]:
    """Return the SQL predicate shared by list/count candidate queries."""
    return or_(
        bad_case_root_sync.c.root_session_id.is_(None),
        bad_case_root_sync.c.status == _PENDING,
        and_(
            bad_case_root_sync.c.status == _FAILED,
            or_(
                bad_case_root_sync.c.next_retry_at.is_(None),
                bad_case_root_sync.c.next_retry_at <= now,
            ),
        ),
        and_(
            bad_case_root_sync.c.status == _SYNCING,
            or_(
                bad_case_root_sync.c.lease_expires_at.is_(None),
                bad_case_root_sync.c.lease_expires_at <= now,
            ),
        ),
    )


def _distinct_roots() -> Subquery:
    """Return distinct bad-case root ids as a subquery."""
    return select(bad_cases.c.bad_case_session_id.label("root_session_id")).distinct().subquery()


def _candidate_query(now: datetime) -> Select[Any]:
    roots = _distinct_roots()
    return (
        select(roots.c.root_session_id.label("candidate_root"))
        .select_from(
            roots.outerjoin(
                bad_case_root_sync,
                bad_case_root_sync.c.root_session_id == roots.c.root_session_id,
            ),
        )
        .where(_candidate_condition(now))
    )


def _missing_bad_cases(exc: OperationalError | ProgrammingError) -> bool:
    """Return whether an operational error is only the external table being absent."""
    return "bad_cases" in str(exc).lower()


class BadCaseRootSyncRepository:
    """Read and write root-sync state without touching external tables."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to one application database."""
        self._database = database

    async def get(self, root_session_id: str) -> BadCaseRootSyncRow | None:
        """Return one root's state or ``None`` when it was never claimed."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(bad_case_root_sync).where(
                            bad_case_root_sync.c.root_session_id == root_session_id,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _to_row(row) if row is not None else None

    async def list_candidates(self, now: datetime, *, limit: int) -> list[str]:
        """Return roots that are unclaimed, retry-due, or lease-expired."""
        statement = _candidate_query(now).order_by(column("candidate_root")).limit(limit)
        try:
            async with self._database.session() as session:
                rows: list[str] = list((await session.execute(statement)).scalars().all())
        except (OperationalError, ProgrammingError) as exc:
            if _missing_bad_cases(exc):
                logger.warning("bad_cases is not provisioned; skipping root-sync candidates")
                return []
            raise
        return [str(row) for row in rows]

    async def count_candidates(self, now: datetime) -> int:
        """Return how many roots the next tick could work on."""
        statement = select(func.count()).select_from(_candidate_query(now).subquery())
        try:
            async with self._database.session() as session:
                value = (await session.execute(statement)).scalar_one()
        except (OperationalError, ProgrammingError) as exc:
            if _missing_bad_cases(exc):
                logger.warning("bad_cases is not provisioned; no root-sync candidates")
                return 0
            raise
        return int(value)

    async def claim(
        self,
        root_session_id: str,
        *,
        owner: str,
        lease_seconds: int,
        now: datetime,
    ) -> bool:
        """Atomically claim one root unless it is terminal or leased."""
        now_value = as_shanghai(now)
        expires_at = now_value + timedelta(seconds=lease_seconds)
        async with self._database.transaction() as session:
            row = (
                (
                    await session.execute(
                        select(bad_case_root_sync)
                        .where(bad_case_root_sync.c.root_session_id == root_session_id)
                        .with_for_update(),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                await session.execute(
                    insert(bad_case_root_sync).values(
                        root_session_id=root_session_id,
                        status=_SYNCING,
                        attempts=1,
                        last_error=None,
                        agent_count=0,
                        started_at=now_value,
                        synced_at=None,
                        next_retry_at=None,
                        lease_owner=owner,
                        lease_expires_at=expires_at,
                        updated_at=now_value,
                    ),
                )
                return True

            status = str(row["status"])
            if status == _SYNCED:
                return False
            if status == _SYNCING:
                lease = row["lease_expires_at"]
                if isinstance(lease, datetime) and as_shanghai(lease) > now_value:
                    return False
            if status == _FAILED:
                retry_at = row["next_retry_at"]
                if isinstance(retry_at, datetime) and as_shanghai(retry_at) > now_value:
                    return False

            await session.execute(
                update(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == root_session_id)
                .values(
                    status=_SYNCING,
                    attempts=int(row["attempts"]) + 1,
                    started_at=now_value,
                    next_retry_at=None,
                    lease_owner=owner,
                    lease_expires_at=expires_at,
                    updated_at=now_value,
                ),
            )
            return True

    async def renew_lease(
        self,
        root_session_id: str,
        *,
        owner: str,
        lease_seconds: int,
        now: datetime,
    ) -> None:
        """Extend a live claim without changing its status or attempt count."""
        now_value = as_shanghai(now)
        async with self._database.transaction() as session:
            await session.execute(
                update(bad_case_root_sync)
                .where(
                    bad_case_root_sync.c.root_session_id == root_session_id,
                    bad_case_root_sync.c.lease_owner == owner,
                )
                .values(
                    lease_expires_at=now_value + timedelta(seconds=lease_seconds),
                    updated_at=now_value,
                ),
            )

    async def mark_synced(
        self,
        root_session_id: str,
        *,
        agent_count: int,
        now: datetime,
    ) -> None:
        """Mark one root's payload set complete and clear retry state."""
        now_value = as_shanghai(now)
        async with self._database.transaction() as session:
            await session.execute(
                update(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == root_session_id)
                .values(
                    status=_SYNCED,
                    agent_count=max(0, agent_count),
                    last_error=None,
                    synced_at=now_value,
                    next_retry_at=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now_value,
                ),
            )

    async def mark_failed(
        self,
        root_session_id: str,
        *,
        error: str,
        next_retry_at: datetime,
        now: datetime,
        agent_count: int | None = None,
    ) -> None:
        """Record a retryable root failure and release its lease."""
        now_value = as_shanghai(now)
        values: dict[str, object] = {
            "status": _FAILED,
            "last_error": error,
            "next_retry_at": as_shanghai(next_retry_at),
            "lease_owner": None,
            "lease_expires_at": None,
            "updated_at": now_value,
        }
        if agent_count is not None:
            values["agent_count"] = max(0, agent_count)
        async with self._database.transaction() as session:
            await session.execute(
                update(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == root_session_id)
                .values(**values),
            )

    async def stats(self) -> BadCaseRootSyncStats:
        """Aggregate status counts for roots still present in bad_cases."""
        roots = _distinct_roots()
        total_statement = select(func.count()).select_from(roots)
        grouped_statement = (
            select(bad_case_root_sync.c.status, func.count().label("count"))
            .select_from(
                roots.outerjoin(
                    bad_case_root_sync,
                    bad_case_root_sync.c.root_session_id == roots.c.root_session_id,
                ),
            )
            .group_by(bad_case_root_sync.c.status)
        )
        async with self._database.session() as session:
            try:
                total_value = (await session.execute(total_statement)).scalar_one()
                rows: list[Any] = list((await session.execute(grouped_statement)).all())
            except (OperationalError, ProgrammingError) as exc:
                if _missing_bad_cases(exc):
                    logger.warning("bad_cases is not provisioned; reporting zero sync stats")
                    return BadCaseRootSyncStats(total=0, synced=0, syncing=0, failed=0)
                raise
        total = int(total_value)
        counts = {str(status): int(count) for status, count in rows if isinstance(status, str)}
        return BadCaseRootSyncStats(
            total=total,
            synced=counts.get(_SYNCED, 0),
            syncing=counts.get(_SYNCING, 0),
            failed=counts.get(_FAILED, 0),
        )

    async def last_run_at(self) -> datetime | None:
        """Return the newest state change for a root still in bad_cases."""
        roots = _distinct_roots()
        statement = select(func.max(bad_case_root_sync.c.updated_at)).select_from(
            roots.join(
                bad_case_root_sync,
                bad_case_root_sync.c.root_session_id == roots.c.root_session_id,
            ),
        )
        try:
            async with self._database.session() as session:
                value = (await session.execute(statement)).scalar_one_or_none()
        except (OperationalError, ProgrammingError) as exc:
            if _missing_bad_cases(exc):
                return None
            raise
        return as_shanghai(value) if isinstance(value, datetime) else None

    async def last_error(self) -> str | None:
        """Return the newest failed current root's sanitized error, if any."""
        roots = _distinct_roots()
        statement = (
            select(bad_case_root_sync.c.last_error)
            .select_from(
                roots.join(
                    bad_case_root_sync,
                    bad_case_root_sync.c.root_session_id == roots.c.root_session_id,
                ),
            )
            .where(
                bad_case_root_sync.c.status == _FAILED,
                bad_case_root_sync.c.last_error.is_not(None),
            )
            .order_by(bad_case_root_sync.c.updated_at.desc())
            .limit(1)
        )
        try:
            async with self._database.session() as session:
                value = (await session.execute(statement)).scalar_one_or_none()
        except (OperationalError, ProgrammingError) as exc:
            if _missing_bad_cases(exc):
                return None
            raise
        return value if isinstance(value, str) else None
