"""Dialect-neutral trajectory, issue, and evolution configuration tables."""

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.mysql import LONGTEXT

from app.db.models.workspace import DEFAULT_WORKSPACE_ID

DOMAIN_METADATA = MetaData()


trajectory_payloads = Table(
    "trajectory_payloads",
    DOMAIN_METADATA,
    Column(
        "runtime_key",
        String(32),
        primary_key=True,
        nullable=False,
        server_default="claude-code",
    ),
    Column("root_session_id", String(36), primary_key=True),
    Column("agent_id", String(64), primary_key=True),
    Column("agent_kind", String(16), nullable=False),
    Column("payload", Text().with_variant(LONGTEXT, "mysql"), nullable=False),
    Column("agent_meta", JSON, nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("line_count", Integer, nullable=False),
    Column("source_type", String(16), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_trajectory_payloads_updated_at", "runtime_key", "updated_at"),
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
    Column(
        "runtime_key",
        String(32),
        nullable=False,
        server_default="claude-code",
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
        "runtime_key",
        "root_session_id",
        "agent_id",
        name="uq_source_records_runtime_root_agent",
    ),
    Index("ix_source_records_processed_at", "processed_at"),
    Index("ix_source_records_parser_version", "runtime_key", "parser_version"),
)


session_families = Table(
    "session_families",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "runtime_key",
        String(32),
        nullable=False,
        server_default="claude-code",
    ),
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
    Column(
        "execution_outcome",
        String(16),
        nullable=False,
        server_default="legacy_unknown",
    ),
    Column("end_reason", String(32), nullable=True),
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
        "runtime_key",
        String(32),
        nullable=False,
        server_default="claude-code",
    ),
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
    Column(
        "execution_outcome",
        String(16),
        nullable=False,
        server_default="legacy_unknown",
    ),
    Column("end_reason", String(32), nullable=True),
    Column("agent_definition_hash", String(64), nullable=True),
    Column("definition_source", String(32), nullable=True),
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
    Column("tree_index", Integer, nullable=False, server_default="0"),
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
    Column("object_revision", String(96), nullable=True),
    Column("object_version", String(64), nullable=True),
    Column("triggered_at", DateTime(timezone=True), nullable=True),
    Column("definition_hash", String(64), nullable=True),
    Column("file_read_hash", String(64), nullable=True),
    Column("read_complete", Boolean, nullable=True),
    Column("relation_confidence", String(16), nullable=True),
    Column("description", Text, nullable=True),
    Column("tool_use_id", String(128), nullable=True),
    Column("document_id", String(255), nullable=True),
    Column("document_revision", String(96), nullable=True),
    Column("source_path", String(1024), nullable=True),
    Column("retrieval_kind", String(32), nullable=True),
    Column("retrieval_scope", String(512), nullable=True),
    UniqueConstraint("agent_id", "event_index", name="uq_agent_events_agent_index"),
    Index("ix_agent_events_agent_line", "agent_id", "line_no"),
    Index("ix_agent_events_agent_message", "agent_id", "message_offset"),
    Index("ix_agent_events_agent_triggered", "agent_id", "triggered_at"),
    Index("ix_agent_events_object_version", "agent_id", "kind", "name", "object_version"),
    Index(
        "ix_agent_events_knowledge_document",
        "agent_id",
        "kind",
        "document_id",
    ),
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
    Column(
        "workspace_id",
        String(36),
        nullable=False,
        server_default=DEFAULT_WORKSPACE_ID,
    ),
    Column("origin", String(16), nullable=False, server_default="catalog"),
    Column("bad_case_session_id", String(36), nullable=False),
    Column("bad_case_type", String(16), nullable=False),
    Column("object_name", String(128), nullable=False),
    Column("object_type", String(16), nullable=False),
    Column("object_version", String(64), nullable=True),
    Column("bad_case_agent_id", String(64), nullable=True),
    Column("trigger_line", Integer, nullable=True),
    Column("title", String(255), nullable=False),
    Column("bad_case_description", Text, nullable=False),
    Column("meta_data", JSON, nullable=True),
    Column("catalog_label", String(128), nullable=True),
    Column("catalog_synced", Boolean, nullable=False, server_default=text("0")),
    Column("source", String(64), nullable=True),
    Column("session_source", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_bad_cases_session", "bad_case_session_id"),
    Index("ix_bad_cases_agent", "bad_case_agent_id"),
    Index("ix_bad_cases_object", "object_type", "object_name", "object_version"),
    Index("ix_bad_cases_workspace_created", "workspace_id", "created_at"),
    Index(
        "ix_bad_cases_workspace_session",
        "workspace_id",
        "bad_case_session_id",
    ),
    Index("ix_bad_cases_workspace_object", "workspace_id", "object_name"),
    Index("ix_bad_cases_workspace_type", "workspace_id", "bad_case_type"),
    Index("ix_bad_cases_catalog_label", "catalog_label"),
    Index("ix_bad_cases_catalog_synced", "catalog_synced"),
)


workspace_bad_case_labels = Table(
    "workspace_bad_case_labels",
    DOMAIN_METADATA,
    # The migration owns the cross-metadata workspace foreign key.
    Column("workspace_id", String(36), primary_key=True),
    Column("label", String(128), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_bad_case_labels_label", "label"),
)


workspace_bad_cases = Table(
    "workspace_bad_cases",
    DOMAIN_METADATA,
    # The migration owns the cross-metadata workspace foreign key.
    Column("workspace_id", String(36), primary_key=True),
    Column(
        "bad_case_id",
        String(64),
        ForeignKey("bad_cases.bad_case_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("assignment_source", String(24), primary_key=True),
    Column("label", String(128), nullable=True),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_bad_cases_bad_case", "bad_case_id"),
    Index("ix_workspace_bad_cases_label", "label"),
)


probe_reports = Table(
    "probe_reports",
    DOMAIN_METADATA,
    Column("probe_id", String(64), primary_key=True),
    # The migration owns the workspace foreign key; workspace scope columns stay
    # plain strings here so external-table bootstrap never needs the workspace
    # metadata (the same convention as ``bad_cases.workspace_id``).
    Column(
        "workspace_id",
        String(36),
        nullable=False,
        server_default=DEFAULT_WORKSPACE_ID,
    ),
    Column("session_id", String(36), nullable=False),
    Column("probe_type", String(16), nullable=False),
    Column("probe_object", String(128), nullable=False),
    Column("object_version", String(96), nullable=True),
    Column("attribute_type", String(16), nullable=True),
    Column("conclusion", String(16), nullable=False, server_default="attributed"),
    Column("confidence", Double, nullable=False, server_default=text("0.8")),
    Column("probe_description", Text, nullable=False),
    Column("probe_analysis", Text, nullable=False),
    Column("policy_version", String(16), nullable=False, server_default="v1"),
    Column(
        "attribution_engine",
        String(64),
        nullable=False,
        server_default="legacy-probe-import",
    ),
    Column("cache_key", CHAR(64), nullable=True),
    Column("report_schema_version", String(32), nullable=True),
    Column("report_payload", JSON, nullable=True),
    Column("execution_manifest", JSON, nullable=True),
    Column("attribution_skill_name", String(128), nullable=True),
    Column("analyzed_at", DateTime(timezone=True), nullable=True),
    Column("binding_generation", String(36), nullable=True),
    Column("execution_manifest_hash", CHAR(64), nullable=True),
    # ``created_run_id`` / ``last_reused_run_id`` carry migration-owned foreign
    # keys. Declaring them here would require the evolution metadata during
    # external-table bootstrap, so they stay plain strings in the query model.
    Column("created_run_id", String(36), nullable=True),
    Column("last_reused_run_id", String(36), nullable=True),
    Column("reused_count", Integer, nullable=False, server_default="0"),
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
    Index("ix_probe_reports_workspace_object", "workspace_id", "object_version"),
    Index("ix_probe_reports_workspace_updated", "workspace_id", "updated_at"),
    Index("ix_probe_reports_conclusion", "conclusion"),
    Index("ix_probe_reports_manifest_hash", "execution_manifest_hash"),
    Index("uq_probe_reports_cache_key", "cache_key", unique=True),
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
    Column("analysis_status", String(32), nullable=True),
    Column(
        "probe_id",
        String(64),
        ForeignKey("probe_reports.probe_id"),
        nullable=True,
    ),
    Column("analysis_result", JSON, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "bad_case_id",
        "probe_id",
        name="uq_bad_case_analysis_case_probe",
    ),
    Index("ix_bad_case_analysis_probe", "probe_id"),
    Index("ix_bad_case_analysis_status", "analysis_status"),
    Index("ix_bad_case_analysis_case_updated", "bad_case_id", "updated_at"),
)


bad_case_root_sync = Table(
    "bad_case_root_sync",
    DOMAIN_METADATA,
    Column("root_session_id", String(36), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("source_kind", String(16), nullable=False, server_default="global"),
    Column("source_snapshot", JSON, nullable=True),
    Column("attempts", Integer, nullable=False),
    Column("last_error", Text, nullable=True),
    Column("agent_count", Integer, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("synced_at", DateTime(timezone=True), nullable=True),
    Column("next_retry_at", DateTime(timezone=True), nullable=True),
    Column("lease_owner", String(128), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_bad_case_root_sync_status_retry", "status", "next_retry_at"),
)


bad_case_catalog_sync = Table(
    "bad_case_catalog_sync",
    DOMAIN_METADATA,
    Column("id", String(16), primary_key=True),
    Column(
        "last_bad_case_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        nullable=False,
    ),
    Column("synced_count", Integer, nullable=False),
    Column("pending_count", Integer, nullable=False),
    Column("assigned_count", Integer, nullable=False, server_default="0"),
    Column("unassigned_count", Integer, nullable=False, server_default="0"),
    Column("invalid_label_count", Integer, nullable=False, server_default="0"),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("last_error", Text, nullable=True),
    Column("last_run_at", DateTime(timezone=True), nullable=True),
    Column("last_success_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


evolution_targets = Table(
    "evolution_targets",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "workspace_id",
        String(36),
        nullable=False,
        server_default=DEFAULT_WORKSPACE_ID,
    ),
    Column("attribution_package_id", String(64), nullable=True),
    Column("attribution_skill_name", String(128), nullable=True),
    Column("attribution_generation", String(36), nullable=True),
    Column("attribution_owner", String(36), nullable=True),
    Column("attribution_failures", Integer, nullable=False, server_default="0"),
    Column("attribution_error", String(64), nullable=True),
    Column("attribution_snapshot", JSON, nullable=True),
    Column("attribution_due", DateTime(timezone=True), nullable=True),
    Column("attribution_cutoff", DateTime(timezone=True), nullable=True),
    Column("object_type", String(16), nullable=True),
    Column("object_name", String(128), nullable=True),
    Column("repo_url", String(1024), nullable=False),
    Column("sub_dir", String(512), nullable=True),
    Column("default_ref", String(128), nullable=False),
    Column(
        "validation_project_id",
        String(128),
        nullable=False,
        server_default="",
    ),
    Column("test_project_id", String(128), nullable=False, server_default=""),
    Column(
        "primary_metric_key",
        String(128),
        nullable=False,
        server_default="",
    ),
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
        "workspace_id",
        "object_type",
        "object_name",
        name="uq_evolution_targets_workspace_object",
    ),
    Index("ix_evolution_targets_enabled", "enabled"),
    Index("ix_evolution_targets_workspace", "workspace_id"),
)


evolution_target_members = Table(
    "evolution_target_members",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "workspace_id",
        String(36),
        nullable=False,
        server_default=DEFAULT_WORKSPACE_ID,
    ),
    Column(
        "target_id",
        String(36),
        ForeignKey("evolution_targets.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    Column("object_type", String(16), nullable=False),
    Column("object_name", String(128), nullable=False),
    Column("sub_dir", String(512), nullable=False),
    Column("match_by_name", Boolean, nullable=False, server_default=false()),
    Column("definition", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "target_id",
        "object_type",
        "object_name",
        name="uq_evolution_target_members_target_object",
    ),
    UniqueConstraint("target_id", "seq", name="uq_evolution_target_members_target_seq"),
    UniqueConstraint(
        "workspace_id",
        "object_type",
        "object_name",
        name="uq_evolution_target_members_workspace_object",
    ),
    Index(
        "ix_evolution_target_members_object",
        "object_type",
        "object_name",
    ),
    Index("ix_evolution_target_members_workspace", "workspace_id"),
    Index("ix_evolution_target_members_target", "target_id"),
)


attribution_skills = Table(
    "attribution_skills",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("workspace_id", String(36), nullable=True),
    Column("skill_key", String(128), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("built_in", Boolean, nullable=False, server_default=text("0")),
    Column("enabled", Boolean, nullable=False, server_default=true()),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("skill_key", name="uq_attribution_skills_key"),
    Index("ix_attribution_skills_workspace", "workspace_id"),
)


attribution_skill_revisions = Table(
    "attribution_skill_revisions",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "skill_id",
        String(36),
        ForeignKey("attribution_skills.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("revision", Integer, nullable=False),
    Column("content", JSON, nullable=False),
    Column("content_hash", CHAR(64), nullable=False),
    Column("executor_type", String(32), nullable=False),
    Column("output_schema_version", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column(
        "quality_status",
        String(24),
        nullable=False,
        server_default=text("'candidate'"),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("skill_id", "revision", name="uq_attribution_skill_revision"),
    UniqueConstraint("skill_id", "content_hash", name="uq_attribution_skill_content"),
    Index("ix_attribution_skill_revisions_status", "skill_id", "status"),
)


attribution_skill_quality_events = Table(
    "attribution_skill_quality_events",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("workspace_id", String(36), nullable=False),
    Column(
        "skill_revision_id",
        String(36),
        ForeignKey("attribution_skill_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("event_type", String(24), nullable=False),
    Column("evaluation_hash", CHAR(64), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("actor_id", String(36), nullable=False),
    Column("reason", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index(
        "ix_attribution_skill_quality_revision",
        "skill_revision_id",
        "created_at",
    ),
    Index("ix_attribution_skill_quality_workspace", "workspace_id", "created_at"),
)


attribution_skill_bindings = Table(
    "attribution_skill_bindings",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("workspace_id", String(36), nullable=False),
    Column("binding_key", String(64), nullable=False),
    Column(
        "target_id",
        String(36),
        ForeignKey("evolution_targets.id", ondelete="CASCADE"),
        nullable=True,
    ),
    Column(
        "skill_revision_id",
        String(36),
        ForeignKey("attribution_skill_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "binding_key", name="uq_attribution_skill_binding"),
    Index("ix_attribution_skill_bindings_target", "target_id"),
)


attribution_skill_packages = Table(
    "attribution_skill_packages",
    DOMAIN_METADATA,
    Column("id", String(36), primary_key=True),
    Column("workspace_id", String(36), nullable=False),
    Column("skill_name", String(128), nullable=False),
    Column(
        "uploader_id",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("uploader_name", String(255), nullable=False),
    Column("archive_name", String(255), nullable=False),
    Column("file_count", Integer, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("content_hash", CHAR(64), nullable=False),
    Column("storage_path", String(512), nullable=False),
    Column("skill_md_path", String(512), nullable=False),
    Column("prompt_text", Text().with_variant(LONGTEXT, "mysql"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "workspace_id",
        "skill_name",
        name="uq_attribution_skill_packages_workspace_name",
    ),
    Index("ix_attribution_skill_packages_workspace", "workspace_id", "created_at"),
)


attribution_skill_package_bindings = Table(
    "attribution_skill_package_bindings",
    DOMAIN_METADATA,
    Column("workspace_id", String(36), primary_key=True),
    Column(
        "package_id",
        String(36),
        ForeignKey("attribution_skill_packages.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "updated_by",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_attribution_skill_package_bindings_package", "package_id"),
)
