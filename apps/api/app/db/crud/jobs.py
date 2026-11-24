"""Dialect-neutral persistence for durable job audit rows."""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import and_, func, insert, or_, select, update
from sqlalchemy.engine import CursorResult

from app.db.base import Database
from app.db.crud.evolution_lock import lock_run_row
from app.db.models.jobs import JobRunRecord, job_runs, record_from_row
from app.utils.ids import new_id
from app.utils.time import now_shanghai

ACTIVE_JOB_STATUSES = ("queued", "running")
DEFAULT_LEASE_SECONDS = 90
_LEASE_CLEARED = {
    "lease_owner": None,
    "lease_expires_at": None,
    "heartbeat_at": None,
}
EVOLUTION_JOB_KINDS = (
    "evolution_prepare",
    "evolution_advance",
    "evolution_apply",
    "evolution_finalize",
    "evolution_retry",
)


def queued_job_values(
    *,
    job_id: str,
    kind: str,
    payload: Mapping[str, Any],
    ref_id: str | None,
    created_by: str | None,
) -> dict[str, Any]:
    """Build the complete insert payload for one queued local job."""
    now = now_shanghai()
    return {
        "id": job_id,
        "kind": kind,
        "ref_id": ref_id,
        "status": "queued",
        "progress": 0.0,
        "executor": "local",
        "external_job_id": None,
        "attempt": 0,
        "payload": dict(payload),
        "result": None,
        "error": None,
        "created_by": created_by,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "updated_at": now,
    }


