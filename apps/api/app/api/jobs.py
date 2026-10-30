"""Read-only HTTP status adapter for durable jobs."""

from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Path, Request, Security
from pydantic import Field

from app.api.security import BEARER_AUTH
from app.db.models.jobs import JobRunRecord
from app.errors import ErrorResponse
from app.service.identity.schemas import IdentityModel

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
JobKind = Literal[
    "sync",
    "pull",
    "bad_case_root_sync",
    "evolution_prepare",
    "evolution_advance",
    "evolution_apply",
    "evolution_finalize",
    "evolution_retry",
]
JobStatus = Literal["queued", "running", "completed", "failed", "interrupted"]


class JobResponse(IdentityModel):
    """Durable job state returned as the REST source of truth."""

    job_id: str
    kind: JobKind
    ref_id: str | None
    status: JobStatus
    progress: float = Field(ge=0, le=1)
    attempt: int = Field(ge=0)
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


def _job_response(job: JobRunRecord) -> JobResponse:
    return JobResponse(
        job_id=job.id,
        kind=cast(JobKind, job.kind),
        ref_id=job.ref_id,
        status=cast(JobStatus, job.status),
        progress=job.progress,
        attempt=job.attempt,
        created_by=job.created_by,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
    )


@router.get(
    "/{jobId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Job does not exist"},
    },
)
async def get_job(
    job_id: Annotated[str, Path(alias="jobId")],
    request: Request,
) -> JobResponse:
    """Return the latest durable state for one job."""
    runner = request.app.state.jobs
    return _job_response(await runner.get(job_id))
