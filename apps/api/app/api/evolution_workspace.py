"""Workspace-scoped evolution targets, runs, steps, events, and catalogs."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Security, status

from app.api.deps import require_workspace_role
from app.api.evolution_launch import LAUNCH_RESPONSES
from app.api.security import BEARER_AUTH
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.catalogs import CatalogModels, CatalogService, CatalogTargets
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


def targets_from(request: Request) -> EvolutionTargetService:
    """Return the application-scoped target configuration service."""
    return cast(EvolutionTargetService, request.app.state.evolution_targets)


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


def retry_from(request: Request) -> EvolutionRetryService:
    """Return the application-scoped blocked-run retry service."""
    return cast(EvolutionRetryService, request.app.state.evolution_retry)


def catalogs_from(request: Request) -> CatalogService:
    """Return the application-scoped catalog service."""
    return cast(CatalogService, request.app.state.catalogs)


def _principal_id(request: Request) -> str | None:
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
) -> EvolutionStep:
    """Return one backend-owned step of a run owned by this workspace."""
    del access
    return await stages_from(request).step(run_id, key, workspace_ids=(wid,))


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


@catalog_router.get(
    "/targets",
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
