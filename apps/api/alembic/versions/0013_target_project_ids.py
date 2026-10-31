"""Add validation and test project IDs to targets and runs.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-31
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add the two opaque test project IDs to target and run snapshots."""
    for table in ("evolution_targets", "evolution_runs"):
        op.add_column(
            table,
            sa.Column(
                "validation_project_id",
                sa.String(length=128),
                nullable=False,
                server_default="",
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "test_project_id",
                sa.String(length=128),
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    """Drop the project ID snapshots from runs and targets."""
    for table in ("evolution_runs", "evolution_targets"):
        op.drop_column(table, "test_project_id")
        op.drop_column(table, "validation_project_id")
