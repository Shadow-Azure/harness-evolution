"""Persist the per-member name-matching switch on targets and run snapshots."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0037"
down_revision = "0036"


def _existing_columns(bind: object, table: str) -> set[str]:
    """Return the reflected column names of an existing table."""
    return {str(column["name"]) for column in inspect(bind).get_columns(table)}


def upgrade() -> None:
    """Add the default-off switch without backfilling any existing row."""
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("evolution_target_members", "evolution_run_targets"):
        if not inspector.has_table(table):
            continue
        if "match_by_name" in _existing_columns(bind, table):
            continue
        # ``server_default`` keeps historical rows and in-flight inserts false;
        # the application always writes an explicit boolean.
        op.add_column(
            table,
            sa.Column(
                "match_by_name",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    """Drop the switch column from both persistence layers."""
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("evolution_run_targets", "evolution_target_members"):
        if not inspector.has_table(table):
            continue
        if "match_by_name" not in _existing_columns(bind, table):
            continue
        op.drop_column(table, "match_by_name")
