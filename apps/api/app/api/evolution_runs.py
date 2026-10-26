"""Authenticated evolution run list endpoint."""

from typing import cast

from fastapi import APIRouter, Request, Security

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.evolution.runs import EvolutionRunList, EvolutionRunService

router = APIRouter(prefix="/api/evolution/runs", tags=["evolution-runs"])


def runs_from(request: Request) -> EvolutionRunService:
    """Return the application-scoped evolution run service."""
    return cast(EvolutionRunService, request.app.state.evolution_runs)


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
