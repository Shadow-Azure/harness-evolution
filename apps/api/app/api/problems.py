"""Read-only authenticated problem, attribution, and probe endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Path, Query, Request, Security

from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.problems.schemas import (
    BadCase,
    BadCaseAnalysis,
    BadCaseListResponse,
    ProbeListResponse,
    ProbeReport,
)
from app.service.problems.service import ProblemService

router = APIRouter(tags=["problems"])

OptionalSessionId = Annotated[
    str | None,
    Query(alias="sessionId", min_length=1, max_length=36),
]


def problems_from(request: Request) -> ProblemService:
    """Return the application-scoped read-only problem service."""
    return cast(ProblemService, request.app.state.problems)


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
    return await problems_from(request).list_for_session(session_id)


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
    return await problems_from(request).list_probes(session_id)


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
    return await problems_from(request).get_case(bad_case_id, session_id)


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
    return await problems_from(request).get_analysis(bad_case_id, session_id)


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
    return await problems_from(request).get_probe(probe_id)
