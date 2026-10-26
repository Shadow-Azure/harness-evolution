"""Add durable evolution state tables.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create evolution runs, clusters, rounds, and final results."""
    op.create_table(
        "evolution_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("engine_key", sa.String(length=64), nullable=False),
        sa.Column("eval_config", sa.JSON(), nullable=False),
        sa.Column("target_config_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_name", sa.String(length=128), nullable=False),
        sa.Column("target_version", sa.String(length=64), nullable=False),
        sa.Column("repo_url", sa.String(length=1024), nullable=False),
        sa.Column("sub_dir", sa.String(length=512), nullable=False),
        sa.Column("repo_path", sa.String(length=1024), nullable=True),
        sa.Column("base_ref", sa.String(length=128), nullable=True),
        sa.Column("base_commit", sa.String(length=40), nullable=True),
        sa.Column("branch_name", sa.String(length=128), nullable=True),
        sa.Column("workspace_path", sa.String(length=1024), nullable=True),
        sa.Column(
            "remote_name",
            sa.String(length=64),
            nullable=False,
            server_default="origin",
        ),
        sa.Column(
            "push_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_error", sa.Text(), nullable=True),
        sa.Column("window_from", sa.Date(), nullable=True),
        sa.Column("window_to", sa.Date(), nullable=True),
        sa.Column("models", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="preparing",
        ),
        sa.Column("blocked_stage", sa.String(length=16), nullable=True),
        sa.Column(
            "retry_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "eval_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_stage", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "progress_unit",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_evolution_runs_created_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_config_id"],
            ["evolution_targets.id"],
            name="fk_evolution_runs_target_config",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evolution_runs_created_at",
        "evolution_runs",
        [sa.text("created_at DESC")],
    )
    op.create_index("ix_evolution_runs_status", "evolution_runs", ["status"])
    op.create_index(
        "ix_evolution_runs_push_status",
        "evolution_runs",
        ["push_status"],
    )
    op.create_index(
        "ix_evolution_runs_status_next_retry",
        "evolution_runs",
        ["status", "next_retry_at"],
    )
    op.create_index(
        "ix_evolution_runs_target_version",
        "evolution_runs",
        ["target_type", "target_name", "target_version"],
    )
    op.create_index(
        "ix_evolution_runs_target_config",
        "evolution_runs",
        ["target_config_id"],
    )

    op.create_table(
        "probe_clusters",
        sa.Column("probe_cluster_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("probe_cluster_description", sa.Text(), nullable=False),
        sa.Column("probe_cluster_type", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("impact", sa.Float(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evolution_runs.id"],
            name="fk_probe_clusters_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("probe_cluster_id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_probe_clusters_run_seq"),
    )
    op.create_index("ix_probe_clusters_run", "probe_clusters", ["run_id"])
    op.create_index(
        "ix_probe_clusters_run_rank",
        "probe_clusters",
        ["run_id", "rank"],
    )

    op.create_table(
        "probe_cluster_probes",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("probe_cluster_id", sa.String(length=64), nullable=False),
        sa.Column("probe_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["probe_cluster_id"],
            ["probe_clusters.probe_cluster_id"],
            name="fk_probe_cluster_probes_cluster",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["probe_id"],
            ["probe_reports.probe_id"],
            name="fk_probe_cluster_probes_probe",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "probe_cluster_id",
            "probe_id",
            name="uq_probe_cluster_probes_pair",
        ),
    )
    op.create_index(
        "ix_probe_cluster_probes_probe",
        "probe_cluster_probes",
        ["probe_id"],
    )

    op.create_table(
        "evolution_rounds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("probe_cluster_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("patch", sa.JSON(), nullable=True),
        sa.Column("candidate_ref", sa.String(length=255), nullable=True),
        sa.Column("candidate_commit", sa.String(length=40), nullable=True),
        sa.Column("candidate_message", sa.Text(), nullable=True),
        sa.Column(
            "push_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "push_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_error", sa.Text(), nullable=True),
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
        sa.Column("eval_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eval_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eval_current", sa.Float(), nullable=True),
        sa.Column("eval_candidate", sa.Float(), nullable=True),
        sa.Column("eval_result", sa.JSON(), nullable=True),
        sa.Column("eval_error", sa.Text(), nullable=True),
        sa.Column(
            "accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("commit_hash", sa.String(length=40), nullable=True),
        sa.Column("commit_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["probe_cluster_id"],
            ["probe_clusters.probe_cluster_id"],
            name="fk_evolution_rounds_cluster",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evolution_runs.id"],
            name="fk_evolution_rounds_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_evolution_rounds_run_seq"),
    )
    op.create_index(
        "ix_evolution_rounds_cluster",
        "evolution_rounds",
        ["probe_cluster_id"],
    )
    op.create_index(
        "ix_evolution_rounds_run_status",
        "evolution_rounds",
        ["run_id", "status"],
    )
    op.create_index(
        "ix_evolution_rounds_eval_poll",
        "evolution_rounds",
        ["eval_status", "eval_next_poll_at"],
    )

    op.create_table(
        "evolution_finals",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("best_version", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.Boolean(), nullable=False),
        sa.Column("best_score", sa.Float(), nullable=False),
        sa.Column("init_score", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evolution_runs.id"],
            name="fk_evolution_finals_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    """Remove evolution tables in reverse dependency order."""
    op.drop_table("evolution_finals")
    op.drop_index(
        "ix_evolution_rounds_eval_poll",
        table_name="evolution_rounds",
    )
    op.drop_index(
        "ix_evolution_rounds_run_status",
        table_name="evolution_rounds",
    )
    op.drop_index(
        "ix_evolution_rounds_cluster",
        table_name="evolution_rounds",
    )
    op.drop_table("evolution_rounds")
    op.drop_index(
        "ix_probe_cluster_probes_probe",
        table_name="probe_cluster_probes",
    )
    op.drop_table("probe_cluster_probes")
    op.drop_index(
        "ix_probe_clusters_run_rank",
        table_name="probe_clusters",
    )
    op.drop_index("ix_probe_clusters_run", table_name="probe_clusters")
    op.drop_table("probe_clusters")
    op.drop_index(
        "ix_evolution_runs_target_config",
        table_name="evolution_runs",
    )
    op.drop_index(
        "ix_evolution_runs_target_version",
        table_name="evolution_runs",
    )
    op.drop_index(
        "ix_evolution_runs_status_next_retry",
        table_name="evolution_runs",
    )
    op.drop_index(
        "ix_evolution_runs_push_status",
        table_name="evolution_runs",
    )
    op.drop_index("ix_evolution_runs_status", table_name="evolution_runs")
    op.drop_index(
        "ix_evolution_runs_created_at",
        table_name="evolution_runs",
    )
    op.drop_table("evolution_runs")
