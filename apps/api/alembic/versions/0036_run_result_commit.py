"""Persist the no-acceptance result commit used as the test-set final target."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0036"
down_revision = "0035"


def upgrade() -> None:
    """Add the optional result commit without touching existing runs."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("evolution_runs"):
        return
    columns = {str(column["name"]) for column in inspector.get_columns("evolution_runs")}
    if "result_commit" not in columns:
        op.add_column(
            "evolution_runs",
            sa.Column("result_commit", sa.String(length=40), nullable=True),
        )


def downgrade() -> None:
    """Drop the result commit column."""
    op.drop_column("evolution_runs", "result_commit")
