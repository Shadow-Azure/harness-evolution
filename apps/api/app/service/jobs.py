"""Single-process durable job runner with serial execution and restart recovery."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.db.crud.jobs import JobRepository
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.service.events import EventBus, RunEventRecorder

logger = logging.getLogger(__name__)

JobHandler = Callable[[JobRunRecord], Awaitable[Mapping[str, Any] | None]]
_REUSABLE_DUPLICATE_KINDS = frozenset({"sync", "evolution_retry"})
_INTERRUPTIBLE_KINDS = frozenset({"sync"})
_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[_-]?key)\b"
    r"\s*[:=]\s*(?:bearer\s+)?\S+",
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")
_SENSITIVE_KEY_SUFFIXES = ("password", "passwd", "token", "secret", "authorization", "apikey")


def _redact_text(value: str) -> str:
    """Remove inline credentials from one free-form string."""
    redacted = _SECRET_PATTERN.sub(r"\1=<redacted>", value)
    return _BEARER_PATTERN.sub("Bearer <redacted>", redacted)


def _is_sensitive_key(key: str) -> bool:
    """Recognize credential keys across snake_case and camelCase payloads."""
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized.endswith(_SENSITIVE_KEY_SUFFIXES)


def sanitize_job_payload(value: Any) -> Any:
    """Recursively redact credential fields before a payload becomes durable."""
    if isinstance(value, Mapping):
        return {
            str(key): ("<redacted>" if _is_sensitive_key(str(key)) else sanitize_job_payload(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_job_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def sanitize_job_error(message: str, *, limit: int = 2_000) -> str:
    """Redact credentials, collapse controls, and bound persisted failure text."""
    compact = " ".join(message.splitlines()).strip()
    if not compact:
        return "job failed"
    redacted = _redact_text(compact)
    redacted = _CONTROL_PATTERN.sub(" ", redacted)
    return redacted[:limit]


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
    ) -> None:
        """Create a runner with no handlers until functional services register them."""
        self.repository = repository
        self._bus = bus
        self._run_events = run_events
        self._handlers: dict[str, JobHandler] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._submit_lock = asyncio.Lock()
        self._worker_lock = asyncio.Lock()
        self._closed = False

    def register_handler(self, kind: str, handler: JobHandler) -> None:
        """Register the single callable that owns one durable job kind."""
        self._handlers[kind] = handler

    async def start(self) -> None:
        """Recover interrupted rows before accepting or retrying durable work."""
        recovered = await self.repository.mark_running_interrupted("process restarted")
        for job in recovered:
            if job.kind.startswith("evolution") and job.ref_id:
                event_seq = (
                    await self._run_events.record_interrupted(
                        run_id=job.ref_id,
                        stage=job.kind,
                        message="job interrupted by process restart",
                    )
                    if self._run_events is not None
                    else None
                )
                self._bus.publish(
                    f"run:{job.ref_id}",
                    "run.interrupted",
                    {
                        "runId": job.ref_id,
                        "stage": job.kind,
                        "message": "job interrupted by process restart",
                        "eventSeq": event_seq or 0,
                    },
                    event_id=event_seq,
                )
            if job.kind in _INTERRUPTIBLE_KINDS:
                await self.repository.insert(
                    kind=job.kind,
                    payload=job.payload,
                    ref_id=job.ref_id,
                    created_by=job.created_by,
                )
        for queued in await self.repository.list_queued():
            self._schedule(queued.id)

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
        if job.ref_id:
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
                raise
            except Exception as exc:
                error = sanitize_job_error(str(exc))
                await self.repository.fail(job.id, error)
                logger.error(
                    "job execution failed",
                    extra={"job_id": job.id, "kind": job.kind, "error_type": type(exc).__name__},
                )

    def _schedule(self, job_id: str) -> None:
        """Schedule one durable queue row at most once in this process."""
        if self._closed or job_id in self._tasks:
            return
        task = asyncio.create_task(self._run(job_id), name=f"job:{job_id}")
        self._tasks[job_id] = task

        def forget_task(_task: asyncio.Task[None]) -> None:
            self._tasks.pop(job_id, None)

        task.add_done_callback(forget_task)
