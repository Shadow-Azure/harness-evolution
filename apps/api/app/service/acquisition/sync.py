"""Single-flight acquisition sync coordination and background scheduling."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.config import Settings
from app.db.base import Database
from app.db.crud.acquisition_replay import (
    SyncBatchSnapshot,
    count_pending_payloads,
    read_sync_status_snapshot,
    terminalize_sync_run,
)
from app.db.crud.jobs import JobRepository
from app.db.crud.sync import SyncLockConflict, SyncLockRepository
from app.db.models.jobs import JobRunRecord
from app.errors import AppError
from app.service.acquisition.normalize import CURRENT_PARSER_VERSION
from app.service.acquisition.replay import ReplayResult, replay_pending_payloads
from app.service.jobs import JobRunner
from app.utils.ids import new_id
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncTriggerResult:
    """Result returned for scheduler and administrator sync triggers."""

    status: Literal["queued", "reused", "idle"]
    job_id: str | None
    reused: bool


@dataclass(frozen=True, slots=True)
class SyncStatus:
    """Durable acquisition status exposed to the quiet prototype top bar."""

    active_job_id: str | None
    status: str
    pending: int
    processed: int
    imported: int
    skipped: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    errors: tuple[dict[str, object], ...]


class SyncCoordinator:
    """Own the shared trigger, sync lock, replay handler, and schedule."""

    def __init__(
        self,
        database: Database,
        jobs: JobRunner,
        job_repository: JobRepository,
        settings: Settings,
    ) -> None:
        """Wire one process-scoped coordinator into the existing job runner."""
        self.database = database
        self.jobs = jobs
        self.job_repository = job_repository
        self.settings = settings
        self.locks = SyncLockRepository(database)
        self._local_lock = asyncio.Lock()
        self._owner = f"{socket.gethostname()}:{os.getpid()}:{new_id()}"[:64]
        self._scheduler_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._next_run_at: datetime | None = None
        jobs.register_handler("sync", self._handle_sync)

    async def start_scheduler(self) -> None:
        """Recover stale locks and start the configured periodic trigger."""
        if self._scheduler_task is not None:
            return
        await self.locks.remove_stale()
        await self.locks.adopt_active_job(
            owner=self._owner,
            ttl_seconds=self.settings.sync_lock_ttl_seconds,
        )
        if self.settings.sync_interval_seconds == 0:
            self._next_run_at = None
            return
        self._stop.clear()
        self._next_run_at = now_shanghai() + timedelta(
            seconds=self.settings.sync_interval_seconds,
        )
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(),
            name="acquisition-sync-scheduler",
        )

    async def stop_scheduler(self) -> None:
        """Cancel and await the scheduler before the runner and database close."""
        self._stop.set()
        task = self._scheduler_task
        self._scheduler_task = None
        self._next_run_at = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def trigger(self, source: str, created_by: str | None) -> SyncTriggerResult:
        """Create at most one sync job, reusing an existing active job."""
        async with self._local_lock:
            await self.locks.remove_stale()
            active = await self.locks.active_job()
            if active is None:
                active = await self.locks.adopt_active_job(
                    owner=self._owner,
                    ttl_seconds=self.settings.sync_lock_ttl_seconds,
                )
            if active is None:
                active = await self.job_repository.find_active_kind("sync")
                if active is not None:
                    await self.locks.adopt_active_job(
                        owner=self._owner,
                        ttl_seconds=self.settings.sync_lock_ttl_seconds,
                    )
            if active is not None:
                return SyncTriggerResult("reused", active.id, True)

            pending = await count_pending_payloads(
                self.database,
                CURRENT_PARSER_VERSION,
            )
            if pending == 0:
                return SyncTriggerResult("idle", None, False)

            try:
                locked = await self.locks.create_job(
                    owner=self._owner,
                    source=source,
                    created_by=created_by,
                    ttl_seconds=self.settings.sync_lock_ttl_seconds,
                )
            except SyncLockConflict:
                active = await self.locks.active_job()
                if active is None:
                    active = await self.locks.adopt_active_job(
                        owner=self._owner,
                        ttl_seconds=self.settings.sync_lock_ttl_seconds,
                    )
                if active is None:
                    raise RuntimeError("sync lock conflict without an active job") from None
                return SyncTriggerResult("reused", active.id, True)

            self.jobs.schedule(locked.job.id)
            return SyncTriggerResult("queued", locked.job.id, False)

    async def status(self) -> SyncStatus:
        """Read pending counts, the active job, and the latest durable batch."""
        snapshot = await read_sync_status_snapshot(
            self.database,
            CURRENT_PARSER_VERSION,
        )
        active = snapshot.active_job
        batch = snapshot.batch
        return SyncStatus(
            active_job_id=active.id if active is not None else None,
            status=active.status if active is not None else "idle",
            pending=snapshot.pending,
            processed=snapshot.processed,
            imported=batch.imported if batch is not None else 0,
            skipped=batch.skipped if batch is not None else 0,
            last_run_at=self._batch_time(batch),
            next_run_at=self._next_run_at,
            errors=batch.errors if batch is not None else (),
        )

    async def release_terminal_job(self, job: JobRunRecord) -> None:
        """Finalize abnormal replay audits and release only the owning sync lock."""
        if job.kind == "sync" and job.status not in {"queued", "running"}:
            if job.ref_id and job.status in {"failed", "interrupted"}:
                await terminalize_sync_run(
                    self.database,
                    sync_run_id=job.ref_id,
                    status=job.status,
                    finished_at=job.finished_at or now_shanghai(),
                    code=(
                        "SYNC_JOB_INTERRUPTED" if job.status == "interrupted" else "SYNC_JOB_FAILED"
                    ),
                    message=(
                        "Sync job was interrupted before its audit completed"
                        if job.status == "interrupted"
                        else "Sync job failed before its audit completed"
                    ),
                )
            await self.locks.release(job.id)

    async def run_once(self) -> SyncTriggerResult:
        """Run one scheduler tick through the same single-flight trigger."""
        return await self.trigger("scheduler", None)

    async def _handle_sync(self, job: JobRunRecord) -> dict[str, object]:
        sync_run_id = job.ref_id or new_id()

        async def progress(done: int, total: int) -> None:
            ratio = done / max(total, 1)
            await self.jobs.update_progress(
                job.id,
                ratio,
                unit="payloads",
                total=total,
                stage_label="normalizing",
            )

        result: ReplayResult = await replay_pending_payloads(
            self.database,
            on_progress=progress,
            sync_run_id=sync_run_id,
        )
        return {
            "syncRunId": result.sync_run_id,
            "rootSessions": result.root_sessions,
            "payloads": result.payloads,
            "imported": result.imported,
            "skipped": result.skipped,
            "failed": result.failed,
            "errors": result.errors,
        }

    async def _scheduler_loop(self) -> None:
        interval = self.settings.sync_interval_seconds
        while not self._stop.is_set():
            self._next_run_at = now_shanghai() + timedelta(seconds=interval)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass
            try:
                await self.run_once()
            except Exception as exc:
                safe_code = exc.code.value if isinstance(exc, AppError) else "UNEXPECTED_ERROR"
                logger.error(
                    "scheduled sync trigger failed (%s/%s)",
                    type(exc).__name__,
                    safe_code,
                    extra={
                        "error_type": type(exc).__name__,
                        "error_code": safe_code,
                    },
                )

    @staticmethod
    def _batch_time(batch: SyncBatchSnapshot | None) -> datetime | None:
        if batch is None:
            return None
        return batch.finished_at or batch.started_at
