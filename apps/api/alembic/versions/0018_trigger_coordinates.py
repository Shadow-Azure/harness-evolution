"""Add object trigger coordinates: tree index, triggered time, and object version.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-16
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None

AGENT_COORDINATE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column(
        "tree_index",
        sa.Integer(),
        nullable=False,
        server_default="0",
    ),
)
EVENT_COORDINATE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("object_version", sa.String(length=64), nullable=True),
)
INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_agent_events_agent_triggered", "agent_events", ("agent_id", "triggered_at")),
    (
        "ix_agent_events_object_version",
        "agent_events",
        ("agent_id", "kind", "name", "object_version"),
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
                f"nullable={bool(column.nullable)}; repair the column before retrying 0018",
            )


def _existing_indexes(table: str) -> set[str]:
    """Return the reflected index names on one table."""
    return {
        str(index["name"])
        for index in inspect(op.get_bind()).get_indexes(table)
        if index.get("name") is not None
    }


def _create_indexes() -> None:
    """Create the coordinate indexes that are still missing."""
    existing = _existing_indexes("agent_events")
    for name, table, columns in INDEXES:
        if name in existing:
            continue
        op.create_index(name, table, list(columns))


def upgrade() -> None:
    """Add nullable/backfilled coordinate columns without touching other evidence.

    Existing Agents read ``tree_index = 0`` until the next replay fills the DFS
    order; existing events keep NULL coordinates. MySQL DDL auto-commits, so each
    column addition is guarded to let a retry after a partial failure resume.
    """
    _add_columns("agents", AGENT_COORDINATE_COLUMNS)
    _add_columns("agent_events", EVENT_COORDINATE_COLUMNS)
    _create_indexes()


def _drop_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Drop coordinate columns that are still present, recreating SQLite tables."""
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
    """Drop coordinate indexes that are still present."""
    existing = _existing_indexes("agent_events")
    for name, _table, _columns in INDEXES:
        if name in existing:
            op.drop_index(name, table_name="agent_events")


def downgrade() -> None:
    """Remove every coordinate column and index added by this revision."""
    _drop_indexes()
    _drop_columns("agent_events", EVENT_COORDINATE_COLUMNS)
    _drop_columns("agents", AGENT_COORDINATE_COLUMNS)
