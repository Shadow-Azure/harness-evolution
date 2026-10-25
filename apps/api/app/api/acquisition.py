"""Authenticated acquisition status and administrator sync trigger."""

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Request, Response, Security

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.acquisition.sync import SyncCoordinator, SyncStatus, SyncTriggerResult
from app.service.identity.schemas import IdentityModel

router = APIRouter(prefix="/api/acquisition", tags=["acquisition"])


class SyncStatusError(IdentityModel):
    """Sanitized issue summary retained from the latest replay batch."""

    session_id: str | None = None
    agent_id: str | None = None
    line_no: int | None = None
    code: str
    message: str


class AcquisitionStatusResponse(IdentityModel):
    """Current acquisition counts and durable latest-run metadata."""

    active_job_id: str | None
    status: Literal["idle", "queued", "running", "completed", "failed", "interrupted"]
    payload_table: str = "trajectory_payloads"
    pending: int
    processed: int
    imported: int
    skipped: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    errors: list[SyncStatusError]


class SyncTriggerResponse(IdentityModel):
    """Queued/reused job identity, or an explicit successful no-work result."""

    job_id: str | None
    status: Literal["queued", "reused", "idle"]
    reused: bool


def sync_from(request: Request) -> SyncCoordinator:
    """Return the application-scoped acquisition coordinator."""
    return cast(SyncCoordinator, request.app.state.sync)


def _status_response(status: SyncStatus) -> AcquisitionStatusResponse:
    errors: list[SyncStatusError] = []
    for issue in status.errors:
        code = issue.get("code")
        message = issue.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            continue
        line_no = issue.get("lineNo")
        errors.append(
            SyncStatusError(
                session_id=_optional_str(issue.get("sessionId")),
                agent_id=_optional_str(issue.get("agentId")),
                line_no=int(line_no) if isinstance(line_no, int) else None,
                code=code,
                message=message,
            ),
        )
    return AcquisitionStatusResponse(
        active_job_id=status.active_job_id,
        status=cast(
            Literal["idle", "queued", "running", "completed", "failed", "interrupted"],
            status.status,
        ),
        pending=status.pending,
        processed=status.processed,
        imported=status.imported,
        skipped=status.skipped,
        last_run_at=status.last_run_at,
        next_run_at=status.next_run_at,
        errors=errors,
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _trigger_response(result: SyncTriggerResult) -> SyncTriggerResponse:
    return SyncTriggerResponse(
        job_id=result.job_id,
        status=result.status,
        reused=result.reused,
    )


@router.get(
    "/status",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
    },
)
async def acquisition_status(request: Request) -> AcquisitionStatusResponse:
    """Return durable acquisition progress for all authenticated users."""
    return _status_response(await sync_from(request).status())


@router.post(
    "/sync",
    status_code=202,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        200: {
            "model": SyncTriggerResponse,
            "description": "No pending payloads; no job was created",
        },
        202: {
            "model": SyncTriggerResponse,
            "description": "A sync job was queued or an active job was reused",
        },
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Admin role is required"},
    },
)
async def trigger_sync(request: Request, response: Response) -> SyncTriggerResponse:
    """Queue one administrator-triggered sync or return explicit no-work."""
    principal = request.state.principal
    result = await sync_from(request).trigger(
        "manual",
        created_by=principal.user_id,
    )
    if result.status == "idle":
        response.status_code = 200
    return _trigger_response(result)
