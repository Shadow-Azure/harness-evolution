"""Administrator-managed evolution target configuration endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Path, Request, Response, Security, status

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.evolution.targets import (
    EvolutionTarget,
    EvolutionTargetList,
    EvolutionTargetService,
    EvolutionTargetVersions,
    EvolutionTargetWrite,
)
from app.service.identity.principals import Principal

router = APIRouter(prefix="/api/evolution/targets", tags=["evolution-targets"])

TargetId = Annotated[str, Path(min_length=1, max_length=36)]


def targets_from(request: Request) -> EvolutionTargetService:
    """Return the application-scoped target configuration service."""
    return cast(EvolutionTargetService, request.app.state.evolution_targets)


@router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
    },
)
async def list_targets(request: Request) -> EvolutionTargetList:
    """Return every configured target, including disabled rows."""
    return await targets_from(request).list()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Administrator role is required"},
        409: {"model": ErrorResponse, "description": "Object pair already exists"},
        422: {"model": ErrorResponse, "description": "Target or remote is invalid"},
    },
)
async def create_target(
    body: EvolutionTargetWrite,
    request: Request,
) -> EvolutionTarget:
    """Validate and create one administrator-managed target."""
    principal = cast(Principal, request.state.principal)
    return await targets_from(request).create(body, created_by=principal.user_id)


@router.put(
    "/{targetId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Administrator role is required"},
        404: {"model": ErrorResponse, "description": "Target does not exist"},
        409: {"model": ErrorResponse, "description": "Object pair already exists"},
        422: {"model": ErrorResponse, "description": "Target or remote is invalid"},
    },
)
async def update_target(
    targetId: TargetId,
    body: EvolutionTargetWrite,
    request: Request,
) -> EvolutionTarget:
    """Replace one target's editable fields after remote validation."""
    return await targets_from(request).update(targetId, body)


@router.delete(
    "/{targetId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Administrator role is required"},
        404: {"model": ErrorResponse, "description": "Target does not exist"},
        409: {"model": ErrorResponse, "description": "Target has an active run"},
        422: {"model": ErrorResponse, "description": "Target id is invalid"},
    },
)
async def delete_target(
    targetId: TargetId,
    request: Request,
) -> Response:
    """Delete one unused target."""
    await targets_from(request).delete(targetId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{targetId}/versions",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Target does not exist"},
        422: {"model": ErrorResponse, "description": "Remote is unavailable"},
    },
)
async def list_target_versions(
    targetId: TargetId,
    request: Request,
) -> EvolutionTargetVersions:
    """Return sorted tags and the target's default reference."""
    return await targets_from(request).versions(targetId)
