"""Authenticated evolution run list, launch, and seven-step step endpoints."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request, Security, status

from app.api.deps import authorize_workspace, visible_workspace_ids
from app.api.evolution_launch import LAUNCH_RESPONSES
from app.api.security import BEARER_AUTH
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.evolution.attribution_jobs import (
    AttributionJobList,
    AttributionJobService,
    AttributionJobView,
)
from app.service.evolution.events import (
    EvolutionRunEventLevel,
    EvolutionRunEventPage,
    EvolutionRunEventService,
)
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.probe_query import ProbeQueryRequest, RunAccepted
from app.service.evolution.retry import (
    EvolutionRetryAccepted,
    EvolutionRetryService,
)
from app.service.evolution.runs import (
    EvolutionRunDetail,
    EvolutionRunList,
    EvolutionRunService,
)
from app.service.evolution.stages import (
    EvolutionStageService,
    EvolutionStepAttribution,
    EvolutionStepClusters,
    EvolutionStepFinal,
    EvolutionStepIteration,
    EvolutionStepPotential,
    EvolutionStepRange,
    EvolutionStepSessions,
)
from app.service.evolution.targets import EvolutionTargetService
from app.service.identity.principals import Principal

router = APIRouter(prefix="/api/evolution/runs", tags=["evolution-runs"])


def runs_from(request: Request) -> EvolutionRunService:
    """Return the application-scoped evolution run service."""
    return cast(EvolutionRunService, request.app.state.evolution_runs)


def launch_from(request: Request) -> EvolutionLaunchService:
    """Return the application-scoped launch service."""
    return cast(EvolutionLaunchService, request.app.state.evolution_launch)


def stages_from(request: Request) -> EvolutionStageService:
    """Return the application-scoped six-step stage service."""
    return cast(EvolutionStageService, request.app.state.evolution_stages)


def events_from(request: Request) -> EvolutionRunEventService:
    """Return the application-scoped evolution event service."""
    return cast(EvolutionRunEventService, request.app.state.evolution_events)


def attribution_jobs_from(request: Request) -> AttributionJobService:
    """Return the application-scoped isolated attribution job service."""
    return cast(AttributionJobService, request.app.state.attribution_jobs)


def retry_from(request: Request) -> EvolutionRetryService:
    """Return the application-scoped blocked-run retry service."""
    return cast(EvolutionRetryService, request.app.state.evolution_retry)


def targets_from(request: Request) -> EvolutionTargetService:
    """Return the application-scoped target configuration service."""
    return cast(EvolutionTargetService, request.app.state.evolution_targets)


def _principal_id(request: Request) -> str | None:
    """Return the authenticated principal's user id."""
    return cast(Principal, request.state.principal).user_id


async def _run_workspace(request: Request, run_id: str) -> str:
    """Return the owning workspace of one run or the shared not-found error."""
    repository = request.app.state.evolution_repository
    run = await repository.get_run(run_id)
    if run is None:
        raise AppError(
            status_code=404,
            code=ErrorCode.RUN_NOT_FOUND,
            message="evolution run not found",
        )
    return cast(str, run.workspace_id)


STEP_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: LAUNCH_RESPONSES[401],
    403: LAUNCH_RESPONSES[403],
    404: {
        "model": ErrorResponse,
        "description": "Run is unknown or the step has not been reached",
    },
}


@router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
    },
)
async def list_runs(request: Request) -> EvolutionRunList:
    """Return backend-ordered running and history groups in visible spaces."""
    return await runs_from(request).list(
        workspace_ids=await visible_workspace_ids(request),
    )


@router.get(
    "/{run_id}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Run is unknown"},
    },
)
async def read_run(run_id: str, request: Request) -> EvolutionRunDetail:
    """Return one visible run shell with its backend-owned step states."""
    detail = await runs_from(request).detail(
        run_id,
        workspace_ids=await visible_workspace_ids(request),
    )
    if detail is None:
        raise AppError(
            status_code=404,
            code=ErrorCode.RUN_NOT_FOUND,
            message="evolution run not found",
        )
    return detail


@router.get(
    "/{run_id}/events",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Run is unknown"},
    },
)
async def read_run_events(
    run_id: str,
    request: Request,
    after_seq: Annotated[int, Query(alias="afterSeq", ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    level: Annotated[EvolutionRunEventLevel | None, Query()] = None,
) -> EvolutionRunEventPage:
    """Return one stable, authenticated page of durable run events."""
    return await events_from(request).list(
        run_id,
        after_seq=after_seq,
        limit=limit,
        level=level,
        workspace_ids=await visible_workspace_ids(request),
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **LAUNCH_RESPONSES,
        202: {"model": RunAccepted, "description": "Full run accepted"},
    },
)
async def create_run(
    body: ProbeQueryRequest,
    request: Request,
) -> RunAccepted:
    """Admit one full evolution run for a target in a visible space."""
    scope = await visible_workspace_ids(request)
    config = await targets_from(request).enabled_config(
        body.target_type,
        body.target_name,
        workspace_ids=scope,
    )
    await authorize_workspace(request, config.workspace_id, "space_admin")
    return await launch_from(request).request_run(
        body,
        expected_mode="full",
        created_by=_principal_id(request),
        workspace_ids=(config.workspace_id,),
    )


@router.post(
    "/{run_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: LAUNCH_RESPONSES[401],
        403: LAUNCH_RESPONSES[403],
        404: {"model": ErrorResponse, "description": "Run is unknown"},
        409: {
            "model": ErrorResponse,
            "description": "Run is not blocked or another stage job is active",
        },
        202: {
            "model": EvolutionRetryAccepted,
            "description": "Blocked-run retry accepted",
        },
    },
)
async def retry_run(run_id: str, request: Request) -> EvolutionRetryAccepted:
    """Admit one manual retry for a blocked run in a visible space."""
    scope = await visible_workspace_ids(request)
    run = await runs_from(request).detail(run_id, workspace_ids=scope)
    if run is None:
        raise AppError(
            status_code=404,
            code=ErrorCode.RUN_NOT_FOUND,
            message="evolution run not found",
        )
    workspace_id = await _run_workspace(request, run_id)
    await authorize_workspace(request, workspace_id, "space_admin")
    return await retry_from(request).request_retry(
        run_id,
        created_by=_principal_id(request),
        workspace_ids=scope,
    )


