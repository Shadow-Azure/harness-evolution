"""Workspace-scoped evolution targets, runs, steps, events, and catalogs."""

from datetime import date
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Security, status

from app.api.deps import require_workspace_role
from app.api.evolution_launch import LAUNCH_RESPONSES
from app.api.security import BEARER_AUTH
from app.db.crud.candidate_sources import CandidateSourcesRepository
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.crud.potential import window_day_boundaries
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.catalogs import CatalogModels, CatalogService, CatalogTargets
from app.service.evolution.attribution_jobs import (
    AttributionJobList,
    AttributionJobService,
    AttributionJobView,
)
from app.service.evolution.candidate_policy import (
    CandidatePolicy,
    ReportType,
    SourceCount,
    SourceKind,
    SourceReportPage,
)
from app.service.evolution.control import EvolutionControlService, EvolutionRunControl
from app.service.evolution.events import (
    EvolutionRunEventLevel,
    EvolutionRunEventPage,
    EvolutionRunEventService,
)
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.potential import (
    AttributionPreviewRequest,
    AttributionPreviewResult,
    PotentialPreviewRequest,
    PotentialPreviewResult,
    PotentialPreviewService,
    SessionPreviewResult,
    SessionsPreviewRequest,
    resolve_window,
)
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
    EvolutionStep,
    StepKey,
)
from app.service.evolution.targets import (
    EvolutionTarget,
    EvolutionTargetList,
    EvolutionTargetService,
    EvolutionTargetVersions,
    EvolutionTargetWrite,
)
from app.service.identity.principals import Principal
from app.service.workspaces.service import WorkspaceAccess

router = APIRouter(
    prefix="/api/workspaces/{wid}/evolution",
    tags=["workspace-evolution"],
)
catalog_router = APIRouter(
    prefix="/api/workspaces/{wid}/catalogs",
    tags=["workspace-catalogs"],
)

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]
TargetId = Annotated[str, Path(min_length=1, max_length=36)]
RunId = Annotated[str, Path(min_length=1, max_length=36)]
ViewerAccess = Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))]
AdminAccess = Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))]

STEP_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: LAUNCH_RESPONSES[401],
    403: LAUNCH_RESPONSES[403],
    404: {
        "model": ErrorResponse,
        "description": "Run is unknown, out of workspace, or step not reached",
    },
}

PREVIEW_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: LAUNCH_RESPONSES[401],
    403: LAUNCH_RESPONSES[403],
    404: {
        "model": ErrorResponse,
        "description": "Workspace is unknown or invisible to the caller",
    },
    409: {
        "model": ErrorResponse,
        "description": "Target is not configured, or no Session/potential matched",
    },
    422: {
        "model": ErrorResponse,
        "description": "Window, policy, version, or engine is invalid",
    },
}


def targets_from(request: Request) -> EvolutionTargetService:
    """Return the application-scoped target configuration service."""
    return cast(EvolutionTargetService, request.app.state.evolution_targets)


def runs_from(request: Request) -> EvolutionRunService:
    """Return the application-scoped evolution run service."""
    return cast(EvolutionRunService, request.app.state.evolution_runs)


def launch_from(request: Request) -> EvolutionLaunchService:
    """Return the application-scoped launch service."""
    return cast(EvolutionLaunchService, request.app.state.evolution_launch)


def preview_from(request: Request) -> PotentialPreviewService:
    """Return the application-scoped read-only preview service."""
    return cast(PotentialPreviewService, request.app.state.potential_preview)


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


def catalogs_from(request: Request) -> CatalogService:
    """Return the application-scoped catalog service."""
    return cast(CatalogService, request.app.state.catalogs)


def _principal_id(request: Request) -> str:
    """Return the authenticated principal's user id."""
    return cast(Principal, request.state.principal).user_id


