"""Authenticated acquisition status and administrator sync trigger."""

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Request, Response, Security

from app.api.security import BEARER_AUTH
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.acquisition.sync import SyncCoordinator, SyncStatus, SyncTriggerResult
from app.service.acquisition.upstream_pull import PullJobPayload, UpstreamPullService
from app.service.identity.schemas import IdentityModel

router = APIRouter(prefix="/api/acquisition", tags=["acquisition"])

_SYNC_ERROR_MESSAGES: dict[str, str] = {
    "INVALID_JSONL_LINE": "JSONL line could not be parsed",
    "INVALID_TRANSCRIPT_RECORD": "Transcript record was invalid",
    "MISSING_USER_TURN_TIMESTAMP": "User turn timestamp was missing",
    "MISSING_PARENT_TOOL_USE_ID": "Parent tool use id was missing",
    "AMBIGUOUS_PARENT_TOOL_USE_ID": "Parent tool use id was ambiguous",
    "MISSING_MAIN_AGENT": "Main Agent was missing",
    "MISSING_FORKED_SKILL_PARENT": "Forked skill parent was missing",
    "AMBIGUOUS_WORKFLOW_PARENT": "Workflow parent was ambiguous",
    "MISSING_SESSION_TIMESTAMP": "Session timestamp was missing",
    "INVALID_ROOT_SESSION_ID": "Root session id was invalid",
    "MISSING_PAYLOAD_SOURCE": "Source payload was missing",
    "SYNC_PROGRESS_FAILED": "Sync progress reporting failed",
    "SYNC_JOB_FAILED": "Sync job failed",
    "SYNC_JOB_INTERRUPTED": "Sync job was interrupted",
    "UPSTREAM_REQUEST_FAILED": "Upstream trajectory request failed",
    "UPSTREAM_INVALID_RESPONSE": "Upstream trajectory response was invalid",
    "UPSTREAM_VERSION_INCOMPATIBLE": "Upstream trajectory API version is incompatible",
}


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


class PullResponse(IdentityModel):
    """Queued pull job identity."""

    job_id: str


def sync_from(request: Request) -> SyncCoordinator:
    """Return the application-scoped acquisition coordinator."""
    return cast(SyncCoordinator, request.app.state.sync)


def pull_from(request: Request) -> UpstreamPullService:
    """Return the application-scoped upstream pull service."""
    return cast(UpstreamPullService, request.app.state.upstream_pull)


def _status_response(status: SyncStatus) -> AcquisitionStatusResponse:
    errors: list[SyncStatusError] = []
    for issue in status.errors:
        code = issue.get("code")
        if not isinstance(code, str):
            continue
        safe_code = code if code in _SYNC_ERROR_MESSAGES else "SYNC_ISSUE"
        line_no = issue.get("lineNo")
        errors.append(
            SyncStatusError(
                session_id=_optional_str(issue.get("sessionId")),
                agent_id=_optional_str(issue.get("agentId")),
                line_no=int(line_no) if isinstance(line_no, int) else None,
                code=safe_code,
                message=_SYNC_ERROR_MESSAGES.get(safe_code, "Sync issue was reported"),
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


@router.post(
    "/pull",
    status_code=202,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Admin role is required"},
        409: {"model": ErrorResponse, "description": "Upstream is not configured"},
        422: {"model": ErrorResponse, "description": "Selector validation failed"},
    },
)
async def trigger_pull(request: Request, body: PullJobPayload) -> PullResponse:
    """Queue one administrator pull from the configured upstream source."""
    pull = pull_from(request)
    if not pull.available:
        raise AppError(
            status_code=409,
            code=ErrorCode.UPSTREAM_NOT_AVAILABLE,
            message="upstream trajectory query is not configured",
        )
    payload = body
    principal = request.state.principal
    submitted = await request.app.state.jobs.submit(
        kind="pull",
        payload=payload.model_dump(by_alias=True, mode="json"),
        ref_id=None,
        created_by=principal.user_id,
    )
    return PullResponse(job_id=submitted.job.id)
