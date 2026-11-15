"""Read-only authenticated problem, attribution, and probe endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Security

from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.db.crud.read_scope import WorkspaceReadScope
from app.errors import ErrorResponse
from app.service.identity.principals import Principal
from app.service.problems.schemas import (
    BadCase,
    BadCaseAnalysis,
    BadCaseListResponse,
    ProbeListResponse,
    ProbeReport,
)
from app.service.problems.service import ProblemService
from app.service.workspaces.service import WorkspaceAccess

router = APIRouter(tags=["problems"])
workspace_router = APIRouter(prefix="/api/workspaces/{wid}", tags=["problems"])

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]
SessionId = Annotated[str, Path(alias="sessionId", min_length=1, max_length=36)]
BadCaseId = Annotated[str, Path(alias="badCaseId", min_length=1, max_length=64)]
OptionalSessionId = Annotated[
    str | None,
    Query(alias="sessionId", min_length=1, max_length=36),
]


def problems_from(request: Request) -> ProblemService:
    """Return the application-scoped read-only problem service."""
    return cast(ProblemService, request.app.state.problems)


def read_scope(request: Request) -> WorkspaceReadScope:
    """Return the legacy endpoints' every-visible-workspace read scope."""
    principal = cast(Principal, request.state.principal)
    return WorkspaceReadScope.for_user(user_id=principal.user_id, role=principal.role)


@router.get(
    "/api/sessions/{sessionId}/bad-cases",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def list_session_bad_cases(
    session_id: Annotated[str, Path(alias="sessionId", min_length=1, max_length=36)],
    request: Request,
) -> BadCaseListResponse:
    """Return one Session's problems in external creation order."""
    return await problems_from(request).list_for_session(session_id, read_scope(request))


@router.get(
    "/api/sessions/{sessionId}/probes",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def list_session_probes(
    session_id: Annotated[str, Path(alias="sessionId", min_length=1, max_length=36)],
    request: Request,
) -> ProbeListResponse:
    """Return every root-cause report owned by one Session."""
    return await problems_from(request).list_probes(session_id, read_scope(request))


@router.get(
    "/api/bad-cases/{badCaseId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Problem does not exist"},
        409: {"model": ErrorResponse, "description": "Problem belongs to another Session"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_bad_case(
    bad_case_id: Annotated[str, Path(alias="badCaseId", min_length=1, max_length=64)],
    request: Request,
    session_id: OptionalSessionId = None,
) -> BadCase:
    """Return one problem and optionally enforce deep-link ownership."""
    return await problems_from(request).get_case(
        bad_case_id,
        session_id,
        read_scope(request),
    )


@router.get(
    "/api/bad-cases/{badCaseId}/analysis",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Problem does not exist"},
        409: {"model": ErrorResponse, "description": "Problem belongs to another Session"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_bad_case_analysis(
    bad_case_id: Annotated[str, Path(alias="badCaseId", min_length=1, max_length=64)],
    request: Request,
    session_id: OptionalSessionId = None,
) -> BadCaseAnalysis:
    """Return the five-state attribution view, including no-row placeholder."""
    return await problems_from(request).get_analysis(
        bad_case_id,
        session_id,
        read_scope(request),
    )


@router.get(
    "/api/probes/{probeId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        404: {"model": ErrorResponse, "description": "Probe does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_probe(
    probe_id: Annotated[str, Path(alias="probeId", min_length=1, max_length=64)],
    request: Request,
) -> ProbeReport:
    """Return one validated root-cause report."""
    return await problems_from(request).get_probe(probe_id, read_scope(request))


@workspace_router.get(
    "/sessions/{sessionId}/bad-cases",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace or Session does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def list_workspace_session_bad_cases(
    wid: WorkspaceId,
    session_id: SessionId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
) -> BadCaseListResponse:
    """Return only this workspace's problems for one projected Session."""
    return await problems_from(request).list_for_session(
        session_id,
        WorkspaceReadScope.for_workspace(access.workspace_id),
    )


@workspace_router.get(
    "/bad-cases/{badCaseId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace or problem does not exist"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def get_workspace_bad_case(
    wid: WorkspaceId,
    bad_case_id: BadCaseId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
) -> BadCase:
    """Return one problem only when it belongs to this workspace."""
    return await problems_from(request).get_case(
        bad_case_id,
        None,
        WorkspaceReadScope.for_workspace(access.workspace_id),
    )
