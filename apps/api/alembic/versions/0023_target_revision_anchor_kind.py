"""Add resolved target revisions and candidate anchor kinds.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-19
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | None = None
depends_on: str | None = None

RUN_COLUMN = sa.Column("target_revision", sa.String(length=96), nullable=True)
CANDIDATE_COLUMN = sa.Column("case_anchor_kind", sa.String(length=16), nullable=True)
TARGET_VERSION_LENGTH = 96


def _has_table(table: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(table)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return the reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def _add_column(table: str, column: sa.Column[Any]) -> None:
    """Add one nullable column when the target table exists and lacks it."""
    if not _has_table(table) or str(column.name) in _existing_columns(table):
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(column)


def _drop_column(table: str, name: str) -> None:
    """Drop one column when the target table still carries it."""
    if not _has_table(table) or name not in _existing_columns(table):
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_column(name)


def _alter_target_version(length: int) -> None:
    """Resize the run's selected version so a knowledge digest revision fits."""
    if not _has_table("evolution_runs"):
        return
    column = _existing_columns("evolution_runs").get("target_version")
    if column is None:
        return
    current_length = getattr(column["type"], "length", None)
    if not isinstance(current_length, int) or current_length == length:
        return
    existing_type = sa.String(length=current_length)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("evolution_runs") as batch_op:
            batch_op.alter_column(
                "target_version",
                existing_type=existing_type,
                type_=sa.String(length=length),
                existing_nullable=False,
            )
        return
    op.alter_column(
        "evolution_runs",
        "target_version",
        existing_type=existing_type,
        type_=sa.String(length=length),
        existing_nullable=False,
    )


def upgrade() -> None:
    """Persist the resolved content revision and the audited case anchor kind.

    Both columns are additive and nullable: historical runs keep a null
    ``target_revision`` and historical candidates keep a null
    ``case_anchor_kind`` until they are re-prepared. ``target_version`` grows to
    96 so a knowledge document revision (``digest:<sha256>`` is 71 chars) fits
    without truncation. The migration is idempotent so a retry after a partial
    DDL attempt can resume.
    """
    _add_column("evolution_runs", RUN_COLUMN)
    _add_column("evolution_run_candidates", CANDIDATE_COLUMN)
    _alter_target_version(TARGET_VERSION_LENGTH)


def downgrade() -> None:
    """Remove both additive columns without shrinking the version column.

    ``target_version`` stays at 96 so a downgrade can never truncate or reject a
    71-character knowledge digest under MySQL strict mode.
    """
    _drop_column("evolution_run_candidates", "case_anchor_kind")
    _drop_column("evolution_runs", "target_revision")
