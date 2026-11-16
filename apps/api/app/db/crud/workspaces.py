"""Dialect-neutral persistence for workspaces, members, and session aggregates."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import case, delete, func, insert, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.crud.acquisition_replay import bad_cases_table_present
from app.db.crud.integrity import is_unique_violation
from app.db.models.domain import bad_cases, source_records
from app.db.models.users import users
from app.db.models.workspace import (
    workspace_ingest_credentials,
    workspace_members,
    workspaces,
)
from app.utils.ids import new_id
from app.utils.knowledge_paths import decode_knowledge_roots
from app.utils.time import as_shanghai, now_shanghai


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    """One workspace row without its aggregates."""

    id: str
    name: str
    mark: str
    quota: int
    status: str
    knowledge_roots: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceMembership:
    """One user-to-workspace membership row."""

    workspace_id: str
    user_id: str
    role: str
    joined_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VisibleWorkspace:
    """A workspace the current user may see plus the stored membership role.

    ``role`` stays ``None`` for a global administrator, who passes through
    without owning a membership row.
    """

    workspace: WorkspaceRecord
    role: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceMemberCounts:
    """Member totals for one workspace."""

    member_count: int
    space_admin_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceMemberRecord:
    """One membership joined with the user's public identity."""

    workspace_id: str
    user_id: str
    username: str
    display_name: str
    role: str
    joined_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceAdminRecord:
    """One space administrator's minimal identity."""

    id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class WorkspaceUserRecord:
    """One user row as seen by workspace administration."""

    id: str
    username: str
    display_name: str
    role: str
    active: bool


@dataclass(frozen=True, slots=True)
class MemberCandidateRecord:
    """One non-member user returned by the server-side candidate search."""

    id: str
    username: str
    display_name: str
    active: bool


@dataclass(frozen=True, slots=True)
class WorkspaceCredentialRecord:
    """One ingest credential row without its plaintext secret."""

    id: str
    workspace_id: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class WorkspaceNameConflict(Exception):
    """The workspace name is already taken."""


class MemberAlreadyExists(Exception):
    """The user already owns a membership row in this workspace."""


def _workspace_from_row(row: Any) -> WorkspaceRecord:
    """Translate one workspace row mapping into its record."""
    return WorkspaceRecord(
        id=row["id"],
        name=row["name"],
        mark=row["mark"],
        quota=row["quota"],
        status=row["status"],
        knowledge_roots=decode_knowledge_roots(row["knowledge_roots"]),
        created_at=as_shanghai(row["created_at"]),
        updated_at=as_shanghai(row["updated_at"]),
    )


def _membership_from_row(row: Any) -> WorkspaceMembership:
    """Translate one membership row mapping into its record."""
    return WorkspaceMembership(
        workspace_id=row["workspace_id"],
        user_id=row["user_id"],
        role=row["role"],
        joined_at=as_shanghai(row["joined_at"]),
        updated_at=as_shanghai(row["updated_at"]),
    )


def _member_from_row(row: Any) -> WorkspaceMemberRecord:
    """Translate one joined membership row into its public record."""
    return WorkspaceMemberRecord(
        workspace_id=row["workspace_id"],
        user_id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        joined_at=as_shanghai(row["joined_at"]),
        updated_at=as_shanghai(row["updated_at"]),
    )


def _credential_from_row(row: Any) -> WorkspaceCredentialRecord:
    """Translate one credential row into its secret-free record."""
    last_used_at = row["last_used_at"]
    revoked_at = row["revoked_at"]
    return WorkspaceCredentialRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        prefix=row["credential_prefix"],
        created_at=as_shanghai(row["created_at"]),
        last_used_at=as_shanghai(last_used_at) if last_used_at is not None else None,
        revoked_at=as_shanghai(revoked_at) if revoked_at is not None else None,
    )


