"""Persistence for workspace label rules and derived badcase assignments."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, insert, literal, select, update
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Database
from app.db.models.domain import (
    bad_cases,
    workspace_bad_case_labels,
    workspace_bad_cases,
)
from app.db.models.workspace import workspaces
from app.utils.time import now_shanghai

CATALOG_ASSIGNMENT_SOURCE = "catalog_label"


@dataclass(frozen=True, slots=True)
class WorkspaceBadCaseLabelRecord:
    """One complete label configuration and its distinct visible case count."""

    items: tuple[str, ...]
    assigned_bad_case_count: int


@dataclass(frozen=True, slots=True)
class BadCaseLabelSuggestionRecord:
    """One public catalog label and the number of cases currently carrying it."""

    label: str
    bad_case_count: int


def _escape_like(value: str) -> str:
    """Treat user-provided LIKE metacharacters as literal text."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class WorkspaceBadCaseLabelRepository:
    """Atomically replace label rules and their derived historical assignments."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database boundary."""
        self._database = database

    async def get(self, workspace_id: str) -> WorkspaceBadCaseLabelRecord:
        """Return sorted rules and the distinct assigned badcase count."""
        async with self._database.session() as session:
            labels: Sequence[str] = (
                (
                    await session.execute(
                        select(workspace_bad_case_labels.c.label)
                        .where(workspace_bad_case_labels.c.workspace_id == workspace_id)
                        .order_by(workspace_bad_case_labels.c.label),
                    )
                )
                .scalars()
                .all()
            )
            assigned_count = int(
                (
                    await session.execute(
                        select(func.count(func.distinct(workspace_bad_cases.c.bad_case_id))).where(
                            workspace_bad_cases.c.workspace_id == workspace_id,
                        ),
                    )
                ).scalar_one(),
            )
        return WorkspaceBadCaseLabelRecord(
            items=tuple(labels),
            assigned_bad_case_count=assigned_count,
        )

    async def suggestions(
        self,
        prefix: str | None,
        limit: int,
    ) -> Sequence[BadCaseLabelSuggestionRecord]:
        """Return the most common public labels, optionally restricted to a prefix.

        The prefix comparison follows the database's default case-insensitive
        ``LIKE`` semantic (SQLite ASCII and MySQL's default collation agree),
        while grouping and tie-breaking use the exact label bytes so ``Review``
        and ``review`` remain separate rows with their own counts.
        """
        conditions: list[ColumnElement[bool]] = [
            bad_cases.c.catalog_label.is_not(None),
            bad_cases.c.catalog_label != "",
        ]
        if prefix:
            conditions.append(
                bad_cases.c.catalog_label.like(
                    f"{_escape_like(prefix)}%",
                    escape="\\",
                ),
            )
        catalog_expression: ColumnElement[str] = bad_cases.c.catalog_label
        if self._database.dialect == "mysql":
            # MySQL's default case-insensitive collation would merge the two
            # casings; pin exact grouping/order to binary comparison so the
            # result matches SQLite's default BINARY collation.
            catalog_expression = catalog_expression.collate("utf8mb4_bin")
        statement = (
            select(
                catalog_expression.label("catalog_label"),
                func.count().label("bad_case_count"),
            )
            .where(*conditions)
            .group_by(catalog_expression)
            .order_by(func.count().desc(), catalog_expression)
            .limit(limit)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [
            BadCaseLabelSuggestionRecord(
                label=str(row["catalog_label"]),
                bad_case_count=int(row["bad_case_count"]),
            )
            for row in rows
        ]

    async def replace(
        self,
        workspace_id: str,
        labels: Sequence[str],
    ) -> WorkspaceBadCaseLabelRecord | None:
        """Replace rules and rebuild catalog assignments in one transaction."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            if self._database.dialect == "sqlite":
                # SQLite has no row locks; a no-op write takes the database
                # write lock so concurrent replacements serialize like MySQL.
                await session.execute(
                    update(workspaces)
                    .where(workspaces.c.id == workspace_id)
                    .values(updated_at=workspaces.c.updated_at),
                )
            workspace_exists = (
                await session.execute(
                    select(workspaces.c.id)
                    .where(workspaces.c.id == workspace_id)
                    .with_for_update(),
                )
            ).scalar_one_or_none()
            if workspace_exists is None:
                return None

            await session.execute(
                delete(workspace_bad_case_labels).where(
                    workspace_bad_case_labels.c.workspace_id == workspace_id,
                ),
            )
            if labels:
                await session.execute(
                    insert(workspace_bad_case_labels),
                    [
                        {
                            "workspace_id": workspace_id,
                            "label": label,
                            "created_at": now,
                            "updated_at": now,
                        }
                        for label in labels
                    ],
                )

            await session.execute(
                delete(workspace_bad_cases).where(
                    workspace_bad_cases.c.workspace_id == workspace_id,
                    workspace_bad_cases.c.assignment_source == CATALOG_ASSIGNMENT_SOURCE,
                ),
            )
            if labels:
                matching_cases = (
                    select(
                        literal(workspace_id),
                        bad_cases.c.bad_case_id,
                        literal(CATALOG_ASSIGNMENT_SOURCE),
                        bad_cases.c.catalog_label,
                        literal(now),
                    )
                    .select_from(
                        bad_cases.join(
                            workspace_bad_case_labels,
                            workspace_bad_case_labels.c.label == bad_cases.c.catalog_label,
                        ),
                    )
                    .where(workspace_bad_case_labels.c.workspace_id == workspace_id)
                )
                await session.execute(
                    insert(workspace_bad_cases).from_select(
                        [
                            "workspace_id",
                            "bad_case_id",
                            "assignment_source",
                            "label",
                            "assigned_at",
                        ],
                        matching_cases,
                    ),
                )

            assigned_count = int(
                (
                    await session.execute(
                        select(func.count(func.distinct(workspace_bad_cases.c.bad_case_id))).where(
                            workspace_bad_cases.c.workspace_id == workspace_id,
                        ),
                    )
                ).scalar_one(),
            )

        return WorkspaceBadCaseLabelRecord(
            items=tuple(labels),
            assigned_bad_case_count=assigned_count,
        )
