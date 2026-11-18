"""Add the optional bad-case trigger log line.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-18
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | None = None
depends_on: str | None = None


def _existing_columns() -> dict[str, Any]:
    """Return the reflected ``bad_cases`` columns keyed by name."""
    return {
        str(column["name"]): column for column in inspect(op.get_bind()).get_columns("bad_cases")
    }


def _has_bad_cases() -> bool:
    """Return whether this database contains the externally owned issue table."""
    return inspect(op.get_bind()).has_table("bad_cases")


def upgrade() -> None:
    """Add a nullable trigger line without inventing values for existing rows.

    The column is additive and remains ``NULL`` for historical reports, which the
    overview renders as an honest dash. Deployments where an externally managed
    schema already carries the column keep their values.
    """
    if not _has_bad_cases() or "trigger_line" in _existing_columns():
        return
    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.add_column(sa.Column("trigger_line", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Drop the trigger line when it is still present."""
    if not _has_bad_cases() or "trigger_line" not in _existing_columns():
        return
    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.drop_column("trigger_line")
