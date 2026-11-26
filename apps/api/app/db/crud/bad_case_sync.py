"""Durable per-root bad-case trajectory sync state and statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, column, exists, func, insert, or_, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.db.base import Database
from app.db.crud.integrity import is_unique_violation
from app.db.crud.read_scope import scoped_case_ids
from app.db.models.domain import bad_case_root_sync, bad_cases, session_families
from app.utils.time import as_shanghai, now_shanghai

logger = logging.getLogger(__name__)

_SYNCED = "synced"
_SYNCING = "syncing"
_FAILED = "failed"
_PENDING = "pending"

_NON_RETRYABLE_ERRORS: frozenset[str] = frozenset(
    {
        "SESSION_QUERY_UNAVAILABLE",
        "SESSION_QUERY_UNAUTHORIZED",
        "SESSION_QUERY_VERSION_INCOMPATIBLE",
        "SESSION_SOURCE_UNAUTHORIZED",
        "SESSION_SOURCE_VERSION_INCOMPATIBLE",
        "SESSION_SOURCE_SESSION_MISMATCH",
        "TRAJECTORY_EMPTY",
        "TRAVERSAL_LIMIT_EXCEEDED",
        "UNSUPPORTED_RUNTIME",
    },
)
"""Stable failures that automatic retries cannot fix without a configuration change."""


@dataclass(frozen=True, slots=True)
class BadCaseRootSyncRow:
    """One root's durable sync state."""

    root_session_id: str
    status: str
    source_kind: str
    source_snapshot: dict[str, object] | None
    attempts: int
    last_error: str | None
    agent_count: int
    started_at: datetime | None
    synced_at: datetime | None
    next_retry_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    updated_at: datetime

    @property
    def deterministic_failure(self) -> bool:
        """Return whether retrying cannot help until the source configuration changes."""
        return self.status == _FAILED and self.last_error in _NON_RETRYABLE_ERRORS


@dataclass(frozen=True, slots=True)
class BadCaseReportSource:
    """The newest per-report download contract for one root session."""

    runtime: str | None
    session_url_template: str

    def snapshot(self) -> dict[str, object]:
        """Return the durable frozen form stored on the root-sync row."""
        return {
            "kind": "report",
            "runtime": self.runtime,
            "session_url_template": self.session_url_template,
        }


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
    snapshot = values["source_snapshot"]
    return BadCaseRootSyncRow(
        root_session_id=str(values["root_session_id"]),
        status=str(values["status"]),
        source_kind=str(values["source_kind"]),
        source_snapshot=(
            {str(key): value for key, value in snapshot.items()}
            if isinstance(snapshot, dict)
            else None
        ),
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


def _retryable_failure_condition() -> ColumnElement[bool]:
    """Exclude failed rows whose stable error cannot change by retrying."""
    return or_(
        bad_case_root_sync.c.last_error.is_(None),
        bad_case_root_sync.c.last_error.not_in(tuple(_NON_RETRYABLE_ERRORS)),
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
            _retryable_failure_condition(),
        ),
        and_(
            bad_case_root_sync.c.status == _SYNCING,
            or_(
                bad_case_root_sync.c.lease_expires_at.is_(None),
                bad_case_root_sync.c.lease_expires_at <= now,
            ),
        ),
    )


def _distinct_roots(workspace_ids: tuple[str, ...] | None = None) -> Subquery:
    """Return distinct bad-case root ids as a subquery."""
    query = select(bad_cases.c.bad_case_session_id.label("root_session_id"))
    if workspace_ids is not None:
        query = query.where(bad_cases.c.bad_case_id.in_(scoped_case_ids(workspace_ids)))
    return query.distinct().subquery()


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


def _pending_values(now: datetime) -> dict[str, object]:
    """Return the clean pending row shared by insert and source re-arm."""
    return {
        "status": _PENDING,
        "source_kind": "global",
        "source_snapshot": None,
        "attempts": 0,
        "last_error": None,
        "started_at": None,
        "next_retry_at": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "updated_at": as_shanghai(now),
    }


