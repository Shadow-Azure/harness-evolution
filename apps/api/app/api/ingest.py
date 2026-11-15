"""Workspace-credential bad-case ingest endpoint."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Request, Response, status

from app.errors import ErrorResponse
from app.service.workspaces.ingest import (
    BadCaseIngest,
    BadCaseIngestResponse,
    BadCaseIngestService,
)
from app.service.workspaces.service import WorkspaceCredentialAccess

router = APIRouter(prefix="/api/workspaces", tags=["ingest"])

WORKSPACE_USED_HEADER = "X-HE-Workspace-Used"
"""Response header carrying the live bad-case usage after a successful report."""

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]

_USED_HEADER_SCHEMA: dict[str, Any] = {
    "description": "Live count of bad cases owned by the workspace after this report.",
    "schema": {"type": "integer", "minimum": 0},
}

_SUCCESS_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "model": BadCaseIngestResponse,
        "description": "The same workspace already owned badCaseId; upstream fields were replaced",
        "headers": {WORKSPACE_USED_HEADER: _USED_HEADER_SCHEMA},
    },
    201: {
        "model": BadCaseIngestResponse,
        "description": "A new bad case was created inside the workspace quota",
        "headers": {WORKSPACE_USED_HEADER: _USED_HEADER_SCHEMA},
    },
}

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "The workspace credential is missing or invalid"},
    403: {
        "model": ErrorResponse,
        "description": "The credential belongs to a different workspace",
    },
    404: {"model": ErrorResponse, "description": "The workspace does not exist"},
    409: {
        "model": ErrorResponse,
        "description": "The quota is exhausted or badCaseId belongs to another workspace",
    },
    422: {"model": ErrorResponse, "description": "The reported payload violates the contract"},
}


def ingest_service(request: Request) -> BadCaseIngestService:
    """Return the application-scoped bad-case ingest service."""
    return cast(BadCaseIngestService, request.app.state.bad_case_ingest)


def bearer_credential(request: Request) -> str | None:
    """Return the raw bearer value, or ``None`` when the header is unusable."""
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        return None
    return token


async def credential_access(
    request: Request,
    wid: WorkspaceId,
) -> WorkspaceCredentialAccess:
    """Resolve the ingest credential and bind it to the path workspace."""
    return await ingest_service(request).authorize(wid, bearer_credential(request))


@router.post(
    "/{wid}/bad-cases",
    status_code=status.HTTP_201_CREATED,
    responses={**_SUCCESS_RESPONSES, **_ERROR_RESPONSES},
    summary="Report one bad case with a workspace credential",
)
async def ingest_bad_case(
    wid: WorkspaceId,
    body: BadCaseIngest,
    request: Request,
    response: Response,
    access: Annotated[WorkspaceCredentialAccess, Depends(credential_access)],
) -> BadCaseIngestResponse:
    """Upsert one reported bad case as the workspace resolved from URL and credential.

    Authentication is a workspace ingest credential
    (`Authorization: Bearer whk_…`), not the browser access token. The body may
    never carry workspace identity: the workspace comes from the URL, and the
    credential must belong to it. A new `badCaseId` answers `201`; re-reporting
    an id already owned by this workspace replaces its upstream fields and
    answers `200` without consuming quota.
    """
    outcome = await ingest_service(request).ingest(access, body)
    response.status_code = status.HTTP_201_CREATED if outcome.created else status.HTTP_200_OK
    response.headers[WORKSPACE_USED_HEADER] = str(outcome.response.workspace_used)
    return outcome.response
