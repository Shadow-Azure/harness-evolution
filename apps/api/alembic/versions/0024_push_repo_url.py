"""Add the per-run Git push target derived during preparation.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-21
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | None = None
depends_on: str | None = None

PUSH_REPO_URL_COLUMN = sa.Column(
    "push_repo_url",
    sa.String(length=1024),
    nullable=False,
    server_default="",
)


def _has_table(table: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(table)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return the reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """Persist the provider-derived push target without breaking historical runs.

    The column is additive and defaults to an empty string, so a run prepared
    before this migration keeps falling back to ``repo_url``. The migration is
    idempotent so a retry after a partial DDL attempt can resume.
    """
    if not _has_table("evolution_runs"):
        return
    if str(PUSH_REPO_URL_COLUMN.name) in _existing_columns("evolution_runs"):
        return
    with op.batch_alter_table("evolution_runs") as batch_op:
        batch_op.add_column(PUSH_REPO_URL_COLUMN)


def downgrade() -> None:
    """Remove the derived push target; offline runs fall back to ``repo_url``."""
    if not _has_table("evolution_runs"):
        return
    if str(PUSH_REPO_URL_COLUMN.name) not in _existing_columns("evolution_runs"):
        return
    with op.batch_alter_table("evolution_runs") as batch_op:
        batch_op.drop_column(PUSH_REPO_URL_COLUMN.name)
