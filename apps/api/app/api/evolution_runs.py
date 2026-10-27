"""Authenticated evolution run list and launch endpoints."""

from typing import cast

from fastapi import APIRouter, Request, Security, status

from app.api.evolution_launch import LAUNCH_RESPONSES
from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.probe_query import ProbeQueryRequest, RunAccepted
from app.service.evolution.runs import EvolutionRunList, EvolutionRunService
from app.service.identity.principals import Principal

router = APIRouter(prefix="/api/evolution/runs", tags=["evolution-runs"])


def runs_from(request: Request) -> EvolutionRunService:
    """Return the application-scoped evolution run service."""
    return cast(EvolutionRunService, request.app.state.evolution_runs)


def launch_from(request: Request) -> EvolutionLaunchService:
    """Return the application-scoped launch service."""
    return cast(EvolutionLaunchService, request.app.state.evolution_launch)


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
    principal = cast(Principal, request.state.principal)
    return await launch_from(request).request_run(
        body,
        expected_mode="full",
        created_by=principal.user_id,
    )
