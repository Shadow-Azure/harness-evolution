"""Read-only HTTP adapters for session cards and execution trees."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Security

from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.db.crud.read_scope import WorkspaceReadScope
from app.errors import ErrorResponse
from app.service.identity.principals import Principal
from app.service.sessions.schemas import SessionListItem, SessionListResponse, SessionTree
from app.service.sessions.service import SessionFilters, SessionService
from app.service.workspaces.service import WorkspaceAccess

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
workspace_router = APIRouter(prefix="/api/workspaces/{wid}/sessions", tags=["sessions"])

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]

SessionQuery = Annotated[str, Query(max_length=512)]
SessionStatus = Annotated[
    Literal["all", "ok", "partial", "fail", "problem"],
    Query(alias="status"),
]
SessionSortQuery = Annotated[
    Literal["latest", "userTurns", "messages", "agents"],
    Query(),
]
SessionLimit = Annotated[int, Query(ge=1, le=500)]


def sessions_from(request: Request) -> SessionService:
    """Return the application-scoped session service."""
    return cast(SessionService, request.app.state.sessions)


def read_scope(request: Request) -> WorkspaceReadScope:
    """Return the legacy endpoints' every-visible-workspace read scope."""
    principal = cast(Principal, request.state.principal)
    return WorkspaceReadScope.for_user(user_id=principal.user_id, role=principal.role)


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
    q: SessionQuery = "",
    status_filter: SessionStatus = "all",
    sort: SessionSortQuery = "latest",
    limit: SessionLimit = 100,
) -> SessionListResponse:
    """Return the current page of root-session cards."""
    return await sessions_from(request).list(
        SessionFilters(
            query=q,
            status=status_filter,
            sort=sort,
            limit=limit,
            exact_query=False,
        ),
        read_scope(request),
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
    return await sessions_from(request).get(session_id, read_scope(request))


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
    return await sessions_from(request).tree(session_id, read_scope(request))


@workspace_router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def list_workspace_sessions(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    q: SessionQuery = "",
    status_filter: SessionStatus = "all",
    sort: SessionSortQuery = "latest",
    limit: SessionLimit = 10,
) -> SessionListResponse:
    """Return the root sessions projected from one workspace's bad cases."""
    return await sessions_from(request).list(
        SessionFilters(
            query=q.strip(),
            status=status_filter,
            sort=sort,
            limit=limit,
            exact_query=True,
        ),
        WorkspaceReadScope.for_workspace(access.workspace_id),
    )


@workspace_router.get(
    "/{sessionId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace or Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_workspace_session(
    wid: WorkspaceId,
    session_id: Annotated[str, Path(alias="sessionId")],
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
) -> SessionListItem:
    """Return one session card only when the workspace projected it."""
    return await sessions_from(request).get(
        session_id,
        WorkspaceReadScope.for_workspace(access.workspace_id),
    )


@workspace_router.get(
    "/{sessionId}/tree",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace or Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_workspace_session_tree(
    wid: WorkspaceId,
    session_id: Annotated[str, Path(alias="sessionId")],
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
) -> SessionTree:
    """Return one workspace-projected tree with only this workspace's cases."""
    return await sessions_from(request).tree(
        session_id,
        WorkspaceReadScope.for_workspace(access.workspace_id),
    )
