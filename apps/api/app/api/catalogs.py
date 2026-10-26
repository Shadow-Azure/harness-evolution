"""Member-readable evolution wizard catalogs."""

from typing import cast

from fastapi import APIRouter, Request, Security

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.catalogs import CatalogModels, CatalogService, CatalogTargets

router = APIRouter(prefix="/api/catalogs", tags=["catalogs"])


def catalogs_from(request: Request) -> CatalogService:
    """Return the application-scoped catalog service."""
    return cast(CatalogService, request.app.state.catalogs)


@router.get(
    "/targets",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        422: {"model": ErrorResponse, "description": "Configured remote is unavailable"},
    },
)
async def get_target_catalog(request: Request) -> CatalogTargets:
    """Return enabled evolution targets and their remote versions."""
    return await catalogs_from(request).targets()


@router.get(
    "/models",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
    },
)
async def get_model_catalog(request: Request) -> CatalogModels:
    """Return normalized model usage from the Agent table."""
    return await catalogs_from(request).models()
