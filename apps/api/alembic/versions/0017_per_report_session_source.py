"""Add per-report session sources and frozen root-sync source state.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-16
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None

GLOBAL_SOURCE_KIND = "global"

BAD_CASE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("session_source", sa.JSON(), nullable=True),
)
ROOT_SYNC_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column(
        "source_kind",
        sa.String(length=16),
        nullable=False,
        server_default=GLOBAL_SOURCE_KIND,
    ),
    sa.Column("source_snapshot", sa.JSON(), nullable=True),
)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def _add_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Add missing columns, skipping an externally owned table that is absent."""
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table):
        return
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
                f"nullable={bool(column.nullable)}; repair the column before retrying 0017",
            )


def upgrade() -> None:
    """Persist report sources and freeze the selected source per root.

    MySQL DDL auto-commits, so each column addition is presence-guarded and a
    retry after a partial failure resumes instead of failing on a duplicate.
    """
    _add_columns("bad_cases", BAD_CASE_COLUMNS)
    _add_columns("bad_case_root_sync", ROOT_SYNC_COLUMNS)
    if inspect(op.get_bind()).has_table("bad_case_root_sync"):
        op.execute(
            "UPDATE bad_case_root_sync SET source_kind = 'global' "
            "WHERE source_kind IS NULL OR source_kind = ''",
        )


def _drop_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Drop selected columns that are still present, recreating SQLite tables."""
    if not inspect(op.get_bind()).has_table(table):
        return
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
    """Remove per-report sources and frozen source state."""
    _drop_columns("bad_case_root_sync", ROOT_SYNC_COLUMNS)
    _drop_columns("bad_cases", BAD_CASE_COLUMNS)
