"""Periodic single-flight trigger for bad-case root trajectory backfill."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from app.config import Settings
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository, BadCaseRootSyncStats
from app.errors import AppError, ErrorCode
from app.service.jobs import JobRunner
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

KIND = "bad_case_root_sync"

TriggerStatus = Literal["queued", "reused", "idle", "skipped", "unavailable"]
SyncStatus = Literal["unavailable", "idle", "queued", "running", "failed"]


@dataclass(frozen=True, slots=True)
class BadCaseSyncTriggerResult:
    """Outcome of one scheduler tick."""

    status: TriggerStatus
    job_id: str | None
    reused: bool


@dataclass(frozen=True, slots=True)
class BadCaseSyncStatus:
    """Read-only status block merged into the acquisition response."""

    total: int
    synced: int
    unsynced: int
    syncing: int
    failed: int
    status: SyncStatus
    last_run_at: datetime | None
    last_error: str | None


class BadCaseRootSyncCoordinator:
    """Own the periodic trigger; JobRunner owns execution and serialization."""

    def __init__(
        self,
        jobs: JobRunner,
        repository: BadCaseRootSyncRepository,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = now_shanghai,
    ) -> None:
        """Bind the process-scoped runner, state repository, and schedule."""
        self._jobs = jobs
        self._repository = repository
        self._settings = settings
        self._clock = clock
        self._scheduler_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    @property
    def available(self) -> bool:
        """Return whether the global query service is configured."""
        return self._settings.session_query_configured

    async def _sources_available(self) -> bool:
        """Return whether any root can be synced by a global or report source."""
        if self.available:
            return True
        return await self._repository.has_report_source()

    async def source_available(self) -> bool:
        """Expose whether progress is possible without a configuration change."""
        return await self._sources_available()

    async def trigger(self, source: str) -> BadCaseSyncTriggerResult:
        """Submit one job unless unavailable, already active, or idle."""
        if not await self._sources_available():
            return BadCaseSyncTriggerResult("unavailable", None, False)
        active = await self._jobs.repository.find_active_kind(KIND)
        if active is not None:
            return BadCaseSyncTriggerResult("skipped", active.id, True)
        if await self._repository.count_candidates(self._clock()) == 0:
            return BadCaseSyncTriggerResult("idle", None, False)
        try:
            submitted = await self._jobs.submit(
                kind=KIND,
                payload={"source": source},
                ref_id=KIND,
                created_by=None,
            )
        except AppError as exc:
            if exc.code is ErrorCode.RUN_BUSY:
                return BadCaseSyncTriggerResult("skipped", None, True)
            raise
        return BadCaseSyncTriggerResult(
            "reused" if submitted.reused else "queued",
            submitted.job.id,
            submitted.reused,
        )

    async def run_once(self) -> BadCaseSyncTriggerResult:
        """Run one scheduler tick through the same trigger."""
        return await self.trigger("scheduler")

    async def start(self) -> None:
        """Re-arm recoverable rows when a source exists, then start the loop."""
        if self._scheduler_task is not None or self._settings.bad_case_sync_interval_seconds == 0:
            return
        # Parked rows stay unavailable while no source can run. Once a global
        # query or a per-report source exists, one fresh claim is worth it: the
        # configuration change may be exactly what unblocks them. A synced root
        # whose Session disappeared gets the same one-shot recovery.
        if await self._sources_available():
            await self._repository.reset_deterministic_failures()
            await self._repository.rearm_missing_sessions()
        self._stop.clear()
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(),
            name="bad-case-root-sync-scheduler",
        )

    async def stop(self) -> None:
        """Cancel and await the scheduler before the runner closes."""
        self._stop.set()
        task = self._scheduler_task
        self._scheduler_task = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def status(self) -> BadCaseSyncStatus:
        """Read current counts, active job state, and the latest failure."""
        stats: BadCaseRootSyncStats = await self._repository.stats()
        last_run_at = await self._repository.last_run_at()
        last_error = await self._repository.last_error()
        if not await self._sources_available():
            return _status(stats, "unavailable", last_run_at, last_error)
        active = await self._jobs.repository.find_active_kind(KIND)
        if active is not None:
            return _status(
                stats,
                cast(SyncStatus, active.status),
                last_run_at,
                last_error,
            )
        state: SyncStatus = "failed" if stats.failed > 0 else "idle"
        return _status(stats, state, last_run_at, last_error)

    async def _scheduler_loop(self) -> None:
        interval = self._settings.bad_case_sync_interval_seconds
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break
            except TimeoutError:
                pass
            try:
                await self.run_once()
            except Exception as exc:
                code = exc.code.value if isinstance(exc, AppError) else "UNEXPECTED_ERROR"
                logger.error(
                    "bad-case root sync trigger failed (%s/%s)",
                    type(exc).__name__,
                    code,
                    extra={"error_type": type(exc).__name__, "error_code": code},
                )


def _status(
    stats: BadCaseRootSyncStats,
    status: SyncStatus,
    last_run_at: datetime | None,
    last_error: str | None,
) -> BadCaseSyncStatus:
    return BadCaseSyncStatus(
        total=stats.total,
        synced=stats.synced,
        unsynced=stats.unsynced,
        syncing=stats.syncing,
        failed=stats.failed,
        status=status,
        last_run_at=last_run_at,
        last_error=last_error,
    )
