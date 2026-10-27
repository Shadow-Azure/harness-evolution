"""Durable evolution event recording, pagination, and topic authorization."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Protocol, cast

from app.db.models.evolution import EvolutionRunRecord
from app.db.models.run_events import RunEventPageRecord, RunEventRecord
from app.errors import AppError, ErrorCode
from app.service.events import EventBus
from app.service.identity.schemas import IdentityModel
from app.utils.redaction import (
    sanitize_detail,
    sanitize_message,
    sanitize_value,
)

EvolutionRunEventType = Literal[
    "run_created",
    "prepare_started",
    "workspace_prepared",
    "clusters_created",
    "step_advanced",
    "run_blocked",
    "run_resumed",
    "final_completed",
    "run_failed",
    "run_interrupted",
    "candidate_committed",
    "candidate_pushed",
    "eval_submitted",
    "eval_polled",
    "eval_completed",
    "eval_failed",
    "eval_timeout",
    "cluster_accepted",
    "cluster_rejected",
    "push_started",
    "push_retry_scheduled",
    "push_succeeded",
    "push_failed",
]
EvolutionRunEventLevel = Literal["info", "warn", "error"]
EvolutionRunEventStage = Literal[
    "prepare",
    "cluster",
    "step",
    "candidate",
    "push",
    "eval",
    "apply",
    "final",
]

EVOLUTION_RUN_EVENT_TYPES: tuple[EvolutionRunEventType, ...] = (
    "run_created",
    "prepare_started",
    "workspace_prepared",
    "clusters_created",
    "step_advanced",
    "run_blocked",
    "run_resumed",
    "final_completed",
    "run_failed",
    "run_interrupted",
    "candidate_committed",
    "candidate_pushed",
    "eval_submitted",
    "eval_polled",
    "eval_completed",
    "eval_failed",
    "eval_timeout",
    "cluster_accepted",
    "cluster_rejected",
    "push_started",
    "push_retry_scheduled",
    "push_succeeded",
    "push_failed",
)
EVOLUTION_RUN_EVENT_LEVELS: tuple[EvolutionRunEventLevel, ...] = ("info", "warn", "error")
EVOLUTION_RUN_EVENT_STAGES: tuple[EvolutionRunEventStage, ...] = (
    "prepare",
    "cluster",
    "step",
    "candidate",
    "push",
    "eval",
    "apply",
    "final",
)
_ACTIVE_SSE_STATUSES = frozenset({"preparing", "running"})


class EvolutionRunEventError(IdentityModel):
    """Sanitized error detail attached to one persisted run event."""

    type: str | None
    message: str | None
    detail: str | None


class EvolutionRunEvent(IdentityModel):
    """One complete event object shared by REST and SSE."""

    seq: int
    event_type: EvolutionRunEventType
    level: EvolutionRunEventLevel
    stage: EvolutionRunEventStage
    step_index: int | None
    cluster_id: str | None
    round_id: str | None
    job_id: str | None
    message: str
    created_at: datetime
    payload: dict[str, Any] | None
    error: EvolutionRunEventError | None


class EvolutionRunEventPage(IdentityModel):
    """One stable run-event page for REST replay and UI pagination."""

    items: list[EvolutionRunEvent]
    next_seq: int
    has_more: bool


class EvolutionRunEventStore(Protocol):
    """Storage seam consumed by the evolution event service."""

    async def append(
        self,
        *,
        run_id: str,
        event_type: str,
        level: str,
        stage: str,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_detail: str | None = None,
    ) -> RunEventRecord:
        """Append one event and return its durable sequence."""

    async def read_page(
        self,
        run_id: str,
        *,
        after_seq: int,
        limit: int,
        level: str | None,
    ) -> RunEventPageRecord:
        """Return one stable event page."""

    async def max_seq(self, run_id: str) -> int:
        """Return the run's latest sequence."""

    async def record_interrupted(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        job_id: str,
    ) -> int | None:
        """Persist one interruption for the M1 recorder protocol."""


