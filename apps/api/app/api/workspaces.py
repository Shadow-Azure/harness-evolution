"""Workspace administration, membership, and ingest credential endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Response, Security, status

from app.api.auth import identity_from, public_user
from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.db.models.users import UserRecord
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.identity.principals import Principal
from app.service.workspaces.bad_case_labels import WorkspaceBadCaseLabelService
from app.service.workspaces.schemas import (
    Workspace,
    WorkspaceBadCaseLabelConfiguration,
    WorkspaceBadCaseLabelRequest,
    WorkspaceCreateRequest,
    WorkspaceCredentialCreated,
    WorkspaceCredentialListResponse,
    WorkspaceListResponse,
    WorkspaceMember,
    WorkspaceMemberCandidateListResponse,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberListResponse,
    WorkspaceMemberUpdateRequest,
    WorkspaceUpdateRequest,
)
from app.service.workspaces.service import WorkspaceAccess, WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]
MemberId = Annotated[str, Path(min_length=1, max_length=36)]
CredentialId = Annotated[str, Path(min_length=1, max_length=36)]
CandidateLimit = Annotated[int, Query(ge=1, le=20)]


def workspaces_from(request: Request) -> WorkspaceService:
    """Return the application-scoped workspace service."""
    return cast(WorkspaceService, request.app.state.workspaces)


def bad_case_labels_from(request: Request) -> WorkspaceBadCaseLabelService:
    """Return the application-scoped workspace label service."""
    return cast(WorkspaceBadCaseLabelService, request.app.state.bad_case_labels)


async def current_user(request: Request) -> UserRecord:
    """Return the authenticated user row for the current principal."""
    principal = cast(Principal, request.state.principal)
    user = await identity_from(request).get_user(principal.user_id)
    if user is None:
        raise AppError(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="authentication is required",
        )
    return user


@router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
    },
)
async def list_workspaces(request: Request) -> WorkspaceListResponse:
    """Return every workspace visible to the current user."""
    user = await current_user(request)
    items = await workspaces_from(request).list_workspaces(public_user(user))
    return WorkspaceListResponse(items=items)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Administrator role is required"},
        409: {"model": ErrorResponse, "description": "Workspace name already exists"},
        422: {"model": ErrorResponse, "description": "Quota or initial admin list is invalid"},
    },
)
async def create_workspace(
    body: WorkspaceCreateRequest,
    request: Request,
) -> Workspace:
    """Create one workspace with at least one existing space administrator."""
    principal = cast(Principal, request.state.principal)
    return await workspaces_from(request).create_workspace(
        body,
        created_by=principal.user_id,
    )


@router.put(
    "/{wid}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Role cannot change this field"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        409: {"model": ErrorResponse, "description": "Workspace name already exists"},
        422: {"model": ErrorResponse, "description": "Quota is below current usage"},
    },
)
async def update_workspace(
    wid: WorkspaceId,
    body: WorkspaceUpdateRequest,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> Workspace:
    """Update the workspace fields permitted for the caller's effective role."""
    return await workspaces_from(request).update_workspace(access, body)


@router.get(
    "/{wid}/bad-case-labels",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def get_bad_case_labels(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
) -> WorkspaceBadCaseLabelConfiguration:
    """Return the public badcase labels accepted by this workspace."""
    return await bad_case_labels_from(request).get(access.workspace_id)


@router.put(
    "/{wid}/bad-case-labels",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        422: {"model": ErrorResponse, "description": "Label set is invalid"},
    },
)
async def replace_bad_case_labels(
    wid: WorkspaceId,
    body: WorkspaceBadCaseLabelRequest,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> WorkspaceBadCaseLabelConfiguration:
    """Replace label rules and historical catalog assignments atomically."""
    return await bad_case_labels_from(request).replace(access.workspace_id, body.items)


@router.get(
    "/{wid}/members",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def list_members(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("member"))],
) -> WorkspaceMemberListResponse:
    """Return the member table in role and join-time order."""
    return WorkspaceMemberListResponse(
        items=await workspaces_from(request).list_members(access.workspace_id),
    )


