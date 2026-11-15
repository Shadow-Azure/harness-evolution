"""Reusable FastAPI dependencies for workspace-scoped business routes."""

from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import Path, Request

from app.service.workspaces.roles import WorkspaceMemberRole
from app.service.workspaces.service import WorkspaceAccess, WorkspaceService

WorkspaceRoleDependency = Callable[..., Awaitable[WorkspaceAccess]]
"""Dependency signature that resolves one verified workspace access."""


def workspaces_from(request: Request) -> WorkspaceService:
    """Return the application-scoped workspace service."""
    return cast(WorkspaceService, request.app.state.workspaces)


async def visible_workspace_ids(request: Request) -> tuple[str, ...] | None:
    """Return the caller's visible workspace ids, or ``None`` for a global admin.

    Unscoped compatibility routes use this result to filter every row they
    project, so a legacy path cannot leak another workspace's resources.
    """
    principal = request.state.principal
    return await workspaces_from(request).visible_ids(principal.user_id, principal.role)


async def authorize_workspace(
    request: Request,
    workspace_id: str,
    minimum: WorkspaceMemberRole,
) -> WorkspaceAccess:
    """Authorize the current principal on one resolved workspace.

    Legacy write routes resolve the workspace from the target or run they are
    about to mutate, then enforce the same role matrix as the V2 routes.
    """
    principal = request.state.principal
    return await workspaces_from(request).authorize(
        user_id=principal.user_id,
        user_role=principal.role,
        workspace_id=workspace_id,
        minimum=minimum,
    )


def require_workspace_role(minimum: WorkspaceMemberRole) -> WorkspaceRoleDependency:
    """Build a dependency enforcing the minimum effective role on ``{wid}``.

    Global administrators pass through any existing workspace; other roles read
    their membership row on every request, so membership changes apply at once.
    Missing and invisible workspaces both answer ``404 WORKSPACE_NOT_FOUND``.
    """

    async def dependency(
        request: Request,
        wid: Annotated[str, Path(min_length=1, max_length=36)],
    ) -> WorkspaceAccess:
        """Authorize the current principal against the path workspace."""
        principal = request.state.principal
        service = cast(WorkspaceService, request.app.state.workspaces)
        return await service.authorize(
            user_id=principal.user_id,
            user_role=principal.role,
            workspace_id=wid,
            minimum=minimum,
        )

    return dependency
