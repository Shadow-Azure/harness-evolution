"""Workspace visibility conditions shared by Session and bad-case read paths."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import inspect, select, true
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

from app.db.base import Database
from app.db.models.domain import bad_cases, session_families, workspace_bad_cases
from app.db.models.workspace import workspace_members


@dataclass(frozen=True, slots=True)
class WorkspaceReadScope:
    """One resolved workspace visibility scope for read repositories.

    The three scopes are exclusive in intent: a pinned ``workspace_id`` comes
    from an already-authorized workspace route, a ``user_id`` expands to that
    user's membership rows for the legacy endpoints, and ``all`` means every
    workspace because the caller is a global administrator. There is no default
    constructor on purpose, so an omitted scope cannot silently widen reads.
    """

    workspace_id: str | None
    user_id: str | None

    @classmethod
    def all_workspaces(cls) -> WorkspaceReadScope:
        """Return the scope used by a global administrator."""
        return cls(workspace_id=None, user_id=None)

    @classmethod
    def for_workspace(cls, workspace_id: str) -> WorkspaceReadScope:
        """Pin one workspace after ``require_workspace_role`` authorized it."""
        return cls(workspace_id=workspace_id, user_id=None)

    @classmethod
    def for_user(cls, *, user_id: str, role: str) -> WorkspaceReadScope:
        """Return membership scope, or every workspace for a global administrator."""
        if role == "admin":
            return cls.all_workspaces()
        return cls(workspace_id=None, user_id=user_id)

    def case_condition(self) -> ColumnElement[bool]:
        """Return the predicate selecting bad cases associated with this scope.

        Visibility comes from the ``workspace_bad_cases`` association, so one
        canonical case shared through a label is readable by every matching
        workspace while an unrelated space reads nothing. All bad-case and
        Session read paths must go through this boundary.
        """
        if self.workspace_id is not None:
            return (
                select(workspace_bad_cases.c.bad_case_id)
                .where(
                    workspace_bad_cases.c.workspace_id == self.workspace_id,
                    workspace_bad_cases.c.bad_case_id == bad_cases.c.bad_case_id,
                )
                .exists()
            )
        if self.user_id is not None:
            return bad_cases.c.bad_case_id.in_(
                select(workspace_bad_cases.c.bad_case_id).where(
                    workspace_bad_cases.c.workspace_id.in_(
                        select(workspace_members.c.workspace_id).where(
                            workspace_members.c.user_id == self.user_id,
                        ),
                    ),
                ),
            )
        return true()

    def session_condition(self) -> ColumnElement[bool]:
        """Keep only sessions projected from bad cases inside this scope."""
        return session_families.c.id.in_(
            select(bad_cases.c.bad_case_session_id).where(self.case_condition()),
        )


def scoped_case_ids(workspace_ids: Sequence[str]) -> Select[tuple[str]]:
    """Return the case ids associated with any of the explicit workspaces.

    Legacy unscoped compatibility routes resolve a workspace-id list first and
    then reuse this subquery instead of filtering ``bad_cases.workspace_id``.
    """
    return select(workspace_bad_cases.c.bad_case_id).where(
        workspace_bad_cases.c.workspace_id.in_(workspace_ids),
    )


async def bad_cases_table_present(database: Database) -> bool:
    """Return whether the external bad-case table exists in this installation.

    Bad cases are an externally bootstrapped table, so a fresh database can run
    the API before any bad case is ever reported. Read paths then degrade to an
    empty projection instead of failing the whole Session page.
    """

    async with database.engine.connect() as connection:
        return bool(
            await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table(
                    bad_cases.name,
                ),
            ),
        )