@router.get(
    "/{wid}/member-candidates",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        422: {"model": ErrorResponse, "description": "Search limit is out of range"},
    },
)
async def list_member_candidates(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
    q: Annotated[str, Query(max_length=64)] = "",
    limit: CandidateLimit = 10,
) -> WorkspaceMemberCandidateListResponse:
    """Search non-member users without exposing the global user directory."""
    return WorkspaceMemberCandidateListResponse(
        items=await workspaces_from(request).list_member_candidates(
            access.workspace_id,
            query=q,
            limit=limit,
        ),
    )


@router.post(
    "/{wid}/members",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Space admins cannot grant space_admin"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        409: {"model": ErrorResponse, "description": "User is already a member"},
        422: {"model": ErrorResponse, "description": "User or role is invalid"},
    },
)
async def add_member(
    wid: WorkspaceId,
    body: WorkspaceMemberCreateRequest,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> WorkspaceMember:
    """Add one existing user to the workspace."""
    return await workspaces_from(request).add_member(access, body)


@router.put(
    "/{wid}/members/{userId}",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Space admins cannot grant space_admin"},
        404: {"model": ErrorResponse, "description": "Workspace or member does not exist"},
        409: {"model": ErrorResponse, "description": "Space-admin row or last admin is locked"},
        422: {"model": ErrorResponse, "description": "Role is invalid"},
    },
)
async def update_member(
    wid: WorkspaceId,
    userId: MemberId,
    body: WorkspaceMemberUpdateRequest,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> WorkspaceMember:
    """Change one workspace member's role."""
    return await workspaces_from(request).update_member(access, userId, body)


@router.delete(
    "/{wid}/members/{userId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Space admins cannot remove space admins"},
        404: {"model": ErrorResponse, "description": "Workspace or member does not exist"},
        409: {"model": ErrorResponse, "description": "The last space admin cannot be removed"},
        422: {"model": ErrorResponse, "description": "Member id is invalid"},
    },
)
async def remove_member(
    wid: WorkspaceId,
    userId: MemberId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> Response:
    """Remove one workspace member while preserving a space administrator."""
    await workspaces_from(request).remove_member(access, userId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{wid}/members/self-admin",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {
            "model": ErrorResponse,
            "description": "Only the global administrator may appoint itself",
        },
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def appoint_self_as_space_admin(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> WorkspaceMember:
    """Write an idempotent real space-admin row for the global administrator."""
    principal = cast(Principal, request.state.principal)
    return await workspaces_from(request).appoint_self(access, principal.user_id)


@router.get(
    "/{wid}/credentials",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    },
)
async def list_credentials(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> WorkspaceCredentialListResponse:
    """Return every credential row, including revoked ones, without plaintext."""
    return WorkspaceCredentialListResponse(
        items=await workspaces_from(request).list_credentials(access.workspace_id),
    )


@router.post(
    "/{wid}/credentials",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Workspace does not exist"},
        409: {"model": ErrorResponse, "description": "Three active credentials already exist"},
    },
)
async def create_credential(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> WorkspaceCredentialCreated:
    """Mint one credential and return its plaintext exactly once."""
    principal = cast(Principal, request.state.principal)
    return await workspaces_from(request).create_credential(
        access,
        created_by=principal.user_id,
    )


@router.delete(
    "/{wid}/credentials/{cid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
        404: {"model": ErrorResponse, "description": "Credential does not exist"},
        422: {"model": ErrorResponse, "description": "Credential id is invalid"},
    },
)
async def revoke_credential(
    wid: WorkspaceId,
    cid: CredentialId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
) -> Response:
    """Revoke one credential; retries stay idempotent."""
    await workspaces_from(request).revoke_credential(access.workspace_id, cid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
