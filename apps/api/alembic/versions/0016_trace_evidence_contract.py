"""Add M9 execution, relation, definition, and file-read evidence columns.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-16
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None

LEGACY_EXECUTION_OUTCOME = "legacy_unknown"

SESSION_EVIDENCE_COLUMNS = ("execution_outcome", "end_reason")
AGENT_EVIDENCE_COLUMNS = (
    "execution_outcome",
    "end_reason",
    "agent_definition_hash",
    "definition_source",
)
EVENT_EVIDENCE_COLUMNS = (
    "object_revision",
    "definition_hash",
    "file_read_hash",
    "read_complete",
    "relation_confidence",
)


def _backfill_execution_outcome(table: str) -> None:
    """Backfill legacy rows that predate the non-null execution outcome default."""
    op.execute(
        sa.text(
            f"UPDATE {table} SET execution_outcome = :outcome "  # noqa: S608
            "WHERE execution_outcome IS NULL",
        ).bindparams(outcome=LEGACY_EXECUTION_OUTCOME),
    )


def upgrade() -> None:
    """Add the M9 evidence contract without touching runtime identity columns."""
    op.add_column(
        "session_families",
        sa.Column(
            "execution_outcome",
            sa.String(length=16),
            nullable=False,
            server_default=LEGACY_EXECUTION_OUTCOME,
        ),
    )
    op.add_column(
        "session_families",
        sa.Column("end_reason", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column(
            "execution_outcome",
            sa.String(length=16),
            nullable=False,
            server_default=LEGACY_EXECUTION_OUTCOME,
        ),
    )
    op.add_column(
        "agents",
        sa.Column("end_reason", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("agent_definition_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("definition_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "agent_events",
        sa.Column("object_revision", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "agent_events",
        sa.Column("definition_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_events",
        sa.Column("file_read_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_events",
        sa.Column("read_complete", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "agent_events",
        sa.Column("relation_confidence", sa.String(length=16), nullable=True),
    )
    _backfill_execution_outcome("session_families")
    _backfill_execution_outcome("agents")


def _drop_columns(table: str, columns: tuple[str, ...]) -> None:
    """Drop evidence columns, recreating SQLite tables through batch mode."""
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            for column in columns:
                batch_op.drop_column(column)
        return
    for column in columns:
        op.drop_column(table, column)


def downgrade() -> None:
    """Remove every M9 evidence column added by this revision."""
    _drop_columns("agent_events", EVENT_EVIDENCE_COLUMNS)
    _drop_columns("agents", AGENT_EVIDENCE_COLUMNS)
    _drop_columns("session_families", SESSION_EVIDENCE_COLUMNS)
