"""Add M9 execution, relation, definition, and file-read evidence columns.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-16
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None

LEGACY_EXECUTION_OUTCOME = "legacy_unknown"

SESSION_EVIDENCE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column(
        "execution_outcome",
        sa.String(length=16),
        nullable=False,
        server_default=LEGACY_EXECUTION_OUTCOME,
    ),
    sa.Column("end_reason", sa.String(length=32), nullable=True),
)
AGENT_EVIDENCE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column(
        "execution_outcome",
        sa.String(length=16),
        nullable=False,
        server_default=LEGACY_EXECUTION_OUTCOME,
    ),
    sa.Column("end_reason", sa.String(length=32), nullable=True),
    sa.Column("agent_definition_hash", sa.String(length=64), nullable=True),
    sa.Column("definition_source", sa.String(length=32), nullable=True),
)
EVENT_EVIDENCE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("object_revision", sa.String(length=96), nullable=True),
    sa.Column("definition_hash", sa.String(length=64), nullable=True),
    sa.Column("file_read_hash", sa.String(length=64), nullable=True),
    sa.Column("read_complete", sa.Boolean(), nullable=True),
    sa.Column("relation_confidence", sa.String(length=16), nullable=True),
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
                f"nullable={bool(column.nullable)}; repair the column before retrying 0016",
            )


def upgrade() -> None:
    """Add the M9 evidence contract without touching runtime identity columns.

    Existing rows read the ``legacy_unknown`` server default after the column is
    added; MySQL DDL auto-commits, so each column addition is guarded to make a
    retry after a partial failure resume instead of failing on a duplicate.
    """
    _add_columns("session_families", SESSION_EVIDENCE_COLUMNS)
    _add_columns("agents", AGENT_EVIDENCE_COLUMNS)
    _add_columns("agent_events", EVENT_EVIDENCE_COLUMNS)


def _drop_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Drop evidence columns that are still present, recreating SQLite tables."""
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


def downgrade() -> None:
    """Remove every M9 evidence column added by this revision."""
    _drop_columns("agent_events", EVENT_EVIDENCE_COLUMNS)
    _drop_columns("agents", AGENT_EVIDENCE_COLUMNS)
    _drop_columns("session_families", SESSION_EVIDENCE_COLUMNS)