class JobRepository:
    """Read and mutate job state through one shared SQLAlchemy expression tree."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database boundary."""
        self._database = database

    async def insert(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> JobRunRecord:
        """Insert one queued local job and return its durable audit row."""
        job_id = new_id()
        async with self._database.transaction() as session:
            await session.execute(
                insert(job_runs).values(
                    **queued_job_values(
                        job_id=job_id,
                        kind=kind,
                        payload=payload,
                        ref_id=ref_id,
                        created_by=created_by,
                    ),
                ),
            )
        created = await self.get(job_id)
        if created is None:
            raise RuntimeError("created job disappeared before response")
        return created

    async def get(self, job_id: str) -> JobRunRecord | None:
        """Return one job by stable identifier."""
        async with self._database.session() as session:
            row = (
                (await session.execute(select(job_runs).where(job_runs.c.id == job_id)))
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None

    async def find_active(self, kind: str, ref_id: str | None) -> JobRunRecord | None:
        """Return an active job that conflicts with this kind and resource reference."""
        if ref_id is None:
            return None
        kind_condition = (
            job_runs.c.kind.in_(EVOLUTION_JOB_KINDS)
            if kind in EVOLUTION_JOB_KINDS
            else job_runs.c.kind == kind
        )
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(job_runs)
                        .where(
                            kind_condition,
                            job_runs.c.ref_id == ref_id,
                            job_runs.c.status.in_(ACTIVE_JOB_STATUSES),
                        )
                        .order_by(job_runs.c.created_at.desc())
                        .limit(1),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None

    async def find_active_kind(self, kind: str) -> JobRunRecord | None:
        """Return the newest active job of one kind, independent of resource id."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(job_runs)
                        .where(
                            job_runs.c.kind == kind,
                            job_runs.c.status.in_(ACTIVE_JOB_STATUSES),
                        )
                        .order_by(job_runs.c.created_at.desc())
                        .limit(1),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None

    async def list_recent(self, limit: int = 100) -> list[JobRunRecord]:
        """Return recent jobs for recovery diagnostics and tests."""
        async with self._database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(job_runs).order_by(job_runs.c.created_at.desc()).limit(limit),
                    )
                )
                .mappings()
                .all()
            )
        return [record_from_row(row) for row in rows]

    async def list_queued(self, limit: int = 1_000) -> list[JobRunRecord]:
        """Return durable queued rows in insertion order for worker recovery."""
        async with self._database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(job_runs)
                        .where(job_runs.c.status == "queued")
                        .order_by(job_runs.c.created_at)
                        .limit(limit),
                    )
                )
                .mappings()
                .all()
            )
        return [record_from_row(row) for row in rows]

    async def claim(
        self,
        job_id: str,
        *,
        owner: str = "local",
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> JobRunRecord | None:
        """Atomically claim a queued or lease-expired running job.

        A queued row is the normal path. Reclaiming an expired running row is
        the future multi-instance safety valve; startup recovery still marks
        residual rows interrupted before dispatch in the single-instance
        deployment.
        """
        if lease_seconds <= 0:
            raise ValueError("job lease must be positive")
        job = await self.get(job_id)
        if job is None or job.status not in ACTIVE_JOB_STATUSES:
            return None
        now = now_shanghai()
        async with self._database.transaction() as session:
            if job.ref_id and job.kind in EVOLUTION_JOB_KINDS:
                await lock_run_row(session, job.ref_id)
            if job.kind == "attribution_batch" and job.attempt >= job.max_attempts:
                await session.execute(
                    update(job_runs)
                    .where(
                        job_runs.c.id == job_id,
                        job_runs.c.status.in_(ACTIVE_JOB_STATUSES),
                        job_runs.c.attempt >= job_runs.c.max_attempts,
                        or_(
                            job_runs.c.lease_expires_at.is_(None), job_runs.c.lease_expires_at < now
                        ),
                    )
                    .values(
                        status="interrupted",
                        error="attribution worker lease expired at attempt limit",
                        finished_at=now,
                        updated_at=now,
                        **_LEASE_CLEARED,
                    )
                )
                return None
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(job_runs)
                    .where(
                        job_runs.c.id == job_id,
                        job_runs.c.cancel_requested.is_(False),
                        or_(
                            job_runs.c.kind != "attribution_batch",
                            job_runs.c.attempt < job_runs.c.max_attempts,
                        ),
                        or_(
                            job_runs.c.status == "queued",
                            and_(
                                job_runs.c.status == "running",
                                or_(
                                    job_runs.c.lease_expires_at.is_(None),
                                    job_runs.c.lease_expires_at < now,
                                ),
                            ),
                        ),
                    )
                    .values(
                        status="running",
                        started_at=now,
                        attempt=job_runs.c.attempt + 1,
                        lease_owner=owner,
                        lease_expires_at=now + timedelta(seconds=lease_seconds),
                        heartbeat_at=now,
                        finished_at=None,
                        error=None,
                        updated_at=now,
                    ),
                ),
            )
        if result.rowcount != 1:
            return None
        return await self.get(job_id)

    async def renew(
        self,
        job_id: str,
        *,
        owner: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> bool:
        """Extend the lease only while this owner still holds the running row."""
        if lease_seconds <= 0:
            raise ValueError("job lease must be positive")
        now = now_shanghai()
        async with self._database.transaction() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(job_runs)
                    .where(
                        job_runs.c.id == job_id,
                        job_runs.c.status == "running",
                        job_runs.c.lease_owner == owner,
                    )
                    .values(
                        lease_expires_at=now + timedelta(seconds=lease_seconds),
                        heartbeat_at=now,
                        updated_at=now,
                    ),
                ),
            )
        return result.rowcount == 1

    async def release(self, job_id: str, *, owner: str | None = None) -> None:
        """Give up the lease while leaving the row's lifecycle status untouched."""
        conditions = [job_runs.c.id == job_id]
        if owner is not None:
            conditions.append(job_runs.c.lease_owner == owner)
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(*conditions)
                .values(**_LEASE_CLEARED, updated_at=now_shanghai()),
            )

    async def update_progress(
        self,
        job_id: str,
        progress: float,
        result: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist normalized progress and optional sanitized observations."""
        values: dict[str, Any] = {"progress": progress, "updated_at": now_shanghai()}
        if result is not None:
            values["result"] = dict(result)
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs).where(job_runs.c.id == job_id).values(**values),
            )

    async def complete(
        self,
        job_id: str,
        result: Mapping[str, Any] | None,
        *,
        owner: str | None = None,
    ) -> bool:
        """Record successful completion, final progress, and optional result."""
        now = now_shanghai()
        conditions = [job_runs.c.id == job_id]
        if owner is not None:
            conditions.append(job_runs.c.lease_owner == owner)
        async with self._database.transaction() as session:
            changed = await session.execute(
                update(job_runs)
                .where(*conditions)
                .values(
                    status="completed",
                    progress=1.0,
                    result=dict(result) if result is not None else None,
                    error=None,
                    finished_at=now,
                    updated_at=now,
                    **_LEASE_CLEARED,
                ),
            )
        return cast(CursorResult[Any], changed).rowcount == 1

    async def fail(self, job_id: str, error: str, *, owner: str | None = None) -> bool:
        """Record a sanitized terminal failure for the owning worker."""
        now = now_shanghai()
        conditions = [job_runs.c.id == job_id]
        if owner is not None:
            conditions.append(job_runs.c.lease_owner == owner)
        async with self._database.transaction() as session:
            changed = await session.execute(
                update(job_runs)
                .where(*conditions)
                .values(
                    status="failed",
                    error=error,
                    finished_at=now,
                    updated_at=now,
                    **_LEASE_CLEARED,
                ),
            )
        return cast(CursorResult[Any], changed).rowcount == 1

    async def interrupt(
        self,
        job_id: str,
        reason: str,
        *,
        owner: str | None = None,
    ) -> bool:
        """Record process interruption for one active job and its owner."""
        now = now_shanghai()
        conditions = [job_runs.c.id == job_id, job_runs.c.status == "running"]
        if owner is not None:
            conditions.append(job_runs.c.lease_owner == owner)
        async with self._database.transaction() as session:
            changed = await session.execute(
                update(job_runs)
                .where(*conditions)
                .values(
                    status="interrupted",
                    error=reason,
                    finished_at=now,
                    updated_at=now,
                    **_LEASE_CLEARED,
                ),
            )
        return cast(CursorResult[Any], changed).rowcount == 1

    async def mark_running_interrupted(self, reason: str) -> list[JobRunRecord]:
        """Atomically turn every residual running row into an interrupted audit row."""
        async with self._database.session() as session:
            ids: list[str] = list(
                (
                    await session.execute(
                        select(job_runs.c.id).where(job_runs.c.status == "running"),
                    )
                ).scalars()
            )
        for job_id in ids:
            await self.interrupt(job_id, reason)
        recovered: list[JobRunRecord] = []
        for job_id in ids:
            record = await self.get(job_id)
            if record is not None:
                recovered.append(record)
        return recovered

    async def requeue_running_kind(self, kind: str) -> int:
        """Release interrupted claims for a restart-safe handler kind."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            result = await session.execute(
                update(job_runs)
                .where(
                    job_runs.c.kind == kind,
                    job_runs.c.status == "running",
                    job_runs.c.cancel_requested.is_(False),
                    job_runs.c.attempt < job_runs.c.max_attempts,
                )
                .values(
                    status="queued",
                    **_LEASE_CLEARED,
                    error="worker restarted; claim released",
                    updated_at=now,
                ),
            )
        return int(getattr(result, "rowcount", 0) or 0)

    async def latest_interrupted(self, kinds: Sequence[str]) -> list[JobRunRecord]:
        """Return the newest row per kind and resource when a restart interrupted it.

        A replacement job inserted after a previous recovery makes the older
        interrupted row stale; selecting the newest row for each
        ``(kind, ref_id)`` pair keeps a second restart from queueing it again.
        """
        if not kinds:
            return []
        recency = (
            func.row_number()
            .over(
                partition_by=(job_runs.c.kind, job_runs.c.ref_id),
                order_by=(job_runs.c.created_at.desc(), job_runs.c.id.desc()),
            )
            .label("recency")
        )
        ranked = select(*job_runs.c, recency).where(job_runs.c.kind.in_(tuple(kinds))).subquery()
        statement = select(ranked).where(
            ranked.c.recency == 1,
            ranked.c.status == "interrupted",
            ranked.c.cancel_requested.is_(False),
            ranked.c.attempt < ranked.c.max_attempts,
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [record_from_row(row) for row in rows]

    async def requeue_interrupted(self, job_id: str) -> JobRunRecord | None:
        """Return one shutdown-interrupted row to the queue under its own identity."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            result = await session.execute(
                update(job_runs)
                .where(
                    job_runs.c.id == job_id,
                    job_runs.c.status == "interrupted",
                    job_runs.c.cancel_requested.is_(False),
                    job_runs.c.attempt < job_runs.c.max_attempts,
                )
                .values(
                    status="queued",
                    **_LEASE_CLEARED,
                    error=None,
                    finished_at=None,
                    updated_at=now,
                ),
            )
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            return None
        return await self.get(job_id)

    async def request_cancel(self, job_id: str) -> JobRunRecord | None:
        """Persist cancellation for queued or running work."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(job_runs.c.id == job_id, job_runs.c.status.in_(("queued", "running")))
                .values(
                    status="cancelled",
                    cancel_requested=True,
                    error="cancelled by user",
                    **_LEASE_CLEARED,
                    finished_at=now,
                    updated_at=now,
                ),
            )
        return await self.get(job_id)

    async def retry(
        self,
        job_id: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> JobRunRecord | None:
        """Requeue one terminal job while retaining its stable audit identity."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            values: dict[str, Any] = {
                "status": "queued",
                "cancel_requested": False,
                "error": None,
                "started_at": None,
                "finished_at": None,
                **_LEASE_CLEARED,
                "updated_at": now,
            }
            if payload is not None:
                values["payload"] = dict(payload)
            result = await session.execute(
                update(job_runs)
                .where(
                    job_runs.c.id == job_id,
                    job_runs.c.status.in_(("failed", "interrupted", "cancelled")),
                    job_runs.c.attempt < job_runs.c.max_attempts,
                )
                .values(**values),
            )
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            return None
        return await self.get(job_id)

    async def list_for_ref(
        self,
        kind: str,
        ref_id: str,
        *,
        limit: int = 20,
    ) -> list[JobRunRecord]:
        """Return newest jobs for one resource and handler kind."""
        statement = (
            select(job_runs)
            .where(job_runs.c.kind == kind, job_runs.c.ref_id == ref_id)
            .order_by(job_runs.c.created_at.desc())
            .limit(limit)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [record_from_row(row) for row in rows]
