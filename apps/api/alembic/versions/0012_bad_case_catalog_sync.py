"""Add the single-row bad-case catalog sync cursor.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-30
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the service-owned catalog-sync state table."""
    op.create_table(
        "bad_case_catalog_sync",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("last_bad_case_id", sa.BigInteger(), nullable=False),
        sa.Column("synced_count", sa.Integer(), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the service-owned catalog-sync state table."""
    op.drop_table("bad_case_catalog_sync")
