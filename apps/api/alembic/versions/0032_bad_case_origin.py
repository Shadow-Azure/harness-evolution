"""Add the bad-case writer origin that protects reported rows from catalog sync.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-24
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | None = None
depends_on: str | None = None

DEFAULT_WORKSPACE_ID = "ws-default"
CATALOG_ORIGIN = "catalog"
REPORT_ORIGIN = "report"

ORIGIN_COLUMN = sa.Column(
    "origin",
    sa.String(length=16),
    nullable=False,
    server_default=CATALOG_ORIGIN,
)


def _has_bad_cases() -> bool:
    """Return whether this database contains the externally owned issue table."""
    return inspect(op.get_bind()).has_table("bad_cases")


def _columns() -> dict[str, Any]:
    """Return reflected bad-case columns keyed by name."""
    return {
        str(column["name"]): column for column in inspect(op.get_bind()).get_columns("bad_cases")
    }


def upgrade() -> None:
    """Attribute existing rows to their first writer and default new rows to the catalog.

    The column lands with the catalog default so the adding DDL itself is the
    backfill for catalog rows; one UPDATE then marks the rows that were
    submitted through workspace credentials. MySQL DDL auto-commits, so the
    presence check makes a retry after a partial failure resume instead of
    failing on a duplicate column.
    """
    if not _has_bad_cases():
        return
    if "origin" not in _columns():
        op.add_column("bad_cases", ORIGIN_COLUMN)
    op.execute(
        sa.text(
            "UPDATE bad_cases SET origin = :report "
            "WHERE workspace_id <> :default_workspace OR session_source IS NOT NULL",
        ).bindparams(
            report=REPORT_ORIGIN,
            default_workspace=DEFAULT_WORKSPACE_ID,
        ),
    )


def downgrade() -> None:
    """Drop the writer origin; catalog ownership is no longer recorded."""
    if not _has_bad_cases() or "origin" not in _columns():
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("bad_cases") as batch_op:
            batch_op.drop_column("origin")
        return
    op.drop_column("bad_cases", "origin")
