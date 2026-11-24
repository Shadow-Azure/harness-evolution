"""Add bad-case writer ownership so catalog sync stops overwriting reports.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from app.db.models.workspace import DEFAULT_WORKSPACE_ID

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | None = None
depends_on: str | None = None

_BACKFILL_SQL = {
    ("workspace_id", "session_source"): (
        "UPDATE bad_cases SET origin = 'report' "
        "WHERE workspace_id <> :default_workspace OR session_source IS NOT NULL"
    ),
    ("workspace_id",): (
        "UPDATE bad_cases SET origin = 'report' WHERE workspace_id <> :default_workspace"
    ),
    ("session_source",): (
        "UPDATE bad_cases SET origin = 'report' WHERE session_source IS NOT NULL"
    ),
}


def _has_bad_cases() -> bool:
    """Return whether this database contains the externally owned issue table."""
    return inspect(op.get_bind()).has_table("bad_cases")


def _existing_columns() -> set[str]:
    """Return the reflected ``bad_cases`` column names."""
    return {str(column["name"]) for column in inspect(op.get_bind()).get_columns("bad_cases")}


def upgrade() -> None:
    """Add the owner column and backfill the historic writers."""
    if not _has_bad_cases():
        return
    columns = _existing_columns()
    if "origin" not in columns:
        with op.batch_alter_table("bad_cases") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "origin",
                    sa.String(length=16),
                    nullable=False,
                    server_default="catalog",
                ),
            )
    key = tuple(column for column in ("workspace_id", "session_source") if column in columns)
    statement = _BACKFILL_SQL.get(key)
    if statement is None:
        return
    op.execute(
        sa.text(statement).bindparams(default_workspace=DEFAULT_WORKSPACE_ID),
    )


def downgrade() -> None:
    """Drop the owner column when the external table carries it."""
    if not _has_bad_cases() or "origin" not in _existing_columns():
        return
    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.drop_column("origin")