@router.get(
    "/targets",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def list_targets(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
) -> EvolutionTargetList:
    """Return every configured target in this workspace."""
    del access
    return await targets_from(request).list(workspace_ids=(wid,))


@router.post(
    "/targets",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Space administrator is required"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        409: {"model": ErrorResponse, "description": "Object pair already exists"},
        422: {"model": ErrorResponse, "description": "Target configuration is invalid"},
    },
)
async def create_target(
    request: Request,
    wid: WorkspaceId,
    body: EvolutionTargetWrite,
    access: AdminAccess,
) -> EvolutionTarget:
    """Validate and create one target owned by this workspace."""
    del access
    return await targets_from(request).create(
        body,
        workspace_id=wid,
        created_by=_principal_id(request),
    )


@router.put("/targets/{targetId}/candidate-policy", dependencies=[Security(BEARER_AUTH)])
async def save_candidate_policy(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    body: CandidatePolicy,
    access: AdminAccess,
) -> CandidatePolicy:
    """Update only source rules under the target lock, preserving concurrent metadata edits."""
    await EvolutionTargetRepository(request.app.state.database).save_policy(
        wid, targetId, body.model_dump()
    )
    return body


@router.get("/candidate-sources", dependencies=[Security(BEARER_AUTH)])
async def candidate_sources(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[SourceCount]:
    window = window_day_boundaries(*resolve_window(start, end))
    rows = await CandidateSourcesRepository(request.app.state.database).counts(wid, *window)
    return [SourceCount.model_validate(row) for row in rows]


@router.get("/candidate-source-reports", dependencies=[Security(BEARER_AUTH)])
async def source_reports(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
    kind: SourceKind,
    name: Annotated[str, Query(min_length=1, max_length=128)],
    types: Annotated[list[ReportType], Query(min_length=1, max_length=2)],
    labels: Annotated[list[str] | None, Query()] = None,
    unlabelled: bool = False,
    filter_type: Annotated[ReportType | None, Query(alias="filterType")] = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> SourceReportPage:
    window = window_day_boundaries(*resolve_window(start, end))
    result = await CandidateSourcesRepository(request.app.state.database).reports(
        wid,
        *window,
        kind=kind,
        name=name,
        types=types,
        labels=labels or [],
        unlabelled=unlabelled,
        filter_type=filter_type,
        page=page,
        page_size=20,
    )
    return SourceReportPage.model_validate(result)


@router.put(
    "/targets/{targetId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Space administrator is required"},
        404: {"model": ErrorResponse, "description": "Target does not exist"},
        409: {"model": ErrorResponse, "description": "Object pair already exists"},
        422: {"model": ErrorResponse, "description": "Target configuration is invalid"},
    },
)
async def update_target(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    body: EvolutionTargetWrite,
    access: AdminAccess,
) -> EvolutionTarget:
    """Replace one target owned by this workspace."""
    del access
    return await targets_from(request).update(
        targetId,
        body,
        workspace_ids=(wid,),
    )


@router.delete(
    "/targets/{targetId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Space administrator is required"},
        404: {"model": ErrorResponse, "description": "Target does not exist"},
        409: {"model": ErrorResponse, "description": "Target has an active run"},
    },
)
async def delete_target(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    access: AdminAccess,
) -> None:
    """Delete one unused target owned by this workspace."""
    del access
    await targets_from(request).delete(targetId, workspace_ids=(wid,))


@router.get(
    "/targets/{targetId}/versions",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Target does not exist"},
        422: {"model": ErrorResponse, "description": "Configured remote is unavailable"},
    },
)
async def read_versions(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    access: ViewerAccess,
) -> EvolutionTargetVersions:
    """Return sorted remote tags for one workspace target."""
    del access
    return await targets_from(request).versions(targetId, workspace_ids=(wid,))


@router.post(
    "/preview/sessions",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **PREVIEW_RESPONSES,
        200: {"model": SessionPreviewResult, "description": "Associated Session page"},
    },
)
async def preview_sessions(
    request: Request,
    wid: WorkspaceId,
    body: SessionsPreviewRequest,
    access: ViewerAccess,
) -> SessionPreviewResult:
    """Return one page of Sessions whose trace contains the target version."""
    del access
    return await preview_from(request).sessions(body, workspace_id=wid)


