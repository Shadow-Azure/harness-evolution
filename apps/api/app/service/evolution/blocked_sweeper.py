"""Durable blocked-run sweeper driving the automatic 1/5/15-minute backoff."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Protocol

from app.db.crud.evolution import EvolutionRepository
from app.errors import AppError, ErrorCode
from app.service.evolution.backoff import MAX_RETRY_ATTEMPTS
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)


class RetryJobSubmitter(Protocol):
    """Queue seam used to persist durable recovery jobs."""

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> object:
        """Persist and schedule one durable job."""


class EvolutionBlockedSweeper:
    """Enqueue one recovery job per blocked run once its backoff deadline passes."""

    def __init__(
        self,
        runs: EvolutionRepository,
        jobs: RetryJobSubmitter,
        *,
        now: Callable[[], datetime] = now_shanghai,
        scan_interval_seconds: float = 30.0,
        batch_size: int = 100,
    ) -> None:
        """Validate timing, bind persistence and queueing, and start idle."""
        if scan_interval_seconds <= 0:
            raise ValueError("blocked scan interval must be positive")
        if batch_size < 1:
            raise ValueError("blocked scan batch size must be positive")
        self._runs = runs
        self._jobs = jobs
        self._now = now
        self._scan_interval_seconds = scan_interval_seconds
        self._batch_size = batch_size
        self._stop = asyncio.Event()
        self._stop.set()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """Return whether the background loop currently owns a scan task."""
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the process-local loop at most once."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self.run_forever(),
            name="evolution-blocked-sweeper",
        )

    async def stop(self) -> None:
        """Stop the loop, await its cancellation, and stay idempotent."""
        self._stop.set()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def run_forever(self) -> None:
        """Scan timers forever until graceful shutdown."""
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("blocked sweeper scan failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._scan_interval_seconds,
                )
            except TimeoutError:
                continue

    async def run_once(self) -> int:
        """Schedule due push backoffs and return the number of new jobs."""
        due = await self._runs.list_blocked_due(
            self._now(),
            max_attempts=MAX_RETRY_ATTEMPTS,
            limit=self._batch_size,
        )
        scheduled = 0
        for run in due:
            if await self._schedule_retry(run.id, run.created_by):
                scheduled += 1
        return scheduled

    async def _schedule_retry(self, run_id: str, created_by: str | None) -> bool:
        """Submit one automatic retry while tolerating an already-active stage."""
        try:
            submission = await self._jobs.submit(
                kind="evolution_retry",
                payload={"runId": run_id, "automatic": True},
                ref_id=run_id,
                created_by=created_by,
            )
        except AppError as exc:
            if exc.code == ErrorCode.RUN_BUSY:
                return False
            logger.exception(
                "failed to schedule blocked-run retry",
                extra={"run_id": run_id},
            )
            return False
        except Exception:
            logger.exception(
                "failed to schedule blocked-run retry",
                extra={"run_id": run_id},
            )
            return False
        return not bool(getattr(submission, "reused", False))


__all__ = ["EvolutionBlockedSweeper"]
