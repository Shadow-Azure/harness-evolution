"""Add structured attribution report and execution manifest fields.

Revision ID: 0028a
Revises: 0028
Create Date: 2026-11-17
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0028a"
down_revision: str | None = "0028"
branch_labels: str | None = None
depends_on: str | None = None

PROBE_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("report_schema_version", sa.String(length=32), nullable=True),
    sa.Column("report_payload", sa.JSON(), nullable=True),
    sa.Column("execution_manifest", sa.JSON(), nullable=True),
    sa.Column("execution_manifest_hash", sa.CHAR(length=64), nullable=True),
)
MANIFEST_INDEX = "ix_probe_reports_manifest_hash"


def _has_table(table: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(table)


def _existing_columns(table: str) -> set[str]:
    """Return reflected column names for one existing table."""
    return {str(column["name"]) for column in inspect(op.get_bind()).get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    """Return reflected index names for one existing table."""
    return {
        str(index["name"])
        for index in inspect(op.get_bind()).get_indexes(table)
        if index.get("name") is not None
    }


def upgrade() -> None:
    """Add nullable V2 fields so every legacy report remains readable."""
    if not _has_table("probe_reports"):
        return
    existing = _existing_columns("probe_reports")
    for column in PROBE_COLUMNS:
        if str(column.name) not in existing:
            op.add_column("probe_reports", column)
    if MANIFEST_INDEX not in _existing_indexes("probe_reports"):
        op.create_index(
            MANIFEST_INDEX,
            "probe_reports",
            ["execution_manifest_hash"],
        )


def downgrade() -> None:
    """Remove only the V2 fields and index that are still present."""
    if not _has_table("probe_reports"):
        return
    if MANIFEST_INDEX in _existing_indexes("probe_reports"):
        op.drop_index(MANIFEST_INDEX, table_name="probe_reports")
    existing = _existing_columns("probe_reports")
    present = tuple(column.name for column in reversed(PROBE_COLUMNS) if column.name in existing)
    if not present:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("probe_reports") as batch_op:
            for name in present:
                batch_op.drop_column(name)
        return
    for name in present:
        op.drop_column("probe_reports", name)
