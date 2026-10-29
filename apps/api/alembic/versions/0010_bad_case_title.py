"""Add the bad-case short title and rename the description body column.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def _has_bad_cases() -> bool:
    """Return whether this database contains the externally owned issue table."""
    return inspect(op.get_bind()).has_table("bad_cases")


def upgrade() -> None:
    """Split the short title from the description body on existing issue rows.

    SQLite cannot rename a column or add a NOT NULL column in place, so both
    ALTERs run through batch mode. Existing rows keep their full reason text as
    the description body and receive its first 255 characters as the short
    title (the locked one-time backfill; upstream reload remains authoritative).
    """
    if not _has_bad_cases():
        return

    with op.batch_alter_table("bad_cases") as batch_op:
        # MySQL 的 CHANGE COLUMN 不带 NULL/NOT NULL 时会把列改成可空，所以改名时
        # 显式带上 existing_nullable / nullable，SQLite batch 重建表同样受益。
        batch_op.alter_column(
            "reason",
            new_column_name="bad_case_description",
            existing_type=sa.Text(),
            existing_nullable=False,
            nullable=False,
        )
    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(255), nullable=True))
    op.execute("UPDATE bad_cases SET title = SUBSTR(bad_case_description, 1, 255)")
    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.alter_column(
            "title",
            existing_type=sa.String(255),
            nullable=False,
        )


def downgrade() -> None:
    """Restore the legacy column name and drop the short-title column.

    The description body survives the rename unchanged, so the column names are
    restored without data loss. Dropping ``title`` is deliberately lossy:
    upgraded titles were derived from the description, so they can be derived
    again if this revision is later re-applied.
    """
    if not _has_bad_cases():
        return

    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.drop_column("title")
    with op.batch_alter_table("bad_cases") as batch_op:
        batch_op.alter_column(
            "bad_case_description",
            new_column_name="reason",
            existing_type=sa.Text(),
            existing_nullable=False,
            nullable=False,
        )