class WorkspaceRepository:
    """Read workspace authority and write workspace administration rows."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database boundary."""
        self._database = database

    async def get(self, workspace_id: str) -> WorkspaceRecord | None:
        """Return one workspace by stable identifier, visible or not."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(workspaces).where(workspaces.c.id == workspace_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _workspace_from_row(row) if row else None

    async def get_membership(
        self,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceMembership | None:
        """Return one user's membership row for a workspace."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(workspace_members).where(
                            workspace_members.c.workspace_id == workspace_id,
                            workspace_members.c.user_id == user_id,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _membership_from_row(row) if row else None

    async def list_visible(
        self,
        *,
        user_id: str,
        include_all: bool,
        limit: int | None = None,
    ) -> list[VisibleWorkspace]:
        """Return at most ``limit`` spaces, or every visible space when unset."""
        if limit is not None and limit < 1:
            raise ValueError("workspace list limit must be positive")
        order = (workspaces.c.created_at.desc(), workspaces.c.id)
        async with self._database.session() as session:
            if include_all:
                statement = select(workspaces).order_by(*order)
                if limit is not None:
                    statement = statement.limit(limit)
                rows = (await session.execute(statement)).mappings().all()
                return [
                    VisibleWorkspace(workspace=_workspace_from_row(row), role=None) for row in rows
                ]
            joined = (
                select(workspaces, workspace_members.c.role)
                .join(
                    workspace_members,
                    workspace_members.c.workspace_id == workspaces.c.id,
                )
                .where(workspace_members.c.user_id == user_id)
                .order_by(*order)
            )
            if limit is not None:
                joined = joined.limit(limit)
            visible_rows = (await session.execute(joined)).mappings().all()
        return [
            VisibleWorkspace(
                workspace=_workspace_from_row(row),
                role=str(row["role"]),
            )
            for row in visible_rows
        ]

    async def used_counts(self, workspace_ids: Sequence[str]) -> dict[str, int]:
        """Return live bad-case counts grouped by the requested workspaces."""
        if not workspace_ids:
            return {}
        statement = (
            select(
                bad_cases.c.workspace_id.label("workspace_id"),
                func.count().label("case_count"),
            )
            .where(bad_cases.c.workspace_id.in_(workspace_ids))
            .group_by(bad_cases.c.workspace_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return {str(row["workspace_id"]): int(row["case_count"]) for row in rows}

    async def used_count(self, workspace_id: str) -> int:
        """Return one workspace's live bad-case count for quota checks."""
        async with self._database.session() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(bad_cases)
                        .where(bad_cases.c.workspace_id == workspace_id),
                    )
                ).scalar_one(),
            )

    async def member_counts(
        self,
        workspace_ids: Sequence[str],
    ) -> dict[str, WorkspaceMemberCounts]:
        """Return member and space-admin totals grouped by the requested workspaces."""
        if not workspace_ids:
            return {}
        statement = (
            select(
                workspace_members.c.workspace_id.label("workspace_id"),
                func.count().label("member_count"),
                func.sum(
                    case((workspace_members.c.role == "space_admin", 1), else_=0),
                ).label("space_admin_count"),
            )
            .where(workspace_members.c.workspace_id.in_(workspace_ids))
            .group_by(workspace_members.c.workspace_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return {
            str(row["workspace_id"]): WorkspaceMemberCounts(
                member_count=int(row["member_count"]),
                space_admin_count=int(row["space_admin_count"] or 0),
            )
            for row in rows
        }

    async def list_space_admins(
        self,
        workspace_ids: Sequence[str],
    ) -> dict[str, list[WorkspaceAdminRecord]]:
        """Return space administrators grouped by workspace in join order."""
        if not workspace_ids:
            return {}
        statement = (
            select(
                workspace_members.c.workspace_id,
                users.c.id,
                users.c.display_name,
            )
            .join(users, users.c.id == workspace_members.c.user_id)
            .where(
                workspace_members.c.workspace_id.in_(workspace_ids),
                workspace_members.c.role == "space_admin",
            )
            .order_by(workspace_members.c.joined_at, users.c.id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        grouped: dict[str, list[WorkspaceAdminRecord]] = {wid: [] for wid in workspace_ids}
        for row in rows:
            grouped[str(row["workspace_id"])].append(
                WorkspaceAdminRecord(
                    id=str(row["id"]),
                    display_name=str(row["display_name"]),
                ),
            )
        return grouped

    async def create_workspace(
        self,
        *,
        name: str,
        mark: str,
        quota: int,
        created_by: str,
        space_admin_ids: Sequence[str],
        knowledge_roots: Sequence[str] = (),
    ) -> WorkspaceRecord:
        """Insert one workspace and its initial administrators atomically."""
        workspace_id = new_id()
        now = now_shanghai()
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(workspaces).values(
                        id=workspace_id,
                        name=name,
                        mark=mark,
                        quota=quota,
                        status="active",
                        knowledge_roots=list(knowledge_roots),
                        created_by=created_by,
                        created_at=now,
                        updated_at=now,
                    ),
                )
            except IntegrityError as exc:
                if not is_unique_violation(exc):
                    raise
                raise WorkspaceNameConflict from exc
            for user_id in space_admin_ids:
                await session.execute(
                    insert(workspace_members).values(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role="space_admin",
                        joined_at=now,
                        updated_at=now,
                    ),
                )
        created = await self.get(workspace_id)
        if created is None:
            raise RuntimeError("created workspace disappeared before response")
        return created

    async def update_workspace(
        self,
        workspace_id: str,
        values: Mapping[str, object],
    ) -> WorkspaceRecord | None:
        """Apply one partial update and surface only name conflicts."""
        if values:
            values = {**values, "updated_at": now_shanghai()}
            async with self._database.transaction() as session:
                try:
                    await session.execute(
                        update(workspaces).where(workspaces.c.id == workspace_id).values(**values),
                    )
                except IntegrityError as exc:
                    if not is_unique_violation(exc):
                        raise
                    raise WorkspaceNameConflict from exc
        return await self.get(workspace_id)

    async def invalidate_reported_root_parsers(self, workspace_id: str) -> int:
        """Mark this workspace's reported root sessions for the next replay.

        Configuration is not part of a payload hash, so a workspace that changes
        its knowledge roots must clear the parser cursor of the roots it reported;
        otherwise parser-5 sessions would never be re-evaluated. Returns the
        number of cleared cursors and skips silently when the problem-side table
        is absent.
        """
        if not await bad_cases_table_present(self._database):
            return 0
        root_ids = select(bad_cases.c.bad_case_session_id).where(
            bad_cases.c.workspace_id == workspace_id,
        )
        async with self._database.transaction() as session:
            result = await session.execute(
                update(source_records)
                .where(source_records.c.root_session_id.in_(root_ids))
                .values(parser_version=None),
            )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def list_members(self, workspace_id: str) -> list[WorkspaceMemberRecord]:
        """Return members ordered by role rank, then join time."""
        role_rank = case(
            (workspace_members.c.role == "space_admin", 0),
            (workspace_members.c.role == "member", 1),
            else_=2,
        )
        statement = (
            select(
                workspace_members.c.workspace_id,
                workspace_members.c.user_id,
                users.c.username,
                users.c.display_name,
                workspace_members.c.role,
                workspace_members.c.joined_at,
                workspace_members.c.updated_at,
            )
            .join(users, users.c.id == workspace_members.c.user_id)
            .where(workspace_members.c.workspace_id == workspace_id)
            .order_by(role_rank, workspace_members.c.joined_at, workspace_members.c.user_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [_member_from_row(row) for row in rows]

    async def get_member(
        self,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceMemberRecord | None:
        """Return one membership joined with the user's public identity."""
        statement = (
            select(
                workspace_members.c.workspace_id,
                workspace_members.c.user_id,
                users.c.username,
                users.c.display_name,
                workspace_members.c.role,
                workspace_members.c.joined_at,
                workspace_members.c.updated_at,
            )
            .join(users, users.c.id == workspace_members.c.user_id)
            .where(
                workspace_members.c.workspace_id == workspace_id,
                workspace_members.c.user_id == user_id,
            )
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _member_from_row(row) if row is not None else None

    async def space_admin_count(self, workspace_id: str) -> int:
        """Return how many space administrators currently belong to a workspace."""
        async with self._database.session() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(workspace_members)
                        .where(
                            workspace_members.c.workspace_id == workspace_id,
                            workspace_members.c.role == "space_admin",
                        ),
                    )
                ).scalar_one(),
            )

    async def get_user(self, user_id: str) -> WorkspaceUserRecord | None:
        """Return one user row for membership validation."""
        async with self._database.session() as session:
            row = (
                (await session.execute(select(users).where(users.c.id == user_id)))
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return WorkspaceUserRecord(
            id=str(row["id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            active=bool(row["is_active"]),
        )

    async def users_by_ids(
        self,
        user_ids: Sequence[str],
    ) -> dict[str, WorkspaceUserRecord]:
        """Return the known users among the requested ids."""
        if not user_ids:
            return {}
        async with self._database.session() as session:
            rows = (
                (await session.execute(select(users).where(users.c.id.in_(user_ids))))
                .mappings()
                .all()
            )
        return {
            str(row["id"]): WorkspaceUserRecord(
                id=str(row["id"]),
                username=str(row["username"]),
                display_name=str(row["display_name"]),
                role=str(row["role"]),
                active=bool(row["is_active"]),
            )
            for row in rows
        }

    async def search_member_candidates(
        self,
        workspace_id: str,
        query: str,
        limit: int,
    ) -> list[MemberCandidateRecord]:
        """Return non-members matching the username or display-name search."""
        normalized = query.strip().lower()
        if not normalized:
            return []
        member_ids = select(workspace_members.c.user_id).where(
            workspace_members.c.workspace_id == workspace_id,
        )
        statement = (
            select(users.c.id, users.c.username, users.c.display_name, users.c.is_active)
            .where(
                users.c.id.not_in(member_ids),
                or_(
                    func.lower(users.c.username).contains(normalized, autoescape=True),
                    func.lower(users.c.display_name).contains(normalized, autoescape=True),
                ),
            )
            .order_by(users.c.username, users.c.id)
            .limit(limit)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [
            MemberCandidateRecord(
                id=str(row["id"]),
                username=str(row["username"]),
                display_name=str(row["display_name"]),
                active=bool(row["is_active"]),
            )
            for row in rows
        ]

    async def add_member(
        self,
        *,
        workspace_id: str,
        user_id: str,
        role: str,
    ) -> WorkspaceMemberRecord:
        """Insert one membership row and surface duplicates as a stable conflict."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(workspace_members).values(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role=role,
                        joined_at=now,
                        updated_at=now,
                    ),
                )
            except IntegrityError as exc:
                if not is_unique_violation(exc):
                    raise
                raise MemberAlreadyExists from exc
        member = await self.get_member(workspace_id, user_id)
        if member is None:
            raise RuntimeError("created membership disappeared before response")
        return member

    async def update_member_role(
        self,
        workspace_id: str,
        user_id: str,
        role: str,
    ) -> WorkspaceMemberRecord | None:
        """Change one existing membership's role."""
        async with self._database.transaction() as session:
            await session.execute(
                update(workspace_members)
                .where(
                    workspace_members.c.workspace_id == workspace_id,
                    workspace_members.c.user_id == user_id,
                )
                .values(role=role, updated_at=now_shanghai()),
            )
        return await self.get_member(workspace_id, user_id)

    async def remove_member(self, workspace_id: str, user_id: str) -> bool:
        """Delete one membership row and report whether it existed."""
        async with self._database.transaction() as session:
            result = await session.execute(
                delete(workspace_members).where(
                    workspace_members.c.workspace_id == workspace_id,
                    workspace_members.c.user_id == user_id,
                ),
            )
            removed = cast(CursorResult[Any], result).rowcount or 0
        return removed > 0

    async def upsert_space_admin(
        self,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceMemberRecord:
        """Insert a real space-admin row or promote the existing membership."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            existing = (
                await session.execute(
                    select(workspace_members.c.user_id).where(
                        workspace_members.c.workspace_id == workspace_id,
                        workspace_members.c.user_id == user_id,
                    ),
                )
            ).scalar_one_or_none()
            if existing is None:
                await session.execute(
                    insert(workspace_members).values(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role="space_admin",
                        joined_at=now,
                        updated_at=now,
                    ),
                )
            else:
                await session.execute(
                    update(workspace_members)
                    .where(
                        workspace_members.c.workspace_id == workspace_id,
                        workspace_members.c.user_id == user_id,
                    )
                    .values(role="space_admin", updated_at=now),
                )
        member = await self.get_member(workspace_id, user_id)
        if member is None:
            raise RuntimeError("appointed membership disappeared before response")
        return member

    async def list_credentials(
        self,
        workspace_id: str,
    ) -> list[WorkspaceCredentialRecord]:
        """Return every credential row, newest first, including revoked rows."""
        statement = (
            select(workspace_ingest_credentials)
            .where(workspace_ingest_credentials.c.workspace_id == workspace_id)
            .order_by(
                workspace_ingest_credentials.c.created_at.desc(),
                workspace_ingest_credentials.c.id,
            )
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [_credential_from_row(row) for row in rows]

    async def active_credential_count(self, workspace_id: str) -> int:
        """Return how many non-revoked credentials a workspace still owns."""
        async with self._database.session() as session:
            return int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(workspace_ingest_credentials)
                        .where(
                            workspace_ingest_credentials.c.workspace_id == workspace_id,
                            workspace_ingest_credentials.c.revoked_at.is_(None),
                        ),
                    )
                ).scalar_one(),
            )

    async def create_credential(
        self,
        *,
        workspace_id: str,
        credential_hash: str,
        prefix: str,
        created_by: str,
    ) -> WorkspaceCredentialRecord:
        """Insert one hashed credential and return its secret-free row."""
        credential_id = new_id()
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                insert(workspace_ingest_credentials).values(
                    id=credential_id,
                    workspace_id=workspace_id,
                    credential_hash=credential_hash,
                    credential_prefix=prefix,
                    created_by=created_by,
                    created_at=now,
                ),
            )
        return WorkspaceCredentialRecord(
            id=credential_id,
            workspace_id=workspace_id,
            prefix=prefix,
            created_at=now,
            last_used_at=None,
            revoked_at=None,
        )

    async def get_credential(
        self,
        workspace_id: str,
        credential_id: str,
    ) -> WorkspaceCredentialRecord | None:
        """Return one credential only when it belongs to the workspace."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(workspace_ingest_credentials).where(
                            workspace_ingest_credentials.c.id == credential_id,
                            workspace_ingest_credentials.c.workspace_id == workspace_id,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _credential_from_row(row) if row is not None else None

    async def revoke_credential(
        self,
        workspace_id: str,
        credential_id: str,
    ) -> bool:
        """Mark one credential revoked; only an active row changes."""
        async with self._database.transaction() as session:
            result = await session.execute(
                update(workspace_ingest_credentials)
                .where(
                    workspace_ingest_credentials.c.id == credential_id,
                    workspace_ingest_credentials.c.workspace_id == workspace_id,
                    workspace_ingest_credentials.c.revoked_at.is_(None),
                )
                .values(revoked_at=now_shanghai()),
            )
            changed = cast(CursorResult[Any], result).rowcount or 0
        return changed > 0

    async def touch_credential(
        self,
        credential_id: str,
        *,
        now: datetime,
        not_before: datetime,
    ) -> bool:
        """Record one successful ingest unless a recent touch already did."""
        async with self._database.transaction() as session:
            result = await session.execute(
                update(workspace_ingest_credentials)
                .where(
                    workspace_ingest_credentials.c.id == credential_id,
                    or_(
                        workspace_ingest_credentials.c.last_used_at.is_(None),
                        workspace_ingest_credentials.c.last_used_at <= not_before,
                    ),
                )
                .values(last_used_at=as_shanghai(now)),
            )
            changed = cast(CursorResult[Any], result).rowcount or 0
        return changed > 0

    async def find_active_credential_by_hash(
        self,
        credential_hash: str,
    ) -> WorkspaceCredentialRecord | None:
        """Return one non-revoked credential by its SHA-256 hash."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(workspace_ingest_credentials).where(
                            workspace_ingest_credentials.c.credential_hash == credential_hash,
                            workspace_ingest_credentials.c.revoked_at.is_(None),
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _credential_from_row(row) if row is not None else None
