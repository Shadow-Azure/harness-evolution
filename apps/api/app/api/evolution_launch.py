"""Launch-wizard endpoints: probe preview and cluster previews."""

from typing import Any, cast

from fastapi import APIRouter, Request, Security, status

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.probe_query import (
    ProbeQueryRequest,
    ProbeQueryResult,
    ProbeQueryService,
    RunAccepted,
)
from app.service.identity.principals import Principal

probe_router = APIRouter(prefix="/api/evolution/probes", tags=["evolution-launch"])
preview_router = APIRouter(
    prefix="/api/evolution/cluster-previews",
    tags=["evolution-launch"],
)


def probe_service_from(request: Request) -> ProbeQueryService:
    """Return the application-scoped probe query service."""
    return cast(ProbeQueryService, request.app.state.probe_query)


def launch_service_from(request: Request) -> EvolutionLaunchService:
    """Return the application-scoped launch service."""
    return cast(EvolutionLaunchService, request.app.state.evolution_launch)


def _principal_id(request: Request) -> str | None:
    """Return the authenticated principal's user id."""
    return cast(Principal, request.state.principal).user_id


LAUNCH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required"},
    403: {"model": ErrorResponse, "description": "Password change is required"},
    409: {"model": ErrorResponse, "description": "Target unconfigured or no probe hits"},
    422: {"model": ErrorResponse, "description": "Launch condition is invalid"},
}


@probe_router.post(
    "/query",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: LAUNCH_RESPONSES[401],
        403: LAUNCH_RESPONSES[403],
        409: LAUNCH_RESPONSES[409],
        422: LAUNCH_RESPONSES[422],
    },
)
async def query_probe_hits(
    body: ProbeQueryRequest,
    request: Request,
) -> ProbeQueryResult:
    """Return hit statistics and the first probe page for wizard step 2."""
    return await probe_service_from(request).preview(body)


@preview_router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **LAUNCH_RESPONSES,
        202: {"model": RunAccepted, "description": "Cluster-only run accepted"},
    },
)
async def create_cluster_preview(
    body: ProbeQueryRequest,
    request: Request,
) -> RunAccepted:
    """Admit a cluster-only preview run without workspace or evaluation."""
    return await launch_service_from(request).request_run(
        body,
        expected_mode="cluster_only",
        created_by=_principal_id(request),
    )