@router.get(
    "/{run_id}/attribution-jobs",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def list_attribution_jobs(run_id: str, request: Request) -> AttributionJobList:
    """Return sanitized attribution throughput and failure observations."""
    workspace_id = await _run_workspace(request, run_id)
    await authorize_workspace(request, workspace_id, "viewer")
    return await attribution_jobs_from(request).history(run_id)


@router.post(
    "/{run_id}/attribution-jobs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def create_attribution_job(run_id: str, request: Request) -> AttributionJobView:
    """Start or join the run's manual attribution batch."""
    workspace_id = await _run_workspace(request, run_id)
    await authorize_workspace(request, workspace_id, "space_admin")
    submission = await attribution_jobs_from(request).submit(
        run_id,
        created_by=_principal_id(request),
        source="manual",
    )
    return attribution_jobs_from(request).public(submission.job)


@router.post(
    "/{run_id}/attribution-jobs/{job_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def retry_attribution_job(
    run_id: str,
    job_id: str,
    request: Request,
) -> AttributionJobView:
    """Retry only cases that still lack a durable report link."""
    workspace_id = await _run_workspace(request, run_id)
    await authorize_workspace(request, workspace_id, "space_admin")
    return await attribution_jobs_from(request).retry(run_id, job_id)


@router.post(
    "/{run_id}/attribution-jobs/{job_id}/cancel",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def cancel_attribution_job(
    run_id: str,
    job_id: str,
    request: Request,
) -> AttributionJobView:
    """Cancel queued or running attribution work without deleting its audit row."""
    workspace_id = await _run_workspace(request, run_id)
    await authorize_workspace(request, workspace_id, "space_admin")
    return await attribution_jobs_from(request).cancel(run_id, job_id)


@router.get(
    "/{run_id}/steps/range",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_range_step(run_id: str, request: Request) -> EvolutionStepRange:
    """Return the backend-owned selection snapshot of one run."""
    return cast(
        EvolutionStepRange,
        await stages_from(request).step(
            run_id, "range", workspace_ids=await visible_workspace_ids(request)
        ),
    )


@router.get(
    "/{run_id}/steps/sessions",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_sessions_step(
    run_id: str,
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=50)] = 4,
) -> EvolutionStepSessions:
    """Return one page of associated Sessions for one run."""
    return cast(
        EvolutionStepSessions,
        await stages_from(request).step(
            run_id,
            "sessions",
            workspace_ids=await visible_workspace_ids(request),
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{run_id}/steps/potential",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_potential_step(
    run_id: str,
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=50)] = 5,
) -> EvolutionStepPotential:
    """Return one page of potential bad cases for one run."""
    return cast(
        EvolutionStepPotential,
        await stages_from(request).step(
            run_id,
            "potential",
            workspace_ids=await visible_workspace_ids(request),
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{run_id}/steps/attribution",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_attribution_step(run_id: str, request: Request) -> EvolutionStepAttribution:
    """Return the backend-owned attribution projection of one run."""
    return cast(
        EvolutionStepAttribution,
        await stages_from(request).step(
            run_id, "attribution", workspace_ids=await visible_workspace_ids(request)
        ),
    )


@router.get(
    "/{run_id}/steps/clusters",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_clusters_step(run_id: str, request: Request) -> EvolutionStepClusters:
    """Return the backend-owned cluster projection of one run."""
    return cast(
        EvolutionStepClusters,
        await stages_from(request).step(
            run_id, "clusters", workspace_ids=await visible_workspace_ids(request)
        ),
    )


@router.get(
    "/{run_id}/steps/iteration",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_iteration_step(run_id: str, request: Request) -> EvolutionStepIteration:
    """Return the backend-owned iteration projection of one run."""
    return cast(
        EvolutionStepIteration,
        await stages_from(request).step(
            run_id, "iteration", workspace_ids=await visible_workspace_ids(request)
        ),
    )


@router.get(
    "/{run_id}/steps/final",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_final_step(run_id: str, request: Request) -> EvolutionStepFinal:
    """Return the backend-owned final evaluation projection of one run."""
    return cast(
        EvolutionStepFinal,
        await stages_from(request).step(
            run_id, "final", workspace_ids=await visible_workspace_ids(request)
        ),
    )
