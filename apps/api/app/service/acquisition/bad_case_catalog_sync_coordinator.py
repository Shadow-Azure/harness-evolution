"""Single-flight scheduling and status aggregation for catalog sync."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from app.config import Settings
from app.db.crud.bad_case_catalog_sync import BadCaseCatalogSyncRepository
from app.errors import AppError, ErrorCode
from app.service.acquisition.bad_case_catalog_sync import (
    KIND,
    BadCaseCatalogSyncService,
)
from app.service.jobs import JobRunner
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

TriggerStatus = Literal["queued", "reused", "idle", "skipped", "unavailable"]
SyncStatus = Literal["unavailable", "idle", "queued", "running", "failed"]


@dataclass(frozen=True, slots=True)
class CatalogSyncTriggerResult:
    """Outcome of one scheduler tick."""

    status: TriggerStatus
    job_id: str | None
    reused: bool


@dataclass(frozen=True, slots=True)
class CatalogSyncStatus:
    """Read-only catalog status merged into the acquisition response."""

    synced: int
    unsynced: int
    last_bad_case_id: int
    status: SyncStatus
    last_run_at: datetime | None
    last_error: str | None


class BadCaseCatalogSyncCoordinator:
    """Own the periodic trigger; JobRunner owns execution and serialization."""

    def __init__(
        self,
        jobs: JobRunner,
        repository: BadCaseCatalogSyncRepository,
        settings: Settings,
        service: BadCaseCatalogSyncService,
        *,
        clock: Callable[[], datetime] = now_shanghai,
    ) -> None:
        """Bind the process-scoped runner, state repository, and schedule."""
        self._jobs = jobs
        self._repository = repository
        self._settings = settings
        self._service = service
        self._clock = clock
        self._scheduler_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    @property
    def available(self) -> bool:
        """Return whether the catalog query service is configured."""
        return bool(self._settings.bad_case_query_configured)

    async def trigger(self, source: str) -> CatalogSyncTriggerResult:
        """Submit one job unless unavailable or already active."""
        if not self.available:
            return CatalogSyncTriggerResult("unavailable", None, False)
        active = await self._jobs.repository.find_active_kind(KIND)
        if active is not None:
            return CatalogSyncTriggerResult("skipped", active.id, True)
        try:
            submitted = await self._jobs.submit(
                kind=KIND,
                payload={"source": source},
                ref_id=KIND,
                created_by=None,
            )
        except AppError as exc:
            if exc.code is ErrorCode.RUN_BUSY:
                return CatalogSyncTriggerResult("skipped", None, True)
            raise
        return CatalogSyncTriggerResult(
            "reused" if submitted.reused else "queued",
            submitted.job.id,
            submitted.reused,
        )

    async def run_once(self) -> CatalogSyncTriggerResult:
        """Run one scheduler tick through the same trigger."""
        return await self.trigger("scheduler")

    async def reconcile(self) -> None:
        """Reset a running row left behind by a previous process."""
        state = await self._repository.get_state()
        if state is None or state.status != "running":
            return
        active = await self._jobs.repository.find_active_kind(KIND)
        if active is not None:
            return
        await self._repository.mark_failed(
            ErrorCode.BAD_CASE_CATALOG_SYNC_INTERRUPTED.value,
            self._clock(),
        )

    async def start(self) -> None:
        """Reconcile, run once immediately, then start the periodic loop."""
        if not self.available:
            return
        try:
            await self.reconcile()
            await self.run_once()
        except Exception as exc:
            code = exc.code.value if isinstance(exc, AppError) else "UNEXPECTED_ERROR"
            logger.error(
                "catalog sync startup trigger failed (%s/%s)",
                type(exc).__name__,
                code,
                extra={"error_type": type(exc).__name__, "error_code": code},
            )
        if self._settings.bad_case_catalog_sync_interval_seconds == 0:
            return
        self._stop.clear()
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(),
            name="bad-case-catalog-sync-scheduler",
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

    async def status(self) -> CatalogSyncStatus:
        """Read counts, the active job state, and the latest failure."""
        state = await self._repository.get_state()
        synced = await self._repository.count_bad_cases()
        last_bad_case_id = state.last_bad_case_id if state is not None else 0
        unsynced = state.pending_count if state is not None else 0
        last_run_at = state.last_run_at if state is not None else None
        last_error = state.last_error if state is not None else None
        if not self.available:
            return CatalogSyncStatus(
                synced=synced,
                unsynced=unsynced,
                last_bad_case_id=last_bad_case_id,
                status="unavailable",
                last_run_at=last_run_at,
                last_error=last_error,
            )
        active = await self._jobs.repository.find_active_kind(KIND)
        if active is not None:
            status = cast(SyncStatus, active.status)
        elif state is not None and state.status == "failed":
            status = "failed"
        else:
            status = "idle"
        return CatalogSyncStatus(
            synced=synced,
            unsynced=unsynced,
            last_bad_case_id=last_bad_case_id,
            status=status,
            last_run_at=last_run_at,
            last_error=last_error,
        )

    async def _scheduler_loop(self) -> None:
        interval = self._settings.bad_case_catalog_sync_interval_seconds
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
                    "catalog sync trigger failed (%s/%s)",
                    type(exc).__name__,
                    code,
                    extra={"error_type": type(exc).__name__, "error_code": code},
                )