class EvolutionRunStateWriter(Protocol):
    """Run state mutations needed at the job failure boundary."""

    async def get_run(self, run_id: str) -> EvolutionRunRecord | None:
        """Return one persisted run or None."""

    async def mark_failed(self, run_id: str, *, stage: str, message: str) -> None:
        """Persist terminal failure facts."""

    async def mark_interrupted(self, run_id: str, *, stage: str, message: str) -> None:
        """Persist interrupted facts."""

    async def mark_blocked(
        self,
        run_id: str,
        *,
        stage: str,
        message: str,
        next_retry_at: datetime | None = None,
    ) -> None:
        """Persist retryable blocked facts."""

    async def mark_resumed(self, run_id: str) -> None:
        """Clear blocked state after a successful retry."""


class EvolutionRunEventService:
    """Coordinate sanitized append, run state, REST replay, and live notification."""

    def __init__(
        self,
        store: EvolutionRunEventStore,
        runs: EvolutionRunStateWriter,
        bus: EventBus,
    ) -> None:
        """Bind durable history, run state, and transient notification."""
        self._store = store
        self._runs = runs
        self._bus = bus

    async def record(
        self,
        run_id: str,
        event_type: EvolutionRunEventType,
        *,
        level: EvolutionRunEventLevel,
        stage: EvolutionRunEventStage,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_detail: str | None = None,
    ) -> EvolutionRunEvent:
        """Sanitize and append one event before publishing its durable sequence."""
        if event_type not in EVOLUTION_RUN_EVENT_TYPES:
            raise ValueError(f"unknown evolution event type: {event_type}")
        if level not in EVOLUTION_RUN_EVENT_LEVELS:
            raise ValueError(f"unknown evolution event level: {level}")
        if stage not in EVOLUTION_RUN_EVENT_STAGES:
            raise ValueError(f"unknown evolution event stage: {stage}")
        if step_index is not None and not 0 <= step_index <= 5:
            raise ValueError("step_index must be between 0 and 5")

        resolved_type = error_type or (type(error).__name__ if error is not None else None)
        resolved_message = error_message or (str(error) if error is not None else None)
        resolved_detail = error_detail
        if resolved_detail is None and error is not None:
            resolved_detail = str(error)
        sanitized_payload = sanitize_value(dict(payload)) if payload is not None else None
        sanitized_error_message = (
            sanitize_message(resolved_message, limit=2_000)
            if resolved_message is not None
            else None
        )
        record = await self._store.append(
            run_id=run_id,
            event_type=event_type,
            level=level,
            stage=stage,
            message=sanitize_message(message),
            step_index=step_index,
            cluster_id=cluster_id,
            round_id=round_id,
            job_id=job_id,
            payload=(
                cast(dict[str, Any], sanitized_payload) if sanitized_payload is not None else None
            ),
            error_type=(
                sanitize_message(resolved_type, limit=128) if resolved_type is not None else None
            ),
            error_message=sanitized_error_message,
            error_detail=sanitize_detail(resolved_detail),
        )
        event = _public_event(record)
        self._bus.publish(
            f"run:{run_id}",
            "run.event",
            event.model_dump(mode="json", by_alias=True),
            event_id=event.seq,
        )
        return event

    async def list(
        self,
        run_id: str,
        *,
        after_seq: int,
        limit: int,
        level: EvolutionRunEventLevel | None,
    ) -> EvolutionRunEventPage:
        """Return one authenticated run's durable event page."""
        run = await self._runs.get_run(run_id)
        if run is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.RUN_NOT_FOUND,
                message="evolution run not found",
            )
        page = await self._store.read_page(
            run_id,
            after_seq=after_seq,
            limit=limit,
            level=level,
        )
        items = [_public_event(item) for item in page.items]
        return EvolutionRunEventPage(
            items=items,
            next_seq=items[-1].seq if items else after_seq,
            has_more=page.has_more,
        )

    async def record_failed(
        self,
        run_id: str,
        *,
        stage: EvolutionRunEventStage,
        message: str,
        job_id: str,
        error: BaseException,
        error_detail: str | None = None,
    ) -> int:
        """Persist one terminal failure event and update the run boundary."""
        event = await self.record(
            run_id,
            "run_failed",
            level="error",
            stage=stage,
            message=message,
            job_id=job_id,
            error=error,
            error_detail=error_detail,
        )
        await self._runs.mark_failed(
            run_id,
            stage=stage,
            message=sanitize_message(str(error), limit=2_000),
        )
        return event.seq

    async def record_interrupted(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        job_id: str,
    ) -> int:
        """Persist one interruption and update the run's terminal state."""
        if stage not in EVOLUTION_RUN_EVENT_STAGES:
            raise ValueError(f"unknown evolution event stage: {stage}")
        event = await self.record(
            run_id,
            "run_interrupted",
            level="error",
            stage=stage,
            message=message,
            job_id=job_id,
            error_type="ProcessInterrupted",
            error_message=message,
        )
        await self._runs.mark_interrupted(run_id, stage=stage, message=message)
        return event.seq

    async def record_blocked(
        self,
        run_id: str,
        *,
        stage: EvolutionRunEventStage,
        blocked_stage: Literal["patch", "push", "eval"] | None = None,
        message: str,
        job_id: str | None = None,
        next_retry_at: datetime | None = None,
        error: BaseException | None = None,
    ) -> int:
        """Persist one retryable failure and enter blocked state."""
        resolved_blocked_stage = blocked_stage or (stage if stage in {"push", "eval"} else None)
        if resolved_blocked_stage is None:
            raise ValueError("blocked events require patch, push, or eval stage")
        event = await self.record(
            run_id,
            "run_blocked",
            level="warn",
            stage=stage,
            message=message,
            job_id=job_id,
            error=error,
        )
        await self._runs.mark_blocked(
            run_id,
            stage=resolved_blocked_stage,
            message=sanitize_message(message, limit=2_000),
            next_retry_at=next_retry_at,
        )
        return event.seq

    async def record_resumed(
        self,
        run_id: str,
        *,
        stage: EvolutionRunEventStage,
        job_id: str | None = None,
    ) -> int:
        """Persist a successful retry handoff and clear blocked state."""
        event = await self.record(
            run_id,
            "run_resumed",
            level="info",
            stage=stage,
            message="运行已恢复",
            job_id=job_id,
        )
        await self._runs.mark_resumed(run_id)
        return event.seq