@router.post(
    "/preview/potential",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **PREVIEW_RESPONSES,
        200: {"model": PotentialPreviewResult, "description": "Potential case page"},
    },
)
async def preview_potential(
    request: Request,
    wid: WorkspaceId,
    body: PotentialPreviewRequest,
    access: ViewerAccess,
) -> PotentialPreviewResult:
    """Return one page of policy-included potential cases."""
    del access
    return await preview_from(request).potential(body, workspace_id=wid)


@router.post(
    "/preview/attribution",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **PREVIEW_RESPONSES,
        200: {
            "model": AttributionPreviewResult,
            "description": "Read-only cache reuse preview",
        },
    },
)
async def preview_attribution(
    request: Request,
    wid: WorkspaceId,
    body: AttributionPreviewRequest,
    access: ViewerAccess,
) -> AttributionPreviewResult:
    """Return cache reuse counts without executing attribution."""
    del access
    return await preview_from(request).attribution(body, workspace_id=wid)


@router.get(
    "/runs",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def list_runs(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
) -> EvolutionRunList:
    """Return backend-ordered running and history groups for this workspace."""
    del access
    return await runs_from(request).list(workspace_ids=(wid,))


@router.get(
    "/runs/{run_id}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **STEP_RESPONSES,
        404: {"model": ErrorResponse, "description": "Run is unknown or out of workspace"},
    },
)
async def read_run(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    access: ViewerAccess,
) -> EvolutionRunDetail:
    """Return one run shell owned by this workspace."""
    del access
    detail = await runs_from(request).detail(run_id, workspace_ids=(wid,))
    if detail is None:
        raise _run_not_found()
    return detail


@router.get(
    "/runs/{run_id}/events",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Run is unknown or out of workspace"},
    },
)
async def read_run_events(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    access: ViewerAccess,
    after_seq: Annotated[int, Query(alias="afterSeq", ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    level: Annotated[EvolutionRunEventLevel | None, Query()] = None,
) -> EvolutionRunEventPage:
    """Return one stable event page of a run owned by this workspace."""
    del access
    return await events_from(request).list(
        run_id,
        after_seq=after_seq,
        limit=limit,
        level=level,
        workspace_ids=(wid,),
    )


@router.get(
    "/runs/{run_id}/steps/{key}",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_step(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    key: StepKey,
    access: ViewerAccess,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=50)] = 5,
) -> EvolutionStep:
    """Return one backend-owned step of a run owned by this workspace."""
    del access
    return await stages_from(request).step(
        run_id,
        key,
        workspace_ids=(wid,),
        page=page,
        page_size=page_size,
    )


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **LAUNCH_RESPONSES,
        202: {"model": RunAccepted, "description": "Full run accepted"},
    },
)
async def create_run(
    request: Request,
    wid: WorkspaceId,
    body: ProbeQueryRequest,
    access: AdminAccess,
) -> RunAccepted:
    """Admit one full evolution run owned by this workspace."""
    del access
    return await launch_from(request).request_run(
        body,
        expected_mode="full",
        created_by=_principal_id(request),
        workspace_ids=(wid,),
    )


@router.post(
    "/cluster-previews",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **LAUNCH_RESPONSES,
        202: {"model": RunAccepted, "description": "Cluster-only run accepted"},
    },
)
async def create_cluster_preview(
    request: Request,
    wid: WorkspaceId,
    body: ProbeQueryRequest,
    access: AdminAccess,
) -> RunAccepted:
    """Admit one cluster-only preview run owned by this workspace."""
    del access
    return await launch_from(request).request_run(
        body,
        expected_mode="cluster_only",
        created_by=_principal_id(request),
        workspace_ids=(wid,),
    )


