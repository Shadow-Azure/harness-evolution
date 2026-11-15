"""Workspace authorization and auth/session aggregation rules."""

from dataclasses import dataclass

from app.db.crud.workspaces import WorkspaceRepository
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import PublicUser
from app.service.workspaces.roles import (
    WorkspaceMemberRole,
    WorkspaceRole,
    effective_role,
    role_at_least,
)
from app.service.workspaces.schemas import SessionPayload, SessionWorkspace

SESSION_WORKSPACE_LIMIT = 200
"""Maximum number of workspaces one auth/session response may carry."""


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """Verified workspace scope attached to one business request."""

    workspace_id: str
    role: WorkspaceRole


class WorkspaceService:
    """Own workspace visibility, role checks, and the session payload."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        """Bind workspace rules to their persistence boundary."""
        self._repository = repository

    async def authorize(
        self,
        *,
        user_id: str,
        user_role: str,
        workspace_id: str,
        minimum: WorkspaceMemberRole,
    ) -> WorkspaceAccess:
        """Resolve the effective role or fail with the shared invisible-space errors.

        Global administrators pass through any existing workspace; every other
        user must own a membership row of at least the required rank. A missing
        workspace and a workspace the caller cannot see share one 404, so callers
        cannot enumerate other spaces.
        """
        if user_role == "admin":
            workspace = await self._repository.get(workspace_id)
            if workspace is None:
                raise self._not_found()
            return WorkspaceAccess(workspace_id=workspace_id, role="global_admin")

        membership = await self._repository.get_membership(workspace_id, user_id)
        if membership is None:
            raise self._not_found()
        if not role_at_least(membership.role, minimum):
            raise AppError(
                status_code=403,
                code=ErrorCode.WORKSPACE_FORBIDDEN,
                message="workspace role is insufficient",
            )
        return WorkspaceAccess(
            workspace_id=workspace_id,
            role=effective_role(membership.role),
        )

    async def session_payload(self, user: PublicUser) -> SessionPayload:
        """Return the user plus their visible workspaces in one bounded payload."""
        visible = await self._repository.list_visible(
            user_id=user.id,
            include_all=user.role == "admin",
            limit=SESSION_WORKSPACE_LIMIT + 1,
        )
        truncated = len(visible) > SESSION_WORKSPACE_LIMIT
        selected = visible[:SESSION_WORKSPACE_LIMIT]
        workspace_ids = [row.workspace.id for row in selected]
        used_counts = await self._repository.used_counts(workspace_ids)
        member_counts = await self._repository.member_counts(workspace_ids)

        workspaces: list[SessionWorkspace] = []
        for row in selected:
            counts = member_counts.get(row.workspace.id)
            workspaces.append(
                SessionWorkspace(
                    id=row.workspace.id,
                    name=row.workspace.name,
                    mark=row.workspace.mark,
                    role=self._effective_role(row.role),
                    quota=row.workspace.quota,
                    used=used_counts.get(row.workspace.id, 0),
                    member_count=counts.member_count if counts else 0,
                    space_admin_count=counts.space_admin_count if counts else 0,
                ),
            )
        return SessionPayload(user=user, workspaces=workspaces, truncated=truncated)

    @staticmethod
    def _effective_role(stored_role: str | None) -> WorkspaceRole:
        """Derive the public role for a visible workspace row."""
        if stored_role is None:
            return "global_admin"
        return effective_role(stored_role)

    @staticmethod
    def _not_found() -> AppError:
        """Return the uniform invisible-or-missing workspace failure."""
        return AppError(
            status_code=404,
            code=ErrorCode.WORKSPACE_NOT_FOUND,
            message="workspace was not found",
        )
