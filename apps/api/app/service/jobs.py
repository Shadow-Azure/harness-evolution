"""Single-process durable job runner with serial execution and restart recovery."""

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.db.crud.jobs import JobRepository
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.service.events import EventBus, RunEventRecorder
from app.service.evolution.engine.contracts import RunBlocked
from app.utils.ids import new_id
from app.utils.redaction import sanitize_job_error, sanitize_job_payload

logger = logging.getLogger(__name__)

__all__ = [
    "JobRunner",
    "JobSubmission",
    "sanitize_job_error",
    "sanitize_job_payload",
]

JobHandler = Callable[[JobRunRecord], Awaitable[Mapping[str, Any] | None]]
TerminalHook = Callable[[JobRunRecord], Awaitable[None]]
_REUSABLE_DUPLICATE_KINDS = frozenset({"sync", "evolution_retry"})
_INTERRUPTIBLE_KINDS = frozenset({"sync"})
_KIND_TO_STAGE = {
    "evolution_prepare": "prepare",
    "evolution_advance": "step",
    "evolution_apply": "apply",
    "evolution_finalize": "final",
    "evolution_retry": "step",
}
_BLOCKED_STAGE_TO_EVENT_STAGE = {
    "patch": "candidate",
    "push": "push",
    "eval": "eval",
}


@dataclass(frozen=True, slots=True)
class JobSubmission:
    """A newly queued job or the active job reused by an idempotent caller."""

    job: JobRunRecord
    reused: bool

    @property
    def id(self) -> str:
        """Expose the stable job identifier for concise service callers."""
        return self.job.id

    @property
    def status(self) -> str:
        """Expose the persisted status at submission time."""
        return self.job.status


