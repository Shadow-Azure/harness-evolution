"""Add durable job lease and heartbeat columns.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-21
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | None = None
depends_on: str | None = None

LEASE_OWNER_COLUMN = sa.Column("lease_owner", sa.String(length=64), nullable=True)
LEASE_EXPIRES_AT_COLUMN = sa.Column(
    "lease_expires_at",
    sa.DateTime(timezone=True),
    nullable=True,
)
HEARTBEAT_AT_COLUMN = sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
LEASE_INDEX = "ix_job_runs_status_lease_expires_at"


def _has_table(table: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(table)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return the reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    """Return the reflected index names on one table."""
    return {str(index["name"]) for index in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    """Add nullable lease facts and the expiry scan index.

    Historical rows stay readable and count as expired because every lease
    column is null. The migration is idempotent so a retry after a partial DDL
    attempt can resume.
    """
    if not _has_table("job_runs"):
        return
    columns = _existing_columns("job_runs")
    with op.batch_alter_table("job_runs") as batch_op:
        if str(LEASE_OWNER_COLUMN.name) not in columns:
            batch_op.add_column(LEASE_OWNER_COLUMN)
        if str(LEASE_EXPIRES_AT_COLUMN.name) not in columns:
            batch_op.add_column(LEASE_EXPIRES_AT_COLUMN)
        if str(HEARTBEAT_AT_COLUMN.name) not in columns:
            batch_op.add_column(HEARTBEAT_AT_COLUMN)
    if LEASE_INDEX not in _existing_indexes("job_runs"):
        op.create_index(
            LEASE_INDEX,
            "job_runs",
            ["status", "lease_expires_at"],
        )


def downgrade() -> None:
    """Drop the lease scan index and the three additive columns."""
    if not _has_table("job_runs"):
        return
    if LEASE_INDEX in _existing_indexes("job_runs"):
        op.drop_index(LEASE_INDEX, table_name="job_runs")
    columns = _existing_columns("job_runs")
    with op.batch_alter_table("job_runs") as batch_op:
        for column in (HEARTBEAT_AT_COLUMN, LEASE_EXPIRES_AT_COLUMN, LEASE_OWNER_COLUMN):
            if str(column.name) in columns:
                batch_op.drop_column(str(column.name))
