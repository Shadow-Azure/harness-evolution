"""Add run-level evaluations and the target primary metric key.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-25
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Store evaluations outside rounds and the target's primary metric."""
    op.add_column(
        "evolution_targets",
        sa.Column(
            "primary_metric_key",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.create_table(
        "evolution_evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("evolution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("eval_external_id", sa.String(length=128), nullable=True),
        sa.Column(
            "eval_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "eval_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("eval_next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "eval_paused_seconds",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("eval_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eval_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eval_score", sa.Float(), nullable=True),
        sa.Column("eval_result", sa.JSON(), nullable=True),
        sa.Column("eval_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id",
            "kind",
            name="uq_evolution_evaluations_run_kind",
        ),
    )
    op.create_index(
        "ix_evolution_evaluations_run",
        "evolution_evaluations",
        ["run_id"],
    )
    op.create_index(
        "ix_evolution_evaluations_poll",
        "evolution_evaluations",
        ["eval_status", "eval_next_poll_at"],
    )


def downgrade() -> None:
    """Drop the run-level evaluation storage and the metric key column."""
    op.drop_index("ix_evolution_evaluations_poll", table_name="evolution_evaluations")
    op.drop_index("ix_evolution_evaluations_run", table_name="evolution_evaluations")
    op.drop_table("evolution_evaluations")
    op.drop_column("evolution_targets", "primary_metric_key")
