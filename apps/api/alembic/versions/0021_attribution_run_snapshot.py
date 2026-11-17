"""Add run attribution snapshots and widen probe object versions.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-17
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | None = None
depends_on: str | None = None

OBJECT_VERSION_LENGTH = 96

RUN_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("potential_policy", sa.JSON(), nullable=True),
    sa.Column(
        "cache_enabled",
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ),
    sa.Column(
        "attribution_engine",
        sa.String(length=64),
        nullable=False,
        server_default="legacy-probe-import",
    ),
)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return the reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def _has_table(table: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(table)


def _add_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Add missing columns and reject an existing column with wrong nullability."""
    existing = _existing_columns(table)
    for column in columns:
        current = existing.get(str(column.name))
        if current is None:
            op.add_column(table, column)
            continue
        if bool(current["nullable"]) != bool(column.nullable):
            raise RuntimeError(
                f"{table}.{column.name} already exists with "
                f"nullable={bool(current['nullable'])}, expected "
                f"nullable={bool(column.nullable)}; repair the column before retrying 0021",
            )


def _widen_object_version() -> None:
    """Let probe identities carry ``digest:<sha256>`` revisions (71 chars)."""
    if not _has_table("probe_reports"):
        return
    column = _existing_columns("probe_reports").get("object_version")
    if column is None:
        return
    current_length = getattr(column["type"], "length", None)
    if isinstance(current_length, int) and current_length >= OBJECT_VERSION_LENGTH:
        return
    existing_type = sa.String(length=current_length or 64)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("probe_reports") as batch_op:
            batch_op.alter_column(
                "object_version",
                existing_type=existing_type,
                type_=sa.String(length=OBJECT_VERSION_LENGTH),
                existing_nullable=True,
            )
        return
    op.alter_column(
        "probe_reports",
        "object_version",
        existing_type=existing_type,
        type_=sa.String(length=OBJECT_VERSION_LENGTH),
        existing_nullable=True,
    )


def _drop_run_columns() -> None:
    """Drop the run attribution snapshot columns that are still present."""
    if not _has_table("evolution_runs"):
        return
    existing = _existing_columns("evolution_runs")
    present = tuple(column.name for column in RUN_COLUMNS if str(column.name) in existing)
    if not present:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("evolution_runs") as batch_op:
            for name in present:
                batch_op.drop_column(name)
        return
    for name in present:
        op.drop_column("evolution_runs", name)


def _shrink_object_version() -> None:
    """Restore the pre-0021 64-character column width."""
    if not _has_table("probe_reports"):
        return
    column = _existing_columns("probe_reports").get("object_version")
    if column is None:
        return
    current_length = getattr(column["type"], "length", None)
    if isinstance(current_length, int) and current_length <= 64:
        return
    existing_type = sa.String(length=current_length or OBJECT_VERSION_LENGTH)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("probe_reports") as batch_op:
            batch_op.alter_column(
                "object_version",
                existing_type=existing_type,
                type_=sa.String(length=64),
                existing_nullable=True,
            )
        return
    op.alter_column(
        "probe_reports",
        "object_version",
        existing_type=existing_type,
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def upgrade() -> None:
    """Add run snapshots and widen probe object versions.

    Every step is guarded by table/column presence so a retry after a partial
    MySQL DDL attempt can resume. Existing runs keep ``legacy-probe-import`` as
    their attribution engine; only V2 run creation overwrites that snapshot.
    """
    if _has_table("evolution_runs"):
        _add_columns("evolution_runs", RUN_COLUMNS)
    _widen_object_version()


def downgrade() -> None:
    """Remove run snapshots and restore the 64-character probe version."""
    _shrink_object_version()
    _drop_run_columns()
