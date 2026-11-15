"""Dialect-neutral persistence for workspaces, members, and session aggregates."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select

from app.db.base import Database
from app.db.models.domain import bad_cases
from app.db.models.workspace import workspace_members, workspaces
from app.utils.time import as_shanghai


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    """One workspace row without its aggregates."""

    id: str
    name: str
    mark: str
    quota: int
    status: str
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


def _workspace_from_row(row: Any) -> WorkspaceRecord:
    """Translate one workspace row mapping into its record."""
    return WorkspaceRecord(
        id=row["id"],
        name=row["name"],
        mark=row["mark"],
        quota=row["quota"],
        status=row["status"],
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


class WorkspaceRepository:
    """Read workspace authority and session aggregates in batched queries."""

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
        limit: int,
    ) -> list[VisibleWorkspace]:
        """Return at most ``limit`` spaces for a member or the global administrator."""
        if limit < 1:
            raise ValueError("workspace list limit must be positive")
        order = (workspaces.c.created_at.desc(), workspaces.c.id)
        async with self._database.session() as session:
            if include_all:
                rows = (
                    (await session.execute(select(workspaces).order_by(*order).limit(limit)))
                    .mappings()
                    .all()
                )
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
                .limit(limit)
            )
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