class EvolutionRunTopicAuthorizer:
    """Authorize SSE subscriptions for one existing active run."""

    def __init__(self, runs: EvolutionRunStateWriter) -> None:
        """Bind the authorizer to the durable run repository."""
        self._runs = runs

    async def authorize(self, topics: tuple[str, ...], *, user_id: str) -> None:
        """Reject missing, terminal, or malformed topics with the stable ticket error."""
        del user_id
        for topic in topics:
            run_id = topic.removeprefix("run:")
            if not topic.startswith("run:") or not run_id:
                raise _ticket_error()
            run = await self._runs.get_run(run_id)
            if run is None or run.status not in _ACTIVE_SSE_STATUSES:
                raise _ticket_error()


def _public_event(record: RunEventRecord) -> EvolutionRunEvent:
    """Map one storage record to the shared camelCase contract."""
    error = (
        EvolutionRunEventError(
            type=record.error_type,
            message=record.error_message,
            detail=record.error_detail,
        )
        if record.error_type or record.error_message or record.error_detail
        else None
    )
    return EvolutionRunEvent(
        seq=record.seq,
        event_type=cast(EvolutionRunEventType, record.event_type),
        level=cast(EvolutionRunEventLevel, record.level),
        stage=cast(EvolutionRunEventStage, record.stage),
        step_index=record.step_index,
        cluster_id=record.cluster_id,
        round_id=record.round_id,
        job_id=record.job_id,
        message=record.message,
        created_at=record.created_at,
        payload=record.payload,
        error=error,
    )


def _ticket_error() -> AppError:
    """Build the non-enumerating error used for unavailable run topics."""
    return AppError(
        status_code=401,
        code=ErrorCode.TICKET_INVALID,
        message="run topic is not available",
    )
