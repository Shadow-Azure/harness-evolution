"""Dialect-neutral persistence for durable job audit rows."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import insert, select, update

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

    async def claim(self, job_id: str) -> JobRunRecord:
        """Move one queued job to running and increment its attempt count."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(job_runs.c.id == job_id, job_runs.c.status == "queued")
                .values(
                    status="running",
                    started_at=now,
                    attempt=job_runs.c.attempt + 1,
                    updated_at=now,
                ),
            )
        claimed = await self.get(job_id)
        if claimed is None:
            raise RuntimeError("claimed job disappeared before execution")
        return claimed

    async def update_progress(self, job_id: str, progress: float) -> None:
        """Persist normalized progress without changing terminal state."""
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(job_runs.c.id == job_id)
                .values(progress=progress, updated_at=now_shanghai()),
            )

    async def complete(self, job_id: str, result: Mapping[str, Any] | None) -> None:
        """Record successful completion, final progress, and optional result."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(job_runs.c.id == job_id)
                .values(
                    status="completed",
                    progress=1.0,
                    result=dict(result) if result is not None else None,
                    error=None,
                    finished_at=now,
                    updated_at=now,
                ),
            )

    async def fail(self, job_id: str, error: str) -> None:
        """Record a sanitized terminal failure."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(job_runs.c.id == job_id)
                .values(
                    status="failed",
                    error=error,
                    finished_at=now,
                    updated_at=now,
                ),
            )

    async def interrupt(self, job_id: str, reason: str) -> None:
        """Record process interruption for one active job."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(job_runs)
                .where(job_runs.c.id == job_id, job_runs.c.status == "running")
                .values(
                    status="interrupted",
                    error=reason,
                    finished_at=now,
                    updated_at=now,
                ),
            )

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
