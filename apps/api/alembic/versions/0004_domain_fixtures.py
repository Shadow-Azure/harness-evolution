"""Add the foundational trajectory, issue, and target tables for fixtures.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None

json_type = sa.JSON()
long_text_type = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    """Create this revision's frozen cross-dialect domain schema."""
    op.create_table(
        "trajectory_payloads",
        sa.Column("root_session_id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(64), primary_key=True),
        sa.Column("agent_kind", sa.String(16), nullable=False),
        sa.Column("payload", long_text_type, nullable=False),
        sa.Column("agent_meta", json_type, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_trajectory_payloads_updated_at",
        "trajectory_payloads",
        ["updated_at"],
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("records_total", sa.Integer(), nullable=False),
        sa.Column("records_done", sa.Integer(), nullable=False),
        sa.Column("imported", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("errors", json_type, nullable=False),
    )
    op.create_table(
        "source_records",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("root_session_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_hash", sa.String(64), nullable=True),
        sa.Column("parser_version", sa.Integer(), nullable=True),
        sa.Column(
            "last_sync_run_id",
            sa.String(36),
            sa.ForeignKey("sync_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "root_session_id",
            "agent_id",
            name="uq_source_records_root_agent",
        ),
    )
    op.create_index(
        "ix_source_records_processed_at",
        "source_records",
        ["processed_at"],
    )
    op.create_index(
        "ix_source_records_parser_version",
        "source_records",
        ["parser_version"],
    )
    op.create_table(
        "session_families",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("short_title", sa.String(255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("search_text", sa.String(512), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("project_path", sa.Text(), nullable=False),
        sa.Column("git_branch", sa.String(255), nullable=True),
        sa.Column("cli_version", sa.String(32), nullable=True),
        sa.Column("entrypoint", sa.String(16), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("models", json_type, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("skill_names", json_type, nullable=False),
        sa.Column("user_turns_count", sa.Integer(), nullable=False),
        sa.Column("messages_count", sa.Integer(), nullable=False),
        sa.Column("tools_count", sa.Integer(), nullable=False),
        sa.Column("errors_count", sa.Integer(), nullable=False),
        sa.Column("agents_count", sa.Integer(), nullable=False),
        sa.Column("tokens_total", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column(
            "main_record_id",
            sa.BigInteger(),
            sa.ForeignKey("source_records.id"),
            nullable=False,
        ),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_families_status", "session_families", ["status"])
    op.create_index(
        "ix_session_families_repo_name",
        "session_families",
        ["repo_name"],
    )
    op.create_index(
        "ix_session_families_started_at",
        "session_families",
        [sa.text("started_at DESC")],
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "root_session_id",
            sa.String(36),
            sa.ForeignKey("session_families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_agent_id",
            sa.String(64),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("agent_type", sa.String(64), nullable=True),
        sa.Column("task_kind", sa.String(32), nullable=True),
        sa.Column("team_name", sa.String(128), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("skill_name", sa.String(255), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("requested_model", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tool_use_id", sa.String(128), nullable=True),
        sa.Column("spawn_depth", sa.Integer(), nullable=False),
        sa.Column(
            "transcript_record_id",
            sa.BigInteger(),
            sa.ForeignKey("source_records.id"),
            nullable=True,
        ),
        sa.Column("lines", sa.Integer(), nullable=False),
        sa.Column("messages_count", sa.Integer(), nullable=False),
        sa.Column("tokens_total", sa.BigInteger(), nullable=False),
        sa.Column("tools_count", sa.Integer(), nullable=False),
        sa.Column("errors_count", sa.Integer(), nullable=False),
        sa.Column("meta", json_type, nullable=True),
        sa.Column("sort_key", sa.Float(), nullable=False),
        sa.UniqueConstraint("root_session_id", "id", name="uq_agents_root_id"),
    )
    op.create_index("ix_agents_parent_agent_id", "agents", ["parent_agent_id"])
    op.create_index("ix_agents_task_kind", "agents", ["task_kind"])
    op.create_index("ix_agents_model", "agents", ["model"])
    op.create_table(
        "agent_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "agent_id",
            sa.String(64),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("message_offset", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tool_use_id", sa.String(128), nullable=True),
        sa.UniqueConstraint(
            "agent_id",
            "event_index",
            name="uq_agent_events_agent_index",
        ),
    )
    op.create_index(
        "ix_agent_events_agent_line",
        "agent_events",
        ["agent_id", "line_no"],
    )
    op.create_index(
        "ix_agent_events_agent_message",
        "agent_events",
        ["agent_id", "message_offset"],
    )
    op.create_table(
        "user_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "root_session_id",
            sa.String(36),
            sa.ForeignKey("session_families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("message_offset", sa.Integer(), nullable=False),
        sa.UniqueConstraint("root_session_id", "seq", name="uq_user_turns_root_seq"),
    )
    op.create_index(
        "ix_user_turns_root_line",
        "user_turns",
        ["root_session_id", "line_no"],
    )
    op.create_table(
        "bad_cases",
        sa.Column("bad_case_id", sa.String(64), primary_key=True),
        sa.Column("bad_case_session_id", sa.String(36), nullable=False),
        sa.Column("bad_case_type", sa.String(16), nullable=False),
        sa.Column("object_name", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(16), nullable=False),
        sa.Column("object_version", sa.String(64), nullable=True),
        sa.Column("bad_case_agent_id", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("meta_data", json_type, nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bad_cases_session", "bad_cases", ["bad_case_session_id"])
    op.create_index("ix_bad_cases_agent", "bad_cases", ["bad_case_agent_id"])
    op.create_index(
        "ix_bad_cases_object",
        "bad_cases",
        ["object_type", "object_name", "object_version"],
    )
    op.create_table(
        "probe_reports",
        sa.Column("probe_id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("probe_type", sa.String(16), nullable=False),
        sa.Column("probe_object", sa.String(128), nullable=False),
        sa.Column("object_version", sa.String(64), nullable=True),
        sa.Column("attribute_type", sa.String(16), nullable=False),
        sa.Column("probe_description", sa.Text(), nullable=False),
        sa.Column("probe_analysis", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_probe_reports_session", "probe_reports", ["session_id"])
    op.create_index(
        "ix_probe_reports_object",
        "probe_reports",
        ["probe_type", "probe_object", "object_version"],
    )
    op.create_index(
        "ix_probe_reports_attribute",
        "probe_reports",
        ["attribute_type"],
    )
    op.create_table(
        "bad_case_analysis",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "bad_case_id",
            sa.String(64),
            sa.ForeignKey("bad_cases.bad_case_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("analysis_status", sa.String(32), nullable=False),
        sa.Column(
            "probe_id",
            sa.String(64),
            sa.ForeignKey("probe_reports.probe_id"),
            nullable=True,
        ),
        sa.Column("analysis_result", json_type, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "bad_case_id",
            name="uq_bad_case_analysis_case",
        ),
    )
    op.create_index(
        "ix_bad_case_analysis_probe",
        "bad_case_analysis",
        ["probe_id"],
    )
    op.create_index(
        "ix_bad_case_analysis_status",
        "bad_case_analysis",
        ["analysis_status"],
    )
    op.create_table(
        "evolution_targets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("object_type", sa.String(16), nullable=False),
        sa.Column("object_name", sa.String(128), nullable=False),
        sa.Column("repo_url", sa.String(1024), nullable=False),
        sa.Column("sub_dir", sa.String(512), nullable=False),
        sa.Column("default_ref", sa.String(128), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "object_type",
            "object_name",
            name="uq_evolution_targets_object",
        ),
    )
    op.create_index(
        "ix_evolution_targets_enabled",
        "evolution_targets",
        ["enabled"],
    )


def downgrade() -> None:
    """Drop this revision's tables in reverse dependency order."""
    op.drop_table("evolution_targets")
    op.drop_table("bad_case_analysis")
    op.drop_table("probe_reports")
    op.drop_table("bad_cases")
    op.drop_table("user_turns")
    op.drop_table("agent_events")
    op.drop_table("agents")
    op.drop_table("session_families")
    op.drop_table("source_records")
    op.drop_table("sync_runs")
    op.drop_table("trajectory_payloads")