@router.post(
    "/runs/{run_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: LAUNCH_RESPONSES[401],
        403: LAUNCH_RESPONSES[403],
        404: {"model": ErrorResponse, "description": "Run is unknown or out of workspace"},
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
async def retry_run(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    access: AdminAccess,
) -> EvolutionRetryAccepted:
    """Admit one manual retry for a blocked run owned by this workspace."""
    del access
    return await retry_from(request).request_retry(
        run_id,
        created_by=_principal_id(request),
        workspace_ids=(wid,),
    )


@router.get(
    "/runs/{run_id}/attribution-jobs",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def list_attribution_jobs(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    access: ViewerAccess,
) -> AttributionJobList:
    """Return sanitized attribution observations for one workspace run."""
    del access
    if await runs_from(request).detail(run_id, workspace_ids=(wid,)) is None:
        raise _run_not_found()
    return await attribution_jobs_from(request).history(run_id)


@router.post(
    "/runs/{run_id}/attribution-jobs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def create_attribution_job(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    access: AdminAccess,
) -> AttributionJobView:
    """Start or join one manual attribution batch."""
    del access
    if await runs_from(request).detail(run_id, workspace_ids=(wid,)) is None:
        raise _run_not_found()
    submission = await attribution_jobs_from(request).submit(
        run_id,
        created_by=_principal_id(request),
        source="manual",
    )
    return attribution_jobs_from(request).public(submission.job)


@router.post(
    "/runs/{run_id}/attribution-jobs/{job_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def retry_attribution_job(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    job_id: str,
    access: AdminAccess,
) -> AttributionJobView:
    """Retry only unfinished cases of one failed attribution batch."""
    del access
    if await runs_from(request).detail(run_id, workspace_ids=(wid,)) is None:
        raise _run_not_found()
    return await attribution_jobs_from(request).retry(run_id, job_id)


@router.post(
    "/runs/{run_id}/attribution-jobs/{job_id}/cancel",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def cancel_attribution_job(
    request: Request,
    wid: WorkspaceId,
    run_id: RunId,
    job_id: str,
    access: AdminAccess,
) -> AttributionJobView:
    """Cancel queued or running attribution work and retain its audit row."""
    del access
    if await runs_from(request).detail(run_id, workspace_ids=(wid,)) is None:
        raise _run_not_found()
    return await attribution_jobs_from(request).cancel(run_id, job_id)


@router.post(
    "/runs/{run_id}/pause",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: LAUNCH_RESPONSES[401],
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def pause_run(
    request: Request, wid: WorkspaceId, run_id: RunId, access: AdminAccess
) -> EvolutionRunControl:
    """Request a cooperative pause at the next durable checkpoint."""
    service = cast(EvolutionControlService, request.app.state.evolution_control)
    return await service.pause(run_id, wid, _principal_id(request))


@router.post(
    "/runs/{run_id}/resume",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: LAUNCH_RESPONSES[401],
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def resume_run(
    request: Request, wid: WorkspaceId, run_id: RunId, access: AdminAccess
) -> EvolutionRunControl:
    """Release a user pause and admit the first unfinished operation."""
    service = cast(EvolutionControlService, request.app.state.evolution_control)
    return await service.resume(run_id, wid, _principal_id(request))


@catalog_router.get(
    "/targets",
    response_model_exclude_none=True,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        422: {"model": ErrorResponse, "description": "Configured remote is unavailable"},
    },
)
async def read_target_catalog(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
) -> CatalogTargets:
    """Return enabled targets owned by this workspace with remote versions."""
    del access
    return await catalogs_from(request).targets(workspace_ids=(wid,))


@catalog_router.get(
    "/models",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def read_model_catalog(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
) -> CatalogModels:
    """Return model usage projected from this workspace's sessions."""
    del access
    return await catalogs_from(request).models(workspace_ids=(wid,))


def _run_not_found() -> AppError:
    """Return the non-enumerating missing-run response."""
    return AppError(
        status_code=404,
        code=ErrorCode.RUN_NOT_FOUND,
        message="evolution run not found",
    )
