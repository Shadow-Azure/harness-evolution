"""Add knowledge-document trigger columns and workspace knowledge roots.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-16
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | None = None
depends_on: str | None = None

EVENT_KNOWLEDGE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("document_id", sa.String(length=255), nullable=True),
    sa.Column("document_revision", sa.String(length=96), nullable=True),
    sa.Column("source_path", sa.String(length=1024), nullable=True),
    sa.Column("retrieval_kind", sa.String(length=32), nullable=True),
    sa.Column("retrieval_scope", sa.String(length=255), nullable=True),
)
WORKSPACE_KNOWLEDGE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("knowledge_roots", sa.JSON(), nullable=True),
)
INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "ix_agent_events_knowledge_document",
        "agent_events",
        ("agent_id", "kind", "document_id"),
    ),
)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return the reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def _add_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Add missing columns and reject an existing column with wrong nullability."""
    existing = _existing_columns(table)
    for column in columns:
        current = existing.get(str(column.name))
        if current is None:
            op.add_column(table, column)
            continue
        if bool(current["nullable"]) != bool(column.nullable):
            raise RuntimeError(
                f"{table}.{column.name} already exists with "
                f"nullable={bool(current['nullable'])}, expected "
                f"nullable={bool(column.nullable)}; repair the column before retrying 0019",
            )


def _existing_indexes(table: str) -> set[str]:
    """Return the reflected index names on one table."""
    return {
        str(index["name"])
        for index in inspect(op.get_bind()).get_indexes(table)
        if index.get("name") is not None
    }


def _create_indexes() -> None:
    """Create the knowledge indexes that are still missing."""
    existing = _existing_indexes("agent_events")
    for name, table, columns in INDEXES:
        if name in existing:
            continue
        op.create_index(name, table, list(columns))


def upgrade() -> None:
    """Add knowledge evidence and workspace roots without touching existing rows.

    Existing events read NULL knowledge columns until the next parser-5 replay;
    existing workspaces read a NULL root list, which the workspace repository
    maps to an empty tuple. JSON columns carry no server default for cross-dialect
    consistency; the application writes ``[]`` explicitly. MySQL DDL auto-commits,
    so each addition is guarded to let a retry after a partial failure resume.
    """
    _add_columns("agent_events", EVENT_KNOWLEDGE_COLUMNS)
    _add_columns("workspaces", WORKSPACE_KNOWLEDGE_COLUMNS)
    _create_indexes()


def _drop_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Drop knowledge columns that are still present, recreating SQLite tables."""
    existing = _existing_columns(table)
    present = tuple(column.name for column in columns if column.name in existing)
    if not present:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            for column in present:
                batch_op.drop_column(column)
        return
    for column in present:
        op.drop_column(table, column)


def _drop_indexes() -> None:
    """Drop knowledge indexes that are still present."""
    existing = _existing_indexes("agent_events")
    for name, _table, _columns in INDEXES:
        if name in existing:
            op.drop_index(name, table_name="agent_events")


def downgrade() -> None:
    """Remove every knowledge column and index added by this revision."""
    _drop_indexes()
    _drop_columns("agent_events", EVENT_KNOWLEDGE_COLUMNS)
    _drop_columns("workspaces", WORKSPACE_KNOWLEDGE_COLUMNS)
