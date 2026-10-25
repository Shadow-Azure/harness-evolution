"""Add durable job and run-event audit rows for the single-process runner.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the cross-dialect job queue and audit table."""
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("executor", sa.String(length=16), nullable=False),
        sa.Column("external_job_id", sa.String(length=128), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_job_runs_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_runs_status", "job_runs", ["status"], unique=False)
    op.execute(
        "CREATE INDEX ix_job_runs_kind_created_at ON job_runs (kind, created_at DESC)",
    )
    op.create_index("ix_job_runs_ref_id", "job_runs", ["ref_id"], unique=False)
    op.create_table(
        "evolution_run_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=True),
        sa.Column("cluster_id", sa.String(length=64), nullable=True),
        sa.Column("evolution_round_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "seq",
            name="uq_evolution_run_events_run_seq",
        ),
    )
    op.create_index(
        "ix_evolution_run_events_run_created",
        "evolution_run_events",
        ["run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_evolution_run_events_event_type",
        "evolution_run_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_evolution_run_events_level",
        "evolution_run_events",
        ["level"],
        unique=False,
    )
    op.create_index(
        "ix_evolution_run_events_cluster_id",
        "evolution_run_events",
        ["cluster_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the job queue when rolling back the migration."""
    op.drop_index(
        "ix_evolution_run_events_cluster_id",
        table_name="evolution_run_events",
    )
    op.drop_index(
        "ix_evolution_run_events_level",
        table_name="evolution_run_events",
    )
    op.drop_index(
        "ix_evolution_run_events_event_type",
        table_name="evolution_run_events",
    )
    op.drop_index(
        "ix_evolution_run_events_run_created",
        table_name="evolution_run_events",
    )
    op.drop_table("evolution_run_events")
    op.drop_index("ix_job_runs_ref_id", table_name="job_runs")
    op.drop_index("ix_job_runs_kind_created_at", table_name="job_runs")
    op.drop_index("ix_job_runs_status", table_name="job_runs")
    op.drop_table("job_runs")
