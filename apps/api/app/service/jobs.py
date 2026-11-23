"""Single-process durable job runner with serial execution and restart recovery."""

import asyncio
import logging
import os
import socket
import traceback
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from app.db.crud.evolution import EvolutionRepository
from app.db.crud.jobs import DEFAULT_LEASE_SECONDS, JobRepository
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.service.events import EventBus, RunEventRecorder
from app.service.evolution.control import EvolutionControlService, PauseAtCheckpoint, checkpoint
from app.service.evolution.engine.contracts import RunBlocked
from app.utils.ids import new_id
from app.utils.redaction import sanitize_job_error, sanitize_job_payload
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

__all__ = [
    "JobRunner",
    "JobSubmission",
    "sanitize_job_error",
    "sanitize_job_payload",
]

JobHandler = Callable[[JobRunRecord], Awaitable[Mapping[str, Any] | None]]
TerminalHook = Callable[[JobRunRecord], Awaitable[None]]
_REUSABLE_DUPLICATE_KINDS = frozenset({"sync", "evolution_retry", "attribution_batch"})
_INTERRUPTIBLE_KINDS = frozenset(
    {
        "sync",
        "evolution_prepare",
        "evolution_advance",
        "evolution_apply",
        "evolution_finalize",
        "evolution_retry",
    },
)
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
    "attribution": "prepare",
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
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        heartbeat_seconds: float = 15.0,
        drain_timeout_seconds: float = 0.0,
        owner: str | None = None,
    ) -> None:
        """Create a runner with no handlers until functional services register them."""
        if lease_seconds <= 0:
            raise ValueError("job lease must be positive")
        if heartbeat_seconds <= 0 or heartbeat_seconds >= lease_seconds:
            raise ValueError("job heartbeat must be positive and shorter than the lease")
        if drain_timeout_seconds < 0:
            raise ValueError("job drain timeout cannot be negative")
        self.repository = repository
        self._bus = bus
        self._run_events = run_events
        self._on_terminal = on_terminal
        self._handlers: dict[str, JobHandler] = {}
        self._kind_lanes: dict[str, asyncio.Semaphore] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._submit_lock = asyncio.Lock()
        self._worker_lock = asyncio.Lock()
        self._closed = False
        self._draining = False
        self._lease_seconds = lease_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._drain_timeout_seconds = drain_timeout_seconds
        self._owner = (owner or f"{socket.gethostname()}:{os.getpid()}")[:64]
        self._control: EvolutionControlService | None = None
        self._runs: EvolutionRepository | None = None

    def set_evolution_control(
        self, control: EvolutionControlService, runs: EvolutionRepository
    ) -> None:
        self._control = control
        self._runs = runs

    def register_handler(
        self,
        kind: str,
        handler: JobHandler,
        *,
        concurrency_limit: int | None = None,
    ) -> None:
        """Register a handler and optionally isolate it from the serial lane."""
        self._handlers[kind] = handler
        if concurrency_limit is not None:
            self._kind_lanes[kind] = asyncio.Semaphore(max(1, concurrency_limit))

    def schedule(self, job_id: str) -> None:
        """Schedule one already-committed queued row for local execution."""
        self._schedule(job_id)

    def set_terminal_hook(self, hook: TerminalHook) -> None:
        """Install post-terminal lifecycle handling for lock-owning services."""
        self._on_terminal = hook

    async def recover(self) -> None:
        """Recover interrupted rows and requeue resumable work without dispatching.

        Every residual running evolution job is requeued as the same stage so
        the stage service can resume from its persisted checkpoint. Sync keeps
        its historical fresh-reference retry because it has no run checkpoint.
        """
        await self.repository.requeue_running_kind("attribution_batch")
        recovered = await self.repository.mark_running_interrupted("process restarted")
        for job in recovered:
            try:
                await self._record_interruption(
                    job,
                    message="job interrupted by process restart",
                )
            except Exception:
                logger.exception(
                    "failed to persist restart interruption",
                    extra={"job_id": job.id, "kind": job.kind},
                )
            try:
                await self._notify_terminal(job)
            except Exception:
                logger.exception(
                    "failed to run restart terminal hook",
                    extra={"job_id": job.id, "kind": job.kind},
                )
            try:
                queued = await self._requeue_interrupted(job)
            except Exception:
                logger.exception(
                    "failed to requeue interrupted job",
                    extra={"job_id": job.id, "kind": job.kind},
                )
                continue
            if queued is not None and job.kind != "sync":
                await self._record_recovery(job, queued.id)

        if self._control:
            for run_id in await self._control.repository.pending_acknowledgements():
                await self._control.acknowledge(run_id)

    async def _requeue_interrupted(self, job: JobRunRecord) -> JobRunRecord | None:
        """Persist the replacement row for one resumable interrupted job."""
        if job.kind not in _INTERRUPTIBLE_KINDS:
            return None
        if job.kind == "sync":
            return await self.repository.insert(
                kind=job.kind,
                payload=job.payload,
                ref_id=new_id(),
                created_by=job.created_by,
            )
        if self._control:
            queued_id = await self._control.repository.requeue_interrupted(job)
            return await self.repository.get(queued_id) if queued_id else None
        if await self.repository.find_active(job.kind, job.ref_id) is not None:
            return None
        payload = dict(job.payload)
        if job.kind == "evolution_retry":
            payload["recovery"] = True
        return await self.repository.insert(
            kind=job.kind,
            payload=payload,
            ref_id=job.ref_id,
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
            if self._closed and not self._draining:
                raise RuntimeError("job runner is closed")
            if self._control and ref_id and kind in _KIND_TO_STAGE:
                job_id, reused = await self._control.repository.admit(
                    ref_id,
                    kind,
                    sanitize_job_payload(payload),
                    created_by,
                )
                self.schedule(job_id)
                return JobSubmission(await self.get(job_id), reused)
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
        """Join local work or follow an attribution child already claimed elsewhere."""
        while True:
            task = self._tasks.get(job_id)
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            job = await self.get(job_id)
            if (
                job.kind != "attribution_batch"
                or job.status not in {"queued", "running"}
                or self._closed
                or job.kind not in self._handlers
            ):
                return job
            if job.status == "queued" or (
                job.lease_expires_at is None or job.lease_expires_at <= now_shanghai()
            ):
                self._schedule(job_id)
            await asyncio.sleep(0.25)

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
        observation: Mapping[str, Any] | None = None,
    ) -> JobRunRecord:
        """Persist normalized progress and notify the job's run topic."""
        normalized = min(1.0, max(0.0, float(progress)))
        metrics = None
        if observation is not None:
            metrics = sanitize_job_payload(observation)
            # Observations carry a usage counter alongside redacted diagnostic fields.
            count = observation.get("tokenCount")
            if type(count) is int and count >= 0:
                metrics["tokenCount"] = count
        await self.repository.update_progress(job_id, normalized, metrics)
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

    async def cancel(self, job_id: str) -> JobRunRecord:
        """Cancel queued or in-process work and retain its audit row."""
        job = await self.get(job_id)
        if job.status not in {"queued", "running"}:
            return job
        cancelled = await self.repository.request_cancel(job_id)
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if cancelled is None:
            return await self.get(job_id)
        return cancelled

    async def retry(
        self,
        job_id: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> JobRunRecord:
        """Requeue a retryable terminal job on its original handler lane."""
        existing = await self.get(job_id)
        retried = await self.repository.retry(job_id, payload=payload)
        if retried is None:
            raise AppError(
                status_code=409,
                code=ErrorCode.RUN_BUSY,
                message="job is not retryable",
                details={
                    "jobId": job_id,
                    "status": existing.status,
                    "attempt": existing.attempt,
                    "maxAttempts": existing.max_attempts,
                },
            )
        self._schedule(job_id)
        return retried

    async def close(self) -> None:
        """Stop accepting work, drain the active handler, then cancel the rest."""
        if self._closed:
            return
        self._draining = True
        self._closed = True
        try:
            await self._drain_and_cancel()
        finally:
            self._draining = False

    async def _drain_and_cancel(self) -> None:
        """Wait for the active handler, then cancel every remaining local task."""
        active = set(self._active_tasks)
        if active:
            _done, pending = await asyncio.wait(
                active,
                timeout=self._drain_timeout_seconds,
            )
            if pending:
                logger.warning(
                    "job drain window expired; interrupting active handler",
                    extra={"drain_timeout_seconds": self._drain_timeout_seconds},
                )
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        tasks = [task for task in self._tasks.values() if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._active_tasks.clear()

    async def _run(self, job_id: str) -> None:
        """Claim on the production serial lane or the registered independent lane."""
        pending = await self.repository.get(job_id)
        if pending is None:
            return
        lane = self._kind_lanes.get(pending.kind, self._worker_lock)
        async with lane:
            job = await self.repository.claim(
                job_id,
                owner=self._owner,
                lease_seconds=self._lease_seconds,
            )
            if job is None:
                return
            handler = self._handlers.get(job.kind)
            current = asyncio.current_task()
            if current is not None:
                self._active_tasks.add(current)
            heartbeat = asyncio.create_task(
                self._heartbeat(job, current),
                name=f"job-heartbeat:{job.id}",
            )
            try:
                if handler is None:
                    raise RuntimeError(f"no handler registered for job kind {job.kind}")
                if self._runs and job.ref_id and job.kind in _KIND_TO_STAGE:
                    await checkpoint(self._runs, job.ref_id)
                result = await handler(job)
                await self.repository.complete(job.id, result, owner=self._owner)
            except PauseAtCheckpoint:
                await self.repository.complete(
                    job.id, {"runId": job.ref_id, "yielded": True}, owner=self._owner
                )
            except asyncio.CancelledError:
                interrupted = await self.repository.interrupt(
                    job.id,
                    "job cancelled during shutdown",
                    owner=self._owner,
                )
                if not interrupted:
                    raise
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
                            detail=exc.detail,
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
                # Keep the claim until the recoverable failure is visible to pause/resume.
                await self.repository.fail(job.id, error, owner=self._owner)
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
                record_failed = getattr(self._run_events, "record_failed", None)
                stage = _failure_event_stage(job, exc)
                if callable(record_failed) and job.ref_id and stage is not None:
                    declared_stage = getattr(exc, "stage", None)
                    try:
                        failure_args = {
                            "run_id": job.ref_id,
                            "stage": stage,
                            "message": "任务执行失败",
                            "job_id": job.id,
                            "error": exc,
                            "error_detail": traceback.format_exc(),
                        }
                        if isinstance(declared_stage, str) and declared_stage:
                            failure_args["error_stage"] = declared_stage
                        await record_failed(
                            **failure_args,
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
                await self.repository.fail(job.id, error, owner=self._owner)
                logger.error(
                    "job execution failed",
                    extra={"job_id": job.id, "kind": job.kind, "error_type": type(exc).__name__},
                )
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
                if current is not None:
                    self._active_tasks.discard(current)
                terminal = await self.repository.get(job.id)
                if terminal is not None:
                    await self._notify_terminal(terminal)

    async def _heartbeat(
        self,
        job: JobRunRecord,
        owner_task: asyncio.Task[None] | None,
    ) -> None:
        """Renew the running job lease until completion or lost ownership."""
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            try:
                alive = await self.repository.renew(
                    job.id,
                    owner=self._owner,
                    lease_seconds=self._lease_seconds,
                )
            except Exception:
                logger.exception(
                    "job lease renewal failed",
                    extra={"job_id": job.id, "kind": job.kind},
                )
                continue
            if alive:
                continue
            current = await self.repository.get(job.id)
            if current is not None and current.cancel_requested:
                if owner_task is not None:
                    owner_task.cancel()
                return
            if current is None or current.status != "running":
                # The handler already wrote its terminal row (for example fail()
                # before recording the blocked event). Do not cancel its
                # bookkeeping just because the lease was cleared by that write.
                return
            if current.lease_owner not in (None, self._owner):
                logger.warning(
                    "job lease lost to another owner; interrupting local handler",
                    extra={"job_id": job.id, "kind": job.kind},
                )
                if owner_task is not None and not owner_task.done():
                    owner_task.cancel()
            return

    async def _record_recovery(
        self,
        interrupted: JobRunRecord,
        queued_job_id: str,
    ) -> None:
        """Best-effort run event tying one interruption to its recovery job."""
        record = getattr(self._run_events, "record_recovered", None)
        if not callable(record) or not interrupted.ref_id:
            return
        stage = _KIND_TO_STAGE.get(interrupted.kind)
        if stage is None:
            return
        try:
            await record(
                run_id=interrupted.ref_id,
                stage=stage,
                message="进程重启后已自动重新排队",
                job_id=queued_job_id,
                previous_job_id=interrupted.id,
            )
        except Exception:
            logger.exception(
                "failed to persist job recovery event",
                extra={"job_id": interrupted.id, "kind": interrupted.kind},
            )

    async def _notify_terminal(self, job: JobRunRecord) -> None:
        """Run terminal lifecycle handling without masking the job outcome."""
        if self._control and job.ref_id and job.kind in _KIND_TO_STAGE:
            await self._control.acknowledge(job.ref_id)
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
        if self._runs:
            run = await self._runs.get_run(job.ref_id)
            if run and run.control_state != "running":
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
    if declared in {"patch", "commit"}:
        return "candidate"
    return _KIND_TO_STAGE.get(job.kind)
