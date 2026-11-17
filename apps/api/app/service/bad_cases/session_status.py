"""Derived trace-readiness for a reported bad case.

A case row is the reported problem; its Session is a separate projection that
can lag behind or never arrive. The read path must keep the case visible and
describe that gap instead of turning it into ``BAD_CASE_NOT_FOUND``. This module
is the single mapping from durable ``bad_case_root_sync`` state plus Session
presence to the public five-state union.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, NoReturn

from app.db.crud.bad_case_sync import BadCaseRootSyncRow
from app.db.crud.bad_cases import BadCaseRow
from app.errors import AppError, ErrorCode


class BadCaseTraceStatus(StrEnum):
    """Public trace state shared by the overview list and detail error body."""

    READY = "ready"
    PENDING = "pending"
    SYNCING = "syncing"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TraceStatus:
    """One case's derived trace state plus the facts the UI needs to explain it."""

    status: BadCaseTraceStatus
    session_ready: bool
    last_error: str | None
    retryable: bool
    next_retry_at: datetime | None
    last_attempt_at: datetime | None


def classify_trace_status(
    sync_state: BadCaseRootSyncRow | None,
    *,
    session_ready: bool,
) -> TraceStatus:
    """Map durable sync state and Session presence to the public union.

    Session presence wins: once the normalized root exists the case is readable
    even if an older sync row still says ``failed``. A missing Session with a
    deterministic failure is ``unavailable``, not ``failed``, because retrying
    cannot change the outcome until the source configuration changes.
    """
    if session_ready:
        return TraceStatus(
            status=BadCaseTraceStatus.READY,
            session_ready=True,
            last_error=None,
            retryable=False,
            next_retry_at=None,
            last_attempt_at=None,
        )
    if sync_state is None:
        return TraceStatus(
            status=BadCaseTraceStatus.PENDING,
            session_ready=False,
            last_error=None,
            retryable=True,
            next_retry_at=None,
            last_attempt_at=None,
        )
    last_attempt_at = sync_state.started_at or sync_state.updated_at
    if sync_state.status == "pending":
        return TraceStatus(
            status=BadCaseTraceStatus.PENDING,
            session_ready=False,
            last_error=sync_state.last_error,
            retryable=True,
            next_retry_at=sync_state.next_retry_at,
            last_attempt_at=None,
        )
    if sync_state.status == "syncing":
        return TraceStatus(
            status=BadCaseTraceStatus.SYNCING,
            session_ready=False,
            last_error=sync_state.last_error,
            retryable=True,
            next_retry_at=sync_state.next_retry_at,
            last_attempt_at=last_attempt_at,
        )
    if sync_state.status == "failed" and not sync_state.deterministic_failure:
        return TraceStatus(
            status=BadCaseTraceStatus.FAILED,
            session_ready=False,
            last_error=sync_state.last_error,
            retryable=True,
            next_retry_at=sync_state.next_retry_at,
            last_attempt_at=last_attempt_at,
        )
    # Deterministic failure, or a synced root whose normalized Session is gone:
    # both are "no usable trace" until a source change re-triggers the sync.
    return TraceStatus(
        status=BadCaseTraceStatus.UNAVAILABLE,
        session_ready=False,
        last_error=sync_state.last_error,
        retryable=False,
        next_retry_at=None,
        last_attempt_at=last_attempt_at,
    )


def trace_status_details(case: BadCaseRow, trace: TraceStatus) -> dict[str, Any]:
    """Build the structured detail payload for a case whose trace is not ready."""
    return {
        "badCaseId": case.bad_case_id,
        "sessionId": case.bad_case_session_id,
        "title": case.title,
        "objectName": case.object_name,
        "createdAt": case.created_at.isoformat(),
        "sessionReady": trace.session_ready,
        "syncStatus": trace.status.value,
        "lastError": trace.last_error,
        "retryable": trace.retryable,
        "nextRetryAt": (
            trace.next_retry_at.isoformat() if trace.next_retry_at is not None else None
        ),
        "lastAttemptAt": (
            trace.last_attempt_at.isoformat() if trace.last_attempt_at is not None else None
        ),
    }


def raise_trace_not_ready(case: BadCaseRow, trace: TraceStatus) -> NoReturn:
    """Raise the stable error that distinguishes "not yet" from "not found"."""
    details = trace_status_details(case, trace)
    if trace.status in (BadCaseTraceStatus.PENDING, BadCaseTraceStatus.SYNCING):
        raise AppError(
            status_code=409,
            code=ErrorCode.BAD_CASE_SESSION_PENDING,
            message="bad case session is not ready yet",
            details=details,
        )
    raise AppError(
        status_code=503,
        code=ErrorCode.BAD_CASE_SESSION_UNAVAILABLE,
        message="bad case session is not available",
        details=details,
    )
