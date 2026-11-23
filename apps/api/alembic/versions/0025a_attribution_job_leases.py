"""Add attribution cancellation and retry limits to durable jobs.

Revision ID: 0025a
Revises: 0024a
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0025a"
down_revision: str | None = "0024a"
branch_labels: str | None = None
depends_on: str | None = None


def _columns() -> set[str]:
    """Return current durable-job columns."""
    return {str(column["name"]) for column in inspect(op.get_bind()).get_columns("job_runs")}


def upgrade() -> None:
    """Add cross-process claim metadata without changing existing job identities."""
    columns = _columns()
    additions = (
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column("job_runs", column)


def downgrade() -> None:
    """Remove durable-claim metadata."""
    columns = _columns()
    names = ("cancel_requested", "max_attempts")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("job_runs") as batch_op:
            for name in names:
                if name in columns:
                    batch_op.drop_column(name)
        return
    for name in names:
        if name in columns:
            op.drop_column("job_runs", name)
