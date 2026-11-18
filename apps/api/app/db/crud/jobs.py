"""Dialect-neutral persistence for durable job audit rows."""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from sqlalchemy import insert, or_, select, update

from app.db.base import Database
from app.db.models.jobs import JobRunRecord, job_runs, record_from_row
from app.utils.ids import new_id
from app.utils.time import now_shanghai

ACTIVE_JOB_STATUSES = ("queued", "running")
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
        "lease_owner": None,
        "lease_expires_at": None,
        "max_attempts": 3,
        "cancel_requested": False,
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
        owner: str = "local-worker",
        lease_seconds: int = 60,
    ) -> JobRunRecord:
        """Claim queued or lease-expired work and increment its attempt count."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            result = await session.execute(
                update(job_runs)
                .where(
                    job_runs.c.id == job_id,
                    job_runs.c.cancel_requested.is_(False),
                    job_runs.c.attempt < job_runs.c.max_attempts,
                    or_(
                        job_runs.c.status == "queued",
                        ((job_runs.c.status == "running") & (job_runs.c.lease_expires_at < now)),
                    ),
                )
                .values(
                    status="running",
                    started_at=now,
                    attempt=job_runs.c.attempt + 1,
                    lease_owner=owner,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                ),
            )
            if int(getattr(result, "rowcount", 0) or 0) != 1:
                raise RuntimeError("job is not claimable")
        claimed = await self.get(job_id)
        if claimed is None:
            raise RuntimeError("claimed job disappeared before execution")
        return claimed

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

    async def renew_lease(
        self,
        job_id: str,
        owner: str,
        *,
        lease_seconds: int = 60,
    ) -> bool:
        """Extend one live claim only while its owner and status still match."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            result = await session.execute(
                update(job_runs)
                .where(
                    job_runs.c.id == job_id,
                    job_runs.c.status == "running",
                    job_runs.c.lease_owner == owner,
                    job_runs.c.cancel_requested.is_(False),
                )
                .values(
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                ),
            )
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def complete(
        self,
        job_id: str,
        result: Mapping[str, Any] | None,
        *,
        owner: str | None = None,
    ) -> bool:
        """Record completion only if the caller still owns the live claim."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            statement = update(job_runs).where(job_runs.c.id == job_id)
            if owner is not None:
                statement = statement.where(
                    job_runs.c.status == "running",
                    job_runs.c.lease_owner == owner,
                )
            executed = await session.execute(
                statement.values(
                    status="completed",
                    progress=1.0,
                    result=dict(result) if result is not None else None,
                    error=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                ),
            )
        return int(getattr(executed, "rowcount", 0) or 0) == 1

    async def fail(
        self,
        job_id: str,
        error: str,
        *,
        owner: str | None = None,
    ) -> bool:
        """Record failure only if the caller still owns the live claim."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            statement = update(job_runs).where(job_runs.c.id == job_id)
            if owner is not None:
                statement = statement.where(
                    job_runs.c.status == "running",
                    job_runs.c.lease_owner == owner,
                )
            executed = await session.execute(
                statement.values(
                    status="failed",
                    error=error,
                    lease_owner=None,
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                ),
            )
        return int(getattr(executed, "rowcount", 0) or 0) == 1

    async def interrupt(
        self,
        job_id: str,
        reason: str,
        *,
        owner: str | None = None,
    ) -> bool:
        """Record interruption only while the optional owner holds the claim."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            statement = update(job_runs).where(
                job_runs.c.id == job_id,
                job_runs.c.status == "running",
            )
            if owner is not None:
                statement = statement.where(job_runs.c.lease_owner == owner)
            executed = await session.execute(
                statement.values(
                    status="interrupted",
                    error=reason,
                    lease_owner=None,
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                ),
            )
        return int(getattr(executed, "rowcount", 0) or 0) == 1

    async def mark_running_interrupted(
        self,
        reason: str,
        *,
        exclude_kinds: tuple[str, ...] = (),
    ) -> list[JobRunRecord]:
        """Atomically turn every residual running row into an interrupted audit row."""
        async with self._database.session() as session:
            statement = select(job_runs.c.id).where(job_runs.c.status == "running")
            if exclude_kinds:
                statement = statement.where(job_runs.c.kind.not_in(exclude_kinds))
            ids: list[str] = list((await session.execute(statement)).scalars())
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
                    lease_owner=None,
                    lease_expires_at=None,
                    error="worker restarted; claim released",
                    updated_at=now,
                ),
            )
        return int(getattr(result, "rowcount", 0) or 0)

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
                    lease_owner=None,
                    lease_expires_at=None,
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
                "lease_owner": None,
                "lease_expires_at": None,
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
