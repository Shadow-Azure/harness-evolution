"""Workspace authorization, administration, and auth/session aggregation rules."""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from app.db.crud.workspaces import (
    MemberAlreadyExists,
    WorkspaceAdminRecord,
    WorkspaceCredentialRecord,
    WorkspaceMemberRecord,
    WorkspaceNameConflict,
    WorkspaceRecord,
    WorkspaceRepository,
)
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import PublicUser
from app.service.workspaces.roles import (
    WorkspaceMemberRole,
    WorkspaceRole,
    effective_role,
    role_at_least,
)
from app.service.workspaces.schemas import (
    SessionPayload,
    SessionWorkspace,
    Workspace,
    WorkspaceAdmin,
    WorkspaceCreateRequest,
    WorkspaceCredential,
    WorkspaceCredentialCreated,
    WorkspaceMember,
    WorkspaceMemberCandidate,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceUpdateRequest,
)
from app.utils.knowledge_paths import KnowledgeRootError, normalize_knowledge_roots
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

SESSION_WORKSPACE_LIMIT = 200
"""Maximum number of workspaces one auth/session response may carry."""

CREDENTIAL_ACTIVE_LIMIT = 3
"""Maximum number of non-revoked ingest credentials per workspace."""

CREDENTIAL_PREFIX_LENGTH = 12
"""Length of the non-secret credential prefix shown in management lists."""

CREDENTIAL_TOKEN_PREFIX = "whk_"  # noqa: S105
"""Namespace every plaintext workspace ingest credential starts with."""

CREDENTIAL_TOUCH_SECONDS = 60
"""Minimum interval between two `last_used_at` writes for one credential."""


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """Verified workspace scope attached to one business request."""

    workspace_id: str
    role: WorkspaceRole


@dataclass(frozen=True, slots=True)
class WorkspaceCredentialAccess:
    """Verified ingest scope resolved from one bearer credential."""

    workspace_id: str
    credential_id: str


