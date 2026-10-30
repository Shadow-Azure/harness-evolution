"""Add durable per-root bad-case trajectory sync state.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-30
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the service-owned root-sync state table."""
    op.create_table(
        "bad_case_root_sync",
        sa.Column("root_session_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("agent_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("root_session_id"),
    )
    op.create_index(
        "ix_bad_case_root_sync_status_retry",
        "bad_case_root_sync",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    """Drop the service-owned root-sync state table."""
    op.drop_index(
        "ix_bad_case_root_sync_status_retry",
        table_name="bad_case_root_sync",
    )
    op.drop_table("bad_case_root_sync")
