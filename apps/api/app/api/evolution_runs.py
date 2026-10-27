"""Authenticated evolution run list, launch, and six-step step endpoints."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request, Security, status

from app.api.evolution_launch import LAUNCH_RESPONSES
from app.api.security import BEARER_AUTH
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.evolution.events import (
    EvolutionRunEventLevel,
    EvolutionRunEventPage,
    EvolutionRunEventService,
)
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.probe_query import ProbeQueryRequest, RunAccepted
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
    EvolutionStepInput,
    EvolutionStepIteration,
    EvolutionStepSeverity,
)
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


def _principal_id(request: Request) -> str | None:
    """Return the authenticated principal's user id."""
    return cast(Principal, request.state.principal).user_id


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
    """Return backend-ordered running and history groups."""
    return await runs_from(request).list()


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
    """Return one run shell with workspace and backend-owned step states."""
    detail = await runs_from(request).detail(run_id)
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
    """Admit one full evolution run after synchronous validation."""
    return await launch_from(request).request_run(
        body,
        expected_mode="full",
        created_by=_principal_id(request),
    )


@router.get(
    "/{run_id}/steps/input",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_input_step(run_id: str, request: Request) -> EvolutionStepInput:
    """Return the backend-owned filter-input projection of one run."""
    return cast(EvolutionStepInput, await stages_from(request).step(run_id, "input"))


@router.get(
    "/{run_id}/steps/clusters",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_clusters_step(run_id: str, request: Request) -> EvolutionStepClusters:
    """Return the backend-owned problem-cluster projection of one run."""
    return cast(EvolutionStepClusters, await stages_from(request).step(run_id, "clusters"))


@router.get(
    "/{run_id}/steps/attribution",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_attribution_step(run_id: str, request: Request) -> EvolutionStepAttribution:
    """Return the backend-owned attribution projection of one run."""
    return cast(
        EvolutionStepAttribution,
        await stages_from(request).step(run_id, "attribution"),
    )


@router.get(
    "/{run_id}/steps/severity",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_severity_step(run_id: str, request: Request) -> EvolutionStepSeverity:
    """Return the backend-owned severity ranking projection of one run."""
    return cast(
        EvolutionStepSeverity,
        await stages_from(request).step(run_id, "severity"),
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
        await stages_from(request).step(run_id, "iteration"),
    )


@router.get(
    "/{run_id}/steps/final",
    dependencies=[Security(BEARER_AUTH)],
    responses=STEP_RESPONSES,
)
async def read_final_step(run_id: str, request: Request) -> EvolutionStepFinal:
    """Return the backend-owned final evaluation projection of one run."""
    return cast(EvolutionStepFinal, await stages_from(request).step(run_id, "final"))
