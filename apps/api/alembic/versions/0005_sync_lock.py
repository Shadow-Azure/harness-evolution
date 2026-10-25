"""Add the durable sync single-flight lock.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the one-row sync lock table."""
    op.create_table(
        "sync_lock",
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["job_runs.id"],
            name="fk_sync_lock_job_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_index("ix_sync_lock_expires_at", "sync_lock", ["expires_at"])


def downgrade() -> None:
    """Remove the durable sync lock."""
    op.drop_index("ix_sync_lock_expires_at", table_name="sync_lock")
    op.drop_table("sync_lock")
