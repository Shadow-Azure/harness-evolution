"""Durable attribution batches shared by prepare, manual, schedule, and retry entrypoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal, cast

from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.models.evolution import EvolutionRunRecord
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.service.evolution.attribution import (
    AttributionRunner,
    AttributionRunProgress,
    AttributionRunSummary,
)
from app.service.evolution.control import PauseAtCheckpoint, checkpoint
from app.service.evolution.engine.contracts import RunBlocked
from app.service.evolution.potential import (
    AnchorSource,
    HitReason,
    OrderState,
    PotentialCase,
    TriggerPoint,
)
from app.service.identity.schemas import IdentityModel
from app.service.jobs import JobRunner, JobSubmission

ATTRIBUTION_JOB_KIND = "attribution_batch"
AttributionJobSource = Literal["prepare", "manual", "schedule", "retry"]


class AttributionJobObservation(IdentityModel):
    """Sanitized throughput, quality, cost, and runtime observations."""

    total: int = 0
    completed: int = 0
    created: int = 0
    reused: int = 0
    failed: int = 0
    non_target: int = 0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    token_count: int | None = 0
    warning_count: int = 0
    evidence_coverage_rate: float = 0.0
    executor: str
    skill_revision: str | None
    context_hash: str | None = None


class AttributionJobView(IdentityModel):
    """One durable attribution execution without raw trace or Skill content."""

    job_id: str
    run_id: str
    source: AttributionJobSource
    status: Literal[
        "queued",
        "running",
        "completed",
        "failed",
        "interrupted",
        "cancelled",
    ]
    progress: float
    attempt: int
    max_attempts: int
    cancel_requested: bool
    observation: AttributionJobObservation
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AttributionJobList(IdentityModel):
    """Newest-first attribution executions for one run."""

    items: list[AttributionJobView]


def _trigger(
    agent_id: str | None,
    event_index: int | None,
    triggered_at: datetime | None,
) -> TriggerPoint:
    """Rebuild one persisted trigger coordinate without guessing tree order."""
    return TriggerPoint(
        agent_id=agent_id,
        event_index=event_index,
        triggered_at=triggered_at,
        tree_index=None,
    )


async def candidate_snapshot(
    run: EvolutionRunRecord,
    candidates: EvolutionRunCandidateRepository,
    attributions: AttributionRepository,
) -> tuple[PotentialCase, ...]:
    """Rebuild included candidates with the original trigger and anchor coordinates."""
    rows = [item for item in await candidates.list(run.id) if item.included]
    evidence = await attributions.load_bad_case_evidence(
        tuple(item.bad_case_id for item in rows),
    )
    return tuple(
        PotentialCase(
            bad_case_id=item.bad_case_id,
            session_id=item.session_id,
            object_name=item.object_name or run.target_name,
            bad_case_type=(
                evidence[item.bad_case_id].bad_case_type if item.bad_case_id in evidence else "self"
            ),
            trigger_at=item.case_trigger_at or item.created_at,
            hit_reason=cast(HitReason, item.included_reason),
            order_state=cast(OrderState, item.order_state),
            included=True,
            anchor_source=cast(AnchorSource, item.case_anchor_kind or "unknown"),
            object_type=item.object_type or run.target_type,
            object_revision=item.object_revision,
            object_trigger=_trigger(
                item.object_trigger_agent_id,
                item.object_trigger_event_index,
                item.object_trigger_at,
            ),
            case_trigger=(
                _trigger(
                    item.case_trigger_agent_id,
                    item.case_trigger_event_index,
                    item.case_trigger_at,
                )
                if item.case_trigger_agent_id is not None
                or item.case_trigger_event_index is not None
                or item.case_trigger_at is not None
                else None
            ),
        )
        for item in rows
    )


class AttributionJobService:
    """Coordinate durable attribution work on an isolated bounded-concurrency lane."""

    def __init__(
        self,
        jobs: JobRunner,
        runs: EvolutionRepository,
        candidates: EvolutionRunCandidateRepository,
        attributions: AttributionRepository,
        runner: AttributionRunner,
    ) -> None:
        """Bind the shared manifest, cache, persistence, and durable worker services."""
        self._jobs = jobs
        self._runs = runs
        self._candidates = candidates
        self._attributions = attributions
        self._runner = runner

    async def submit(
        self,
        run_id: str,
        *,
        created_by: str | None,
        source: AttributionJobSource,
    ) -> JobSubmission:
        """Admit one idempotent batch after the candidate snapshot exists."""
        run = await self._admissible_run(run_id, source)
        return await self._jobs.submit(
            kind=ATTRIBUTION_JOB_KIND,
            payload={"runId": run.id, "source": source},
            ref_id=run.id,
            created_by=created_by,
        )

    async def _admissible_run(
        self, run_id: str, source: AttributionJobSource
    ) -> EvolutionRunRecord:
        run = await self._runs.get_run(run_id)
        if run is None:
            raise AppError(status_code=404, code=ErrorCode.RUN_NOT_FOUND, message="run not found")
        if run.control_state != "running":
            if source == "prepare":
                raise PauseAtCheckpoint
            raise AppError(
                status_code=409,
                code=ErrorCode.RUN_CONTROL_CONFLICT,
                message="attribution requires a running control state",
                details={"controlState": run.control_state},
            )
        if run.progress_unit != 3:
            raise AppError(
                status_code=409,
                code=ErrorCode.RUN_BUSY,
                message="run is not waiting at the attribution stage",
                details={"progressUnit": run.progress_unit},
            )
        return run

    async def run_for_prepare(self, run: EvolutionRunRecord) -> AttributionRunSummary:
        """Submit or join the same durable batch used by every other entrypoint."""
        submission = await self.submit(
            run.id,
            created_by=run.created_by,
            source="prepare",
        )
        terminal = await self._jobs.wait(submission.id)
        if terminal.status != "completed" or terminal.result is None:
            raise RunBlocked(
                terminal.error or "attribution batch did not complete",
                stage="attribution",
                error_stage="prepare",
                retryable=terminal.status != "cancelled",
            )
        if terminal.result.get("yielded"):
            raise PauseAtCheckpoint
        return AttributionRunSummary(
            processed=int(terminal.result.get("processed", 0)),
            created=int(terminal.result.get("created", 0)),
            reused=int(terminal.result.get("reused", 0)),
            non_target=int(terminal.result.get("nonTarget", 0)),
            skipped=int(terminal.result.get("skipped", 0)),
            failed=int(terminal.result.get("failed", 0)),
            average_latency_ms=float(terminal.result.get("averageLatencyMs", 0.0)),
            p95_latency_ms=float(terminal.result.get("p95LatencyMs", 0.0)),
            token_count=int(terminal.result.get("tokenCount", 0)),
            warning_count=int(terminal.result.get("warningCount", 0)),
            evidence_coverage_rate=float(terminal.result.get("evidenceCoverageRate", 0.0)),
            context_hash=(
                str(terminal.result["contextHash"])
                if terminal.result.get("contextHash") is not None
                else None
            ),
        )

    async def submit_scheduled(self, run_id: str) -> JobSubmission:
        """Expose the single scheduler admission seam without duplicating execution."""
        return await self.submit(run_id, created_by=None, source="schedule")

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Execute the frozen run snapshot and persist redacted live observations."""
        run_id = job.payload.get("runId")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("attribution job has no run id")
        run = await self._runs.get_run(run_id)
        if run is None:
            raise LookupError("attribution run not found")
        candidates = await candidate_snapshot(run, self._candidates, self._attributions)

        async def observe(progress: AttributionRunProgress) -> None:
            observation = self._observation(run, progress).model_dump(mode="json", by_alias=True)
            await self._jobs.update_progress(
                job.id,
                progress.completed / progress.total if progress.total else 1.0,
                observation=observation,
            )

        async def before_case() -> None:
            await checkpoint(self._runs, run.id)

        try:
            await before_case()
            summary = await self._runner.run(
                run,
                candidates,
                run.cache_enabled,
                on_progress=observe,
                before_case=before_case,
            )
        except PauseAtCheckpoint:
            return {"runId": run.id, "yielded": True}
        return {
            "processed": summary.processed,
            "created": summary.created,
            "reused": summary.reused,
            "nonTarget": summary.non_target,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "averageLatencyMs": summary.average_latency_ms,
            "p95LatencyMs": summary.p95_latency_ms,
            "tokenCount": summary.token_count,
            "warningCount": summary.warning_count,
            "evidenceCoverageRate": summary.evidence_coverage_rate,
            "executor": run.attribution_engine,
            "skillRevision": (
                f"{run.attribution_skill_key}@r{run.attribution_skill_revision}"
                if run.attribution_skill_key and run.attribution_skill_revision is not None
                else None
            ),
            "contextHash": summary.context_hash,
        }

    async def history(self, run_id: str) -> AttributionJobList:
        """Return the newest durable attempts for one run."""
        return AttributionJobList(
            items=[
                self._view(item)
                for item in await self._jobs.repository.list_for_ref(
                    ATTRIBUTION_JOB_KIND,
                    run_id,
                )
            ],
        )

    def public(self, job: JobRunRecord) -> AttributionJobView:
        """Project one admitted row without exposing its payload."""
        return self._view(job)

    async def cancel(self, run_id: str, job_id: str) -> AttributionJobView:
        """Cancel one attribution job only when it belongs to the requested run."""
        job = await self._owned_job(run_id, job_id)
        return self._view(await self._jobs.cancel(job.id))

    async def retry(self, run_id: str, job_id: str) -> AttributionJobView:
        """Retry only missing cases through the shared cache and candidate pointers."""
        job = await self._owned_job(run_id, job_id)
        await self._admissible_run(run_id, "retry")
        retried = await self._jobs.retry(
            job.id,
            payload={**job.payload, "source": "retry"},
        )
        return self._view(retried)

    async def _owned_job(self, run_id: str, job_id: str) -> JobRunRecord:
        job = await self._jobs.get(job_id)
        if job.kind != ATTRIBUTION_JOB_KIND or job.ref_id != run_id:
            raise AppError(status_code=404, code=ErrorCode.JOB_NOT_FOUND, message="job not found")
        return job

    def _observation(
        self,
        run: EvolutionRunRecord,
        progress: AttributionRunProgress,
    ) -> AttributionJobObservation:
        return AttributionJobObservation(
            **asdict(progress),
            executor=run.attribution_engine,
            skill_revision=(
                f"{run.attribution_skill_key}@r{run.attribution_skill_revision}"
                if run.attribution_skill_key and run.attribution_skill_revision is not None
                else None
            ),
        )

    def _view(
        self,
        job: JobRunRecord,
        *,
        source: AttributionJobSource | None = None,
    ) -> AttributionJobView:
        payload_source = job.payload.get("source")
        resolved_source = source or (
            cast(AttributionJobSource, payload_source)
            if payload_source in {"prepare", "manual", "schedule", "retry"}
            else "prepare"
        )
        result = job.result or {}
        token_count = result.get("tokenCount", 0)
        observation = AttributionJobObservation(
            total=int(result.get("total", result.get("processed", 0))),
            completed=int(
                result.get(
                    "completed",
                    int(result.get("created", 0))
                    + int(result.get("reused", 0))
                    + int(result.get("failed", 0)),
                ),
            ),
            created=int(result.get("created", 0)),
            reused=int(result.get("reused", 0)),
            failed=int(result.get("failed", 0)),
            non_target=int(result.get("nonTarget", 0)),
            average_latency_ms=float(result.get("averageLatencyMs", 0.0)),
            p95_latency_ms=float(result.get("p95LatencyMs", 0.0)),
            token_count=token_count if type(token_count) is int else None,
            warning_count=int(result.get("warningCount", 0)),
            evidence_coverage_rate=float(result.get("evidenceCoverageRate", 0.0)),
            executor=str(result.get("executor", "unknown")),
            skill_revision=(
                str(result["skillRevision"]) if result.get("skillRevision") is not None else None
            ),
            context_hash=(
                str(result["contextHash"]) if result.get("contextHash") is not None else None
            ),
        )
        return AttributionJobView(
            job_id=job.id,
            run_id=job.ref_id or "",
            source=resolved_source,
            status=cast(Any, job.status),
            progress=job.progress,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            cancel_requested=job.cancel_requested,
            observation=observation,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


__all__ = [
    "ATTRIBUTION_JOB_KIND",
    "AttributionJobList",
    "AttributionJobObservation",
    "AttributionJobService",
    "AttributionJobView",
]
