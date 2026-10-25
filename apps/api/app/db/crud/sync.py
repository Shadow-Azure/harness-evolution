"""Durable single-flight coordination for acquisition sync jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.crud.jobs import ACTIVE_JOB_STATUSES, queued_job_values
from app.db.models.jobs import JobRunRecord, job_runs, record_from_row, sync_lock
from app.utils.ids import new_id
from app.utils.time import now_shanghai


@dataclass(frozen=True, slots=True)
class LockedSyncJob:
    """A sync job created together with its durable lock."""

    job: JobRunRecord


class SyncLockConflict(Exception):
    """Another writer acquired the durable sync lock first."""


class SyncLockRepository:
    """Own transactional sync job allocation and matching lock release."""

    def __init__(self, database: Database) -> None:
        """Bind lock operations to the application database boundary."""
        self._database = database

    async def active_job(self) -> JobRunRecord | None:
        """Return the active job currently referenced by the sync lock."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(job_runs)
                        .select_from(
                            sync_lock.join(
                                job_runs,
                                sync_lock.c.job_id == job_runs.c.id,
                            ),
                        )
                        .where(
                            sync_lock.c.name == "sync",
                            job_runs.c.status.in_(ACTIVE_JOB_STATUSES),
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None

    async def create_job(
        self,
        *,
        owner: str,
        source: str,
        created_by: str | None,
        ttl_seconds: int,
    ) -> LockedSyncJob:
        """Create one queued sync job and lock row in a single transaction."""
        job_id = new_id()
        now = now_shanghai()
        expires_at = now + timedelta(seconds=ttl_seconds)
        values = queued_job_values(
            job_id=job_id,
            kind="sync",
            payload={"source": source},
            ref_id=job_id,
            created_by=created_by,
        )
        try:
            async with self._database.transaction() as session:
                await session.execute(insert(job_runs).values(**values))
                await session.execute(
                    insert(sync_lock).values(
                        name="sync",
                        job_id=job_id,
                        owner=owner,
                        acquired_at=now,
                        expires_at=expires_at,
                    ),
                )
        except IntegrityError as exc:
            raise SyncLockConflict from exc
        created = await self._get_job(job_id)
        if created is None:
            raise RuntimeError("created sync job disappeared")
        return LockedSyncJob(job=created)

    async def remove_stale(self) -> None:
        """Delete a lock whose job is missing or already terminal."""
        async with self._database.transaction() as session:
            row = (
                (
                    await session.execute(
                        select(sync_lock.c.name, sync_lock.c.job_id).where(
                            sync_lock.c.name == "sync",
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return
            status = (
                await session.execute(
                    select(job_runs.c.status).where(job_runs.c.id == row["job_id"]),
                )
            ).scalar_one_or_none()
            if status not in ACTIVE_JOB_STATUSES:
                await session.execute(
                    delete(sync_lock).where(
                        sync_lock.c.name == "sync",
                        sync_lock.c.job_id == row["job_id"],
                    ),
                )

    async def adopt_active_job(self, *, owner: str, ttl_seconds: int) -> JobRunRecord | None:
        """Repair a missing/stale lock for one already-active sync job."""
        active = await self._active_kind_job()
        if active is None:
            return None
        now = now_shanghai()
        try:
            async with self._database.transaction() as session:
                current = (
                    await session.execute(
                        select(sync_lock.c.job_id).where(sync_lock.c.name == "sync"),
                    )
                ).scalar_one_or_none()
                if current == active.id:
                    return active
                if current is not None:
                    await session.execute(delete(sync_lock).where(sync_lock.c.name == "sync"))
                await session.execute(
                    insert(sync_lock).values(
                        name="sync",
                        job_id=active.id,
                        owner=owner,
                        acquired_at=now,
                        expires_at=now + timedelta(seconds=ttl_seconds),
                    ),
                )
        except IntegrityError:
            return None
        return active

    async def release(self, job_id: str) -> None:
        """Delete only the lock currently owned by the terminal job."""
        async with self._database.transaction() as session:
            await session.execute(
                delete(sync_lock).where(
                    sync_lock.c.name == "sync",
                    sync_lock.c.job_id == job_id,
                ),
            )

    async def _active_kind_job(self) -> JobRunRecord | None:
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(job_runs)
                        .where(
                            job_runs.c.kind == "sync",
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

    async def _get_job(self, job_id: str) -> JobRunRecord | None:
        async with self._database.session() as session:
            row = (
                (await session.execute(select(job_runs).where(job_runs.c.id == job_id)))
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None