async def insert_pending_root(
    session: AsyncSession,
    root_session_id: str,
    *,
    now: datetime,
    rearm_from_source: bool = False,
) -> bool:
    """Insert a `pending` root-sync row, or re-arm a parked deterministic failure.

    This runs inside the caller's transaction so a committed bad case can never
    lack its discoverable root. The insert is insert-if-absent, not an upsert:
    `synced` is absorbing and a `failed` row keeps its retry backoff, so neither
    may be reset by a later report. The exception is a re-report that now carries
    a `sessionSource`: a root that was parked on a deterministic source failure
    gets one fresh claim, because the report may have replaced the broken source.
    A concurrent claim or ingest that wins the insert makes the loser keep the
    existing state.
    """
    existing = (
        (
            await session.execute(
                select(
                    bad_case_root_sync.c.status,
                    bad_case_root_sync.c.last_error,
                ).where(
                    bad_case_root_sync.c.root_session_id == root_session_id,
                ),
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        parked = (
            rearm_from_source
            and existing["status"] == _FAILED
            and existing["last_error"] in _NON_RETRYABLE_ERRORS
        )
        if parked:
            await session.execute(
                update(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == root_session_id)
                .values(**_pending_values(now)),
            )
        return parked
    try:
        await session.execute(
            insert(bad_case_root_sync).values(
                root_session_id=root_session_id,
                agent_count=0,
                synced_at=None,
                **_pending_values(now),
            ),
        )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        return False
    return True


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

    async def reset_deterministic_failures(
        self,
        *,
        now: datetime | None = None,
    ) -> int:
        """Re-arm roots whose stable failure may now be fixable.

        The scheduler skips these rows instead of burning its retry ladder.
        A process start (or a source configuration change) calls this once so a
        newly configured global query or a newly reported session source gets a
        fresh chance; the frozen first-claim snapshot is cleared for re-selection.
        """
        now_value = as_shanghai(now or now_shanghai())
        async with self._database.transaction() as session:
            result = await session.execute(
                update(bad_case_root_sync)
                .where(
                    bad_case_root_sync.c.status == _FAILED,
                    bad_case_root_sync.c.last_error.in_(tuple(_NON_RETRYABLE_ERRORS)),
                )
                .values(
                    status=_PENDING,
                    source_kind="global",
                    source_snapshot=None,
                    attempts=0,
                    last_error=None,
                    started_at=None,
                    next_retry_at=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now_value,
                ),
            )
        return int(getattr(result, "rowcount", 0) or 0)

    async def rearm_missing_sessions(
        self,
        *,
        now: datetime | None = None,
    ) -> int:
        """Re-arm synced roots whose normalized Session no longer exists.

        A completed sync whose Session projection is gone cannot be read; the
        startup hook gives it one fresh fetch instead of leaving a permanent
        ``unavailable`` dead end. Normal synced roots are untouched.
        """
        now_value = as_shanghai(now or now_shanghai())
        missing_session = ~exists(
            select(1)
            .select_from(session_families)
            .where(
                session_families.c.id == bad_case_root_sync.c.root_session_id,
            ),
        )
        async with self._database.transaction() as session:
            result = await session.execute(
                update(bad_case_root_sync)
                .where(
                    bad_case_root_sync.c.status == _SYNCED,
                    missing_session,
                )
                .values(**_pending_values(now_value)),
            )
        return int(getattr(result, "rowcount", 0) or 0)

    async def ensure_pending(
        self,
        root_session_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Make one reported root discoverable without touching existing state."""
        async with self._database.transaction() as session:
            return await insert_pending_root(
                session,
                root_session_id,
                now=now or now_shanghai(),
            )

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

    async def has_report_source(self, workspace_ids: tuple[str, ...] | None = None) -> bool:
        """Return whether any report carries a session source to sync."""
        statement = (
            select(bad_cases.c.bad_case_id)
            .where(bad_cases.c.session_source["sessionUrlTemplate"].as_string() != "")
            .limit(1)
        )
        if workspace_ids is not None:
            statement = statement.where(
                bad_cases.c.bad_case_id.in_(scoped_case_ids(workspace_ids)),
            )
        try:
            async with self._database.session() as session:
                return (await session.execute(statement)).scalar_one_or_none() is not None
        except (OperationalError, ProgrammingError) as exc:
            if _missing_bad_cases(exc):
                return False
            raise

    async def latest_report_source(
        self,
        root_session_id: str,
    ) -> BadCaseReportSource | None:
        """Return the newest non-empty report source for one root session."""
        statement = (
            select(
                bad_cases.c.session_source,
                bad_cases.c.created_at,
                bad_cases.c.bad_case_id,
            )
            .where(
                bad_cases.c.bad_case_session_id == root_session_id,
                bad_cases.c.session_source["sessionUrlTemplate"].as_string() != "",
            )
            .order_by(bad_cases.c.created_at.desc(), bad_cases.c.bad_case_id.desc())
            .limit(1)
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        if row is None or not isinstance(row["session_source"], dict):
            return None
        source = row["session_source"]
        template = source.get("sessionUrlTemplate")
        runtime = source.get("runtime")
        if not isinstance(template, str) or not template:
            return None
        return BadCaseReportSource(
            runtime=runtime if isinstance(runtime, str) else None,
            session_url_template=template,
        )

    async def claim(
        self,
        root_session_id: str,
        *,
        owner: str,
        lease_seconds: int,
        now: datetime,
        source_kind: str | None = None,
        source_snapshot: dict[str, object] | None = None,
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
                return await self._start_syncing(
                    session,
                    root_session_id,
                    owner=owner,
                    now_value=now_value,
                    expires_at=expires_at,
                    source_kind=source_kind,
                    source_snapshot=source_snapshot,
                )

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

            values: dict[str, object] = {
                "status": _SYNCING,
                "attempts": int(row["attempts"]) + 1,
                "started_at": now_value,
                "next_retry_at": None,
                "lease_owner": owner,
                "lease_expires_at": expires_at,
                "updated_at": now_value,
            }
            if row["source_snapshot"] is None:
                values["source_kind"] = source_kind or str(row["source_kind"])
                values["source_snapshot"] = source_snapshot
            await session.execute(
                update(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == root_session_id)
                .values(**values),
            )
            return True

    async def _start_syncing(
        self,
        session: AsyncSession,
        root_session_id: str,
        *,
        owner: str,
        now_value: datetime,
        expires_at: datetime,
        source_kind: str | None,
        source_snapshot: dict[str, object] | None,
    ) -> bool:
        """Insert the first state row for a root that had none when read.

        `insert_pending_root` is a second writer: a report may commit a
        `pending` row for the same root between this claim's read and its
        insert. The primary key then rejects this insert, and the next tick
        claims the now-visible pending row instead of failing the whole job.
        """
        try:
            await session.execute(
                insert(bad_case_root_sync).values(
                    root_session_id=root_session_id,
                    status=_SYNCING,
                    source_kind=source_kind or "global",
                    source_snapshot=source_snapshot,
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
        except IntegrityError as exc:
            if not is_unique_violation(exc):
                raise
            return False
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

    async def stats(self, workspace_ids: tuple[str, ...] | None = None) -> BadCaseRootSyncStats:
        """Aggregate status counts for roots still present in bad_cases."""
        roots = _distinct_roots(workspace_ids)
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

    async def last_run_at(self, workspace_ids: tuple[str, ...] | None = None) -> datetime | None:
        """Return the newest state change for a root still in bad_cases."""
        roots = _distinct_roots(workspace_ids)
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

    async def last_error(self, workspace_ids: tuple[str, ...] | None = None) -> str | None:
        """Return the newest failed current root's sanitized error, if any."""
        roots = _distinct_roots(workspace_ids)
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
