"""Dialect-neutral trajectory, issue, and evolution configuration tables."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.mysql import LONGTEXT

DOMAIN_METADATA = MetaData()


trajectory_payloads = Table(
    "trajectory_payloads",
    DOMAIN_METADATA,
    Column("root_session_id", String(36), primary_key=True),
    Column("agent_id", String(64), primary_key=True),
    Column("agent_kind", String(16), nullable=False),
    Column("payload", Text().with_variant(LONGTEXT, "mysql"), nullable=False),
    Column("agent_meta", JSON, nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("line_count", Integer, nullable=False),
    Column("source_type", String(16), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_trajectory_payloads_updated_at", "updated_at"),
)


sync_runs = Table(
    "sync_runs",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("source_type", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("status", String(16), nullable=False),
    Column("records_total", Integer, nullable=False),
    Column("records_done", Integer, nullable=False),
    Column("imported", Integer, nullable=False),
    Column("skipped", Integer, nullable=False),
    Column("errors", JSON, nullable=False),
)


source_records = Table(
    "source_records",
    DOMAIN_METADATA,
    Column(
        "id",
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("root_session_id", String(36), nullable=False),
    Column("agent_id", String(64), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("source_type", String(16), nullable=False),
    Column("line_count", Integer, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=True),
    Column("processed_hash", String(64), nullable=True),
    Column("parser_version", Integer, nullable=True),
    Column(
        "last_sync_run_id",
        String(36),
        ForeignKey("sync_runs.id", ondelete="SET NULL"),
        nullable=True,
    ),
    UniqueConstraint(
        "root_session_id",
        "agent_id",
        name="uq_source_records_root_agent",
    ),
    Index("ix_source_records_processed_at", "processed_at"),
    Index("ix_source_records_parser_version", "parser_version"),
)


session_families = Table(
    "session_families",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("short_title", String(255), nullable=False),
    Column("title", Text, nullable=False),
    Column("search_text", String(512), nullable=False),
    Column("repo_name", String(255), nullable=False),
    Column("project_path", Text, nullable=False),
    Column("git_branch", String(255), nullable=True),
    Column("cli_version", String(32), nullable=True),
    Column("entrypoint", String(16), nullable=True),
    Column("model", String(64), nullable=True),
    Column("models", JSON, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=False),
    Column("duration_seconds", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("skill_names", JSON, nullable=False),
    Column("user_turns_count", Integer, nullable=False),
    Column("messages_count", Integer, nullable=False),
    Column("tools_count", Integer, nullable=False),
    Column("errors_count", Integer, nullable=False),
    Column("agents_count", Integer, nullable=False),
    Column("tokens_total", BigInteger, nullable=False),
    Column("source_type", String(16), nullable=False),
    Column(
        "main_record_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("source_records.id"),
        nullable=False,
    ),
    Column("imported_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_session_families_status", "status"),
    Index("ix_session_families_repo_name", "repo_name"),
)
Index("ix_session_families_started_at", session_families.c.started_at.desc())


agents = Table(
    "agents",
    DOMAIN_METADATA,
    Column("id", String(64), primary_key=True),
    Column(
        "root_session_id",
        String(36),
        ForeignKey("session_families.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "parent_agent_id",
        String(64),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("kind", String(16), nullable=False),
    Column("agent_type", String(64), nullable=True),
    Column("task_kind", String(32), nullable=True),
    Column("team_name", String(128), nullable=True),
    Column("name", String(255), nullable=True),
    Column("skill_name", String(255), nullable=True),
    Column("model", String(64), nullable=True),
    Column("requested_model", String(64), nullable=True),
    Column("description", Text, nullable=True),
    Column("tool_use_id", String(128), nullable=True),
    Column("spawn_depth", Integer, nullable=False),
    Column(
        "transcript_record_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("source_records.id"),
        nullable=True,
    ),
    Column("lines", Integer, nullable=False),
    Column("messages_count", Integer, nullable=False),
    Column("tokens_total", BigInteger, nullable=False),
    Column("tools_count", Integer, nullable=False),
    Column("errors_count", Integer, nullable=False),
    Column("meta", JSON, nullable=True),
    Column("sort_key", Float, nullable=False),
    UniqueConstraint("root_session_id", "id", name="uq_agents_root_id"),
    Index("ix_agents_parent_agent_id", "parent_agent_id"),
    Index("ix_agents_task_kind", "task_kind"),
    Index("ix_agents_model", "model"),
)


agent_events = Table(
    "agent_events",
    DOMAIN_METADATA,
    Column(
        "id",
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column(
        "agent_id",
        String(64),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("event_index", Integer, nullable=False),
    Column("line_no", Integer, nullable=False),
    Column("message_offset", Integer, nullable=False),
    Column("kind", String(16), nullable=False),
    Column("name", String(255), nullable=True),
    Column("description", Text, nullable=True),
    Column("tool_use_id", String(128), nullable=True),
    UniqueConstraint("agent_id", "event_index", name="uq_agent_events_agent_index"),
    Index("ix_agent_events_agent_line", "agent_id", "line_no"),
    Index("ix_agent_events_agent_message", "agent_id", "message_offset"),
)


user_turns = Table(
    "user_turns",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "root_session_id",
        String(36),
        ForeignKey("session_families.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    Column("prompt_text", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("line_no", Integer, nullable=False),
    Column("message_offset", Integer, nullable=False),
    UniqueConstraint("root_session_id", "seq", name="uq_user_turns_root_seq"),
    Index("ix_user_turns_root_line", "root_session_id", "line_no"),
)


bad_cases = Table(
    "bad_cases",
    DOMAIN_METADATA,
    Column("bad_case_id", String(64), primary_key=True),
    Column("bad_case_session_id", String(36), nullable=False),
    Column("bad_case_type", String(16), nullable=False),
    Column("object_name", String(128), nullable=False),
    Column("object_type", String(16), nullable=False),
    Column("object_version", String(64), nullable=True),
    Column("bad_case_agent_id", String(64), nullable=True),
    Column("title", String(255), nullable=False),
    Column("bad_case_description", Text, nullable=False),
    Column("meta_data", JSON, nullable=True),
    Column("source", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_bad_cases_session", "bad_case_session_id"),
    Index("ix_bad_cases_agent", "bad_case_agent_id"),
    Index("ix_bad_cases_object", "object_type", "object_name", "object_version"),
)


probe_reports = Table(
    "probe_reports",
    DOMAIN_METADATA,
    Column("probe_id", String(64), primary_key=True),
    Column("session_id", String(36), nullable=False),
    Column("probe_type", String(16), nullable=False),
    Column("probe_object", String(128), nullable=False),
    Column("object_version", String(64), nullable=True),
    Column("attribute_type", String(16), nullable=False),
    Column("probe_description", Text, nullable=False),
    Column("probe_analysis", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_probe_reports_session", "session_id"),
    Index(
        "ix_probe_reports_object",
        "probe_type",
        "probe_object",
        "object_version",
    ),
    Index("ix_probe_reports_attribute", "attribute_type"),
)


bad_case_analysis = Table(
    "bad_case_analysis",
    DOMAIN_METADATA,
    Column(
        "id",
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column(
        "bad_case_id",
        String(64),
        ForeignKey("bad_cases.bad_case_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("analysis_status", String(32), nullable=False),
    Column(
        "probe_id",
        String(64),
        ForeignKey("probe_reports.probe_id"),
        nullable=True,
    ),
    Column("analysis_result", JSON, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("bad_case_id", name="uq_bad_case_analysis_case"),
    Index("ix_bad_case_analysis_probe", "probe_id"),
    Index("ix_bad_case_analysis_status", "analysis_status"),
)


evolution_targets = Table(
    "evolution_targets",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("object_type", String(16), nullable=False),
    Column("object_name", String(128), nullable=False),
    Column("repo_url", String(1024), nullable=False),
    Column("sub_dir", String(512), nullable=False),
    Column("default_ref", String(128), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True, server_default=true()),
    Column(
        "created_by",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "object_type",
        "object_name",
        name="uq_evolution_targets_object",
    ),
    Index("ix_evolution_targets_enabled", "enabled"),
)