class WorkspaceService:
    """Own workspace visibility, role checks, administration, and credentials."""

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

    async def visible_ids(self, user_id: str, user_role: str) -> tuple[str, ...] | None:
        """Return the caller's visible workspace ids, or ``None`` for a global admin.

        Legacy unscoped endpoints use this to filter every workspace-owned row
        without exposing spaces the caller must not see.
        """
        if user_role == "admin":
            return None
        visible = await self._repository.list_visible(user_id=user_id, include_all=False)
        return tuple(row.workspace.id for row in visible)

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

    async def list_workspaces(self, user: PublicUser) -> list[Workspace]:
        """Return every workspace visible to the caller with management aggregates."""
        visible = await self._repository.list_visible(
            user_id=user.id,
            include_all=user.role == "admin",
        )
        workspace_ids = [row.workspace.id for row in visible]
        used_counts = await self._repository.used_counts(workspace_ids)
        member_counts = await self._repository.member_counts(workspace_ids)
        admins = await self._repository.list_space_admins(workspace_ids)
        return [
            self._workspace_dto(
                row.workspace,
                used=used_counts.get(row.workspace.id, 0),
                member_count=(
                    member_counts[row.workspace.id].member_count
                    if row.workspace.id in member_counts
                    else 0
                ),
                space_admins=[self._admin_dto(admin) for admin in admins.get(row.workspace.id, [])],
            )
            for row in visible
        ]

    async def create_workspace(
        self,
        body: WorkspaceCreateRequest,
        *,
        created_by: str,
    ) -> Workspace:
        """Create one workspace with at least one existing initial administrator."""
        name = body.name
        mark = body.mark
        quota = body.quota
        space_admin_ids = list(dict.fromkeys(body.space_admin_ids))
        knowledge_roots = self._validated_knowledge_roots(body.knowledge_roots)
        if quota < 0:
            raise self._quota_invalid(quota=quota, used=0)
        if not space_admin_ids:
            raise self._role_invalid("a workspace needs at least one space admin")
        users = await self._repository.users_by_ids(space_admin_ids)
        if len(users) != len(space_admin_ids):
            raise self._role_invalid("every initial space admin must be an existing user")
        try:
            workspace = await self._repository.create_workspace(
                name=name,
                mark=mark,
                quota=quota,
                created_by=created_by,
                space_admin_ids=space_admin_ids,
                knowledge_roots=knowledge_roots,
            )
        except WorkspaceNameConflict as exc:
            raise self._workspace_exists() from exc
        logger.info("workspace created", extra={"workspace_id": workspace.id})
        space_admins = [
            WorkspaceAdmin(id=user_id, display_name=users[user_id].display_name)
            for user_id in space_admin_ids
        ]
        return self._workspace_dto(
            workspace,
            used=0,
            member_count=len(space_admin_ids),
            space_admins=space_admins,
        )

    async def update_workspace(
        self,
        access: WorkspaceAccess,
        body: WorkspaceUpdateRequest,
    ) -> Workspace:
        """Apply the documented field-level permissions and live quota rule."""
        workspace = await self._repository.get(access.workspace_id)
        if workspace is None:
            raise self._not_found()
        used = await self._repository.used_count(access.workspace_id)
        name = body.name
        mark = body.mark
        quota = body.quota
        knowledge_roots = (
            self._validated_knowledge_roots(body.knowledge_roots)
            if body.knowledge_roots is not None
            else None
        )
        if access.role != "global_admin" and (name is not None or mark is not None):
            raise self._forbidden("only the global administrator may rename a workspace")
        if quota is not None and (quota < 0 or quota < used):
            raise self._quota_invalid(quota=quota, used=used)
        updates: dict[str, object] = {}
        if name is not None:
            updates["name"] = name
        if mark is not None:
            updates["mark"] = mark
        if quota is not None:
            updates["quota"] = quota
        if knowledge_roots is not None:
            updates["knowledge_roots"] = list(knowledge_roots)
        try:
            updated = await self._repository.update_workspace(
                access.workspace_id,
                updates,
            )
        except WorkspaceNameConflict as exc:
            raise self._workspace_exists() from exc
        if updated is None:
            raise self._not_found()
        member_counts = await self._repository.member_counts([access.workspace_id])
        admins = await self._repository.list_space_admins([access.workspace_id])
        counts = member_counts.get(access.workspace_id)
        return self._workspace_dto(
            updated,
            used=used,
            member_count=counts.member_count if counts else 0,
            space_admins=[self._admin_dto(admin) for admin in admins.get(access.workspace_id, [])],
        )

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        """Return workspace members in role and join-time order."""
        return [
            self._member_dto(member) for member in await self._repository.list_members(workspace_id)
        ]

    async def list_member_candidates(
        self,
        workspace_id: str,
        *,
        query: str,
        limit: int,
    ) -> list[WorkspaceMemberCandidate]:
        """Return a bounded page of non-member users matching the search text."""
        candidates = await self._repository.search_member_candidates(
            workspace_id,
            query,
            limit,
        )
        return [
            WorkspaceMemberCandidate(
                id=candidate.id,
                username=candidate.username,
                display_name=candidate.display_name,
                active=candidate.active,
            )
            for candidate in candidates
        ]

    async def add_member(
        self,
        access: WorkspaceAccess,
        body: WorkspaceMemberCreateRequest,
    ) -> WorkspaceMember:
        """Add one existing user while keeping space-admin grants global-admin only."""
        if await self._repository.get_user(body.user_id) is None:
            raise self._role_invalid("member must be an existing user")
        if body.role == "space_admin" and access.role != "global_admin":
            raise self._forbidden("space admins cannot grant space_admin")
        try:
            member = await self._repository.add_member(
                workspace_id=access.workspace_id,
                user_id=body.user_id,
                role=body.role,
            )
        except MemberAlreadyExists as exc:
            raise AppError(
                status_code=409,
                code=ErrorCode.MEMBER_EXISTS,
                message="user is already a workspace member",
            ) from exc
        logger.info(
            "workspace member added",
            extra={"workspace_id": access.workspace_id, "member_id": body.user_id},
        )
        return self._member_dto(member)

    async def update_member(
        self,
        access: WorkspaceAccess,
        user_id: str,
        body: WorkspaceMemberUpdateRequest,
    ) -> WorkspaceMember:
        """Change one role without letting space admins escape their boundary."""
        member = await self._repository.get_member(access.workspace_id, user_id)
        if member is None:
            raise self._member_not_found()
        if member.role == "space_admin" and access.role != "global_admin":
            raise self._role_locked()
        if body.role == "space_admin" and access.role != "global_admin":
            raise self._forbidden("space admins cannot grant space_admin")
        if (
            member.role == "space_admin"
            and body.role != "space_admin"
            and await self._repository.space_admin_count(access.workspace_id) <= 1
        ):
            raise self._role_locked()
        updated = await self._repository.update_member_role(
            access.workspace_id,
            user_id,
            body.role,
        )
        if updated is None:
            raise self._member_not_found()
        return self._member_dto(updated)

    async def remove_member(self, access: WorkspaceAccess, user_id: str) -> None:
        """Remove one member while preserving the last-space-admin invariant."""
        member = await self._repository.get_member(access.workspace_id, user_id)
        if member is None:
            raise self._member_not_found()
        if member.role == "space_admin":
            if access.role != "global_admin":
                raise self._role_locked()
            if await self._repository.space_admin_count(access.workspace_id) <= 1:
                raise self._role_locked()
        if not await self._repository.remove_member(access.workspace_id, user_id):
            raise self._member_not_found()

    async def appoint_self(self, access: WorkspaceAccess, user_id: str) -> WorkspaceMember:
        """Write a real space-admin row for the global administrator, idempotently."""
        if access.role != "global_admin":
            raise self._forbidden("only the global administrator may appoint itself")
        member = await self._repository.upsert_space_admin(access.workspace_id, user_id)
        return self._member_dto(member)

    async def list_credentials(self, workspace_id: str) -> list[WorkspaceCredential]:
        """Return every credential row, including revoked ones."""
        return [
            self._credential_dto(record)
            for record in await self._repository.list_credentials(workspace_id)
        ]

    async def create_credential(
        self,
        access: WorkspaceAccess,
        *,
        created_by: str,
    ) -> WorkspaceCredentialCreated:
        """Mint one credential and return its plaintext exactly once."""
        active = await self._repository.active_credential_count(access.workspace_id)
        if active >= CREDENTIAL_ACTIVE_LIMIT:
            raise AppError(
                status_code=409,
                code=ErrorCode.CREDENTIAL_LIMIT,
                message="at most three active credentials are allowed",
            )
        credential = CREDENTIAL_TOKEN_PREFIX + secrets.token_urlsafe(32)
        prefix = credential[:CREDENTIAL_PREFIX_LENGTH]
        record = await self._repository.create_credential(
            workspace_id=access.workspace_id,
            credential_hash=hashlib.sha256(credential.encode()).hexdigest(),
            prefix=prefix,
            created_by=created_by,
        )
        logger.info(
            "workspace credential created",
            extra={
                "workspace_id": access.workspace_id,
                "credential_id": record.id,
            },
        )
        return WorkspaceCredentialCreated(
            credential_id=record.id,
            prefix=record.prefix,
            credential=credential,
        )

    async def revoke_credential(
        self,
        workspace_id: str,
        credential_id: str,
    ) -> None:
        """Revoke one credential; an already revoked row stays idempotent."""
        record = await self._repository.get_credential(workspace_id, credential_id)
        if record is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.CREDENTIAL_NOT_FOUND,
                message="credential was not found",
            )
        if record.revoked_at is None:
            await self._repository.revoke_credential(workspace_id, credential_id)

    async def verify_credential(self, credential: str | None) -> WorkspaceCredentialAccess:
        """Resolve one ingest credential to its workspace or fail closed."""
        if not credential or not credential.startswith(CREDENTIAL_TOKEN_PREFIX):
            raise self._credential_invalid()
        digest = hashlib.sha256(credential.encode()).hexdigest()
        record = await self._repository.find_active_credential_by_hash(digest)
        if record is None:
            raise self._credential_invalid()
        return WorkspaceCredentialAccess(
            workspace_id=record.workspace_id,
            credential_id=record.id,
        )

    async def touch_credential(self, credential_id: str) -> None:
        """Record one successful ingest without ever failing the report.

        `last_used_at` is diagnostic only, so the update is throttled to one
        write per minute and a failure is logged instead of surfacing as a 500
        after the bad case was already committed.
        """
        now = now_shanghai()
        try:
            await self._repository.touch_credential(
                credential_id,
                now=now,
                not_before=now - timedelta(seconds=CREDENTIAL_TOUCH_SECONDS),
            )
        except Exception:
            logger.warning(
                "workspace credential last-used update failed",
                extra={"credential_id": credential_id},
                exc_info=True,
            )

    @staticmethod
    def _validated_knowledge_roots(values: list[str]) -> tuple[str, ...]:
        """Canonicalize configured roots or fail with one stable public code."""
        try:
            return normalize_knowledge_roots(values)
        except KnowledgeRootError as exc:
            raise AppError(
                status_code=422,
                code=ErrorCode.KNOWLEDGE_ROOTS_INVALID,
                message="knowledge roots are invalid",
                details={"reason": exc.reason},
            ) from exc

    @staticmethod
    def _effective_role(stored_role: str | None) -> WorkspaceRole:
        """Derive the public role for a visible workspace row."""
        if stored_role is None:
            return "global_admin"
        return effective_role(stored_role)

    def _workspace_dto(
        self,
        workspace: WorkspaceRecord,
        *,
        used: int,
        member_count: int,
        space_admins: list[WorkspaceAdmin],
    ) -> Workspace:
        """Assemble the full workspace response from one row and its aggregates."""
        return Workspace(
            id=workspace.id,
            name=workspace.name,
            mark=workspace.mark,
            quota=workspace.quota,
            used=used,
            member_count=member_count,
            space_admins=space_admins,
            knowledge_roots=list(workspace.knowledge_roots),
            created_at=workspace.created_at,
        )

    @staticmethod
    def _admin_dto(admin: WorkspaceAdminRecord) -> WorkspaceAdmin:
        """Convert one space-admin join row into the public identity."""
        return WorkspaceAdmin(
            id=admin.id,
            display_name=admin.display_name,
        )

    @staticmethod
    def _member_dto(member: WorkspaceMemberRecord) -> WorkspaceMember:
        """Convert one persisted membership row into the public contract."""
        return WorkspaceMember(
            workspace_id=member.workspace_id,
            user_id=member.user_id,
            username=member.username,
            display_name=member.display_name,
            role=cast(WorkspaceMemberRole, effective_role(member.role)),
            joined_at=member.joined_at,
            updated_at=member.updated_at,
        )

    @staticmethod
    def _credential_dto(record: WorkspaceCredentialRecord) -> WorkspaceCredential:
        """Convert one persisted credential without exposing its plaintext."""
        return WorkspaceCredential(
            id=record.id,
            prefix=record.prefix,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
            revoked_at=record.revoked_at,
        )

    @staticmethod
    def _not_found() -> AppError:
        """Return the uniform invisible-or-missing workspace failure."""
        return AppError(
            status_code=404,
            code=ErrorCode.WORKSPACE_NOT_FOUND,
            message="workspace was not found",
        )

    @staticmethod
    def _forbidden(message: str) -> AppError:
        """Return the role-insufficient failure used by workspace administration."""
        return AppError(
            status_code=403,
            code=ErrorCode.WORKSPACE_FORBIDDEN,
            message=message,
        )

    @staticmethod
    def _member_not_found() -> AppError:
        """Return the missing-membership failure for member mutation routes."""
        return AppError(
            status_code=404,
            code=ErrorCode.MEMBER_NOT_FOUND,
            message="workspace member was not found",
        )

    @staticmethod
    def _role_locked() -> AppError:
        """Return the invariant failure for protected space-admin rows."""
        return AppError(
            status_code=409,
            code=ErrorCode.ROLE_LOCKED,
            message="space_admin rows are protected",
        )

    @staticmethod
    def _role_invalid(message: str) -> AppError:
        """Return the invalid-role or unknown-user failure."""
        return AppError(
            status_code=422,
            code=ErrorCode.ROLE_INVALID,
            message=message,
        )

    @staticmethod
    def _workspace_exists() -> AppError:
        """Return the duplicate workspace-name failure."""
        return AppError(
            status_code=409,
            code=ErrorCode.WORKSPACE_EXISTS,
            message="workspace name already exists",
        )

    @staticmethod
    def _quota_invalid(*, quota: int, used: int) -> AppError:
        """Return the quota failure with its live usage context."""
        return AppError(
            status_code=422,
            code=ErrorCode.QUOTA_INVALID,
            message="quota must be non-negative and not below current usage",
            details={"quota": quota, "used": used},
        )

    @staticmethod
    def _credential_invalid() -> AppError:
        """Return the missing, unknown, or revoked credential failure."""
        return AppError(
            status_code=401,
            code=ErrorCode.CREDENTIAL_INVALID,
            message="workspace credential is invalid",
        )