class JobRunner:
    """Own queue insertion, the V1 global execution lock, and worker lifecycle."""

    def __init__(
        self,
        repository: JobRepository,
        bus: EventBus,
        run_events: RunEventRecorder | None = None,
        on_terminal: TerminalHook | None = None,
    ) -> None:
        """Create a runner with no handlers until functional services register them."""
        self.repository = repository
        self._bus = bus
        self._run_events = run_events
        self._on_terminal = on_terminal
        self._handlers: dict[str, JobHandler] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._submit_lock = asyncio.Lock()
        self._worker_lock = asyncio.Lock()
        self._closed = False

    def register_handler(self, kind: str, handler: JobHandler) -> None:
        """Register the single callable that owns one durable job kind."""
        self._handlers[kind] = handler

    def schedule(self, job_id: str) -> None:
        """Schedule one already-committed queued row for local execution."""
        self._schedule(job_id)

    def set_terminal_hook(self, hook: TerminalHook) -> None:
        """Install post-terminal lifecycle handling for lock-owning services."""
        self._on_terminal = hook

    async def recover(self) -> None:
        """Recover interrupted rows and create durable retries without dispatching."""
        recovered = await self.repository.mark_running_interrupted("process restarted")
        for job in recovered:
            await self._record_interruption(
                job,
                message="job interrupted by process restart",
            )
            await self._notify_terminal(job)
            if job.kind in _INTERRUPTIBLE_KINDS:
                await self.repository.insert(
                    kind=job.kind,
                    payload=job.payload,
                    ref_id=new_id(),
                    created_by=job.created_by,
                )

    async def start_queued(self) -> None:
        """Dispatch queued work after lock-owning services have adopted state."""
        for queued in await self.repository.list_queued():
            self._schedule(queued.id)

    async def start(self) -> None:
        """Recover and dispatch durable work in one standard startup sequence."""
        await self.recover()
        await self.start_queued()

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> JobSubmission:
        """Persist a queued job, enforce duplicate policy, and schedule execution."""
        async with self._submit_lock:
            if self._closed:
                raise RuntimeError("job runner is closed")
            existing = await self.repository.find_active(kind, ref_id)
            if existing is not None:
                if existing.kind == kind and kind in _REUSABLE_DUPLICATE_KINDS:
                    return JobSubmission(job=existing, reused=True)
                raise AppError(
                    status_code=409,
                    code=ErrorCode.RUN_BUSY,
                    message="another stage job is already active for this run",
                    details={"jobId": existing.id},
                )
            job = await self.repository.insert(
                kind=kind,
                payload=sanitize_job_payload(payload),
                ref_id=ref_id,
                created_by=created_by,
            )
            self._schedule(job.id)
            return JobSubmission(job=job, reused=False)

    async def get(self, job_id: str) -> JobRunRecord:
        """Return a durable job or raise the stable API not-found error."""
        job = await self.repository.get(job_id)
        if job is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.JOB_NOT_FOUND,
                message="job not found",
                details={"jobId": job_id},
            )
        return job

    async def wait(self, job_id: str) -> JobRunRecord:
        """Wait for an in-process task and return its latest durable row."""
        task = self._tasks.get(job_id)
        if task is not None:
            await task
        return await self.get(job_id)

    async def update_progress(
        self,
        job_id: str,
        progress: float,
        *,
        unit: str | None = None,
        total: int | None = None,
        stage_label: str | None = None,
        done_rounds: int = 0,
        accepted: int = 0,
    ) -> JobRunRecord:
        """Persist normalized progress and notify the job's run topic."""
        normalized = min(1.0, max(0.0, float(progress)))
        await self.repository.update_progress(job_id, normalized)
        job = await self.get(job_id)
        if job.ref_id and job.kind != "sync":
            self._bus.publish(
                f"run:{job.ref_id}",
                "run.progress",
                {
                    "runId": job.ref_id,
                    "unit": unit,
                    "total": total,
                    "percent": round(normalized * 100),
                    "status": job.status,
                    "stageLabel": stage_label,
                    "doneRounds": done_rounds,
                    "accepted": accepted,
                },
            )
        return job

    async def close(self) -> None:
        """Cancel active handlers and persist interruption before disposal."""
        if self._closed:
            return
        self._closed = True
        tasks = list(self._tasks.items())
        for _job_id, task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        self._tasks.clear()

    async def _run(self, job_id: str) -> None:
        """Execute one queued job while the global lock serializes all handlers."""
        async with self._worker_lock:
            job = await self.repository.claim(job_id)
            handler = self._handlers.get(job.kind)
            try:
                if handler is None:
                    raise RuntimeError(f"no handler registered for job kind {job.kind}")
                result = await handler(job)
                await self.repository.complete(job.id, result)
            except asyncio.CancelledError:
                await self.repository.interrupt(job.id, "job cancelled during shutdown")
                try:
                    await self._record_interruption(
                        job,
                        message="job interrupted during shutdown",
                    )
                except Exception:
                    logger.exception(
                        "failed to persist shutdown interruption",
                        extra={"job_id": job.id, "kind": job.kind},
                    )
                raise
            except RunBlocked as exc:
                error = sanitize_job_error(str(exc))
                await self.repository.fail(job.id, error)
                record_blocked = getattr(self._run_events, "record_blocked", None)
                event_stage = _BLOCKED_STAGE_TO_EVENT_STAGE[exc.stage]
                if callable(record_blocked) and job.ref_id:
                    try:
                        await record_blocked(
                            job.ref_id,
                            stage=event_stage,
                            blocked_stage=exc.stage,
                            message=str(exc),
                            job_id=job.id,
                            next_retry_at=exc.next_retry_at,
                            retry_attempts=exc.retry_attempts,
                            error=exc,
                        )
                    except Exception:
                        logger.exception(
                            "failed to persist blocked run event",
                            extra={
                                "job_id": job.id,
                                "kind": job.kind,
                                "run_id": job.ref_id,
                            },
                        )
                logger.warning(
                    "job execution blocked",
                    extra={
                        "job_id": job.id,
                        "kind": job.kind,
                        "stage": exc.stage,
                    },
                )
            except Exception as exc:
                error = sanitize_job_error(str(exc))
                await self.repository.fail(job.id, error)
                record_failed = getattr(self._run_events, "record_failed", None)
                stage = _failure_event_stage(job, exc)
                if callable(record_failed) and job.ref_id and stage is not None:
                    try:
                        await record_failed(
                            job.ref_id,
                            stage=stage,
                            message="任务执行失败",
                            job_id=job.id,
                            error=exc,
                            error_detail=traceback.format_exc(),
                        )
                    except Exception:
                        logger.exception(
                            "failed to persist run failure event",
                            extra={
                                "job_id": job.id,
                                "kind": job.kind,
                                "run_id": job.ref_id,
                            },
                        )
                logger.error(
                    "job execution failed",
                    extra={"job_id": job.id, "kind": job.kind, "error_type": type(exc).__name__},
                )
            finally:
                terminal = await self.repository.get(job.id)
                if terminal is not None:
                    await self._notify_terminal(terminal)

    async def _notify_terminal(self, job: JobRunRecord) -> None:
        """Run terminal lifecycle handling without masking the job outcome."""
        if self._on_terminal is None:
            return
        try:
            await self._on_terminal(job)
        except Exception:
            logger.exception(
                "job terminal hook failed",
                extra={"job_id": job.id, "kind": job.kind},
            )

    async def _record_interruption(
        self,
        job: JobRunRecord,
        *,
        message: str,
    ) -> int | None:
        """Persist and publish one interruption using legal stage and job identity."""
        if job.kind == "sync":
            return None
        if self._run_events is None or not job.ref_id:
            return None
        stage = _KIND_TO_STAGE.get(job.kind)
        if stage is None:
            logger.warning(
                "skipping interruption event for unknown evolution job kind",
                extra={"job_id": job.id, "kind": job.kind},
            )
            return None
        event_seq = await self._run_events.record_interrupted(
            run_id=job.ref_id,
            stage=stage,
            message=message,
            job_id=job.id,
        )
        self._bus.publish(
            f"run:{job.ref_id}",
            "run.interrupted",
            {
                "runId": job.ref_id,
                "stage": stage,
                "message": message,
                "eventSeq": event_seq or 0,
            },
            event_id=event_seq,
        )
        return event_seq

    def _schedule(self, job_id: str) -> None:
        """Schedule one durable queue row at most once in this process."""
        if self._closed or job_id in self._tasks:
            return
        task = asyncio.create_task(self._run(job_id), name=f"job:{job_id}")
        self._tasks[job_id] = task

        def forget_task(_task: asyncio.Task[None]) -> None:
            self._tasks.pop(job_id, None)

        task.add_done_callback(forget_task)


def _failure_event_stage(job: JobRunRecord, error: BaseException) -> str | None:
    """Prefer an exception's concrete stage over the coarse job-kind fallback."""
    declared = getattr(error, "stage", None)
    if isinstance(declared, str) and declared in _BLOCKED_STAGE_TO_EVENT_STAGE:
        return _BLOCKED_STAGE_TO_EVENT_STAGE[declared]
    if isinstance(declared, str) and declared in {
        "prepare",
        "cluster",
        "step",
        "candidate",
        "push",
        "eval",
        "apply",
        "final",
    }:
        return declared
    return _KIND_TO_STAGE.get(job.kind)
