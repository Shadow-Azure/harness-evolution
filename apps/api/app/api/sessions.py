"""Read-only HTTP adapters for session cards and execution trees."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Path, Query, Request, Security

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.sessions.schemas import SessionListItem, SessionListResponse, SessionTree
from app.service.sessions.service import SessionFilters, SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def sessions_from(request: Request) -> SessionService:
    """Return the application-scoped session service."""
    return cast(SessionService, request.app.state.sessions)


@router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def list_sessions(
    request: Request,
    q: Annotated[str, Query(max_length=512)] = "",
    status_filter: Annotated[
        Literal["all", "ok", "partial", "fail", "problem"],
        Query(alias="status"),
    ] = "all",
    sort: Annotated[
        Literal["latest", "userTurns", "messages", "agents"],
        Query(),
    ] = "latest",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SessionListResponse:
    """Return the current page of root-session cards."""
    return await sessions_from(request).list(
        SessionFilters(
            query=q,
            status=status_filter,
            sort=sort,
            limit=limit,
        ),
    )


@router.get(
    "/{sessionId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_session(
    session_id: Annotated[str, Path(alias="sessionId")],
    request: Request,
) -> SessionListItem:
    """Return one session overview card."""
    return await sessions_from(request).get(session_id)


@router.get(
    "/{sessionId}/tree",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_session_tree(
    session_id: Annotated[str, Path(alias="sessionId")],
    request: Request,
) -> SessionTree:
    """Return the flat canonical Agent tree and anchored problem cards."""
    return await sessions_from(request).tree(session_id)
