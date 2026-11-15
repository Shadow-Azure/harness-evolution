"""Dialect-neutral workspace, membership, and ingest credential tables."""

from sqlalchemy import (
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

WORKSPACE_METADATA = MetaData()

DEFAULT_WORKSPACE_ID = "ws-default"
"""Stable space for writes that have no explicit workspace context yet."""

workspaces = Table(
    "workspaces",
    WORKSPACE_METADATA,
    Column("id", String(36), primary_key=True),
    Column("name", String(128), nullable=False, unique=True),
    Column("mark", String(255), nullable=False, server_default=""),
    Column("quota", Integer, nullable=False),
    Column("status", String(16), nullable=False, server_default="active"),
    Column(
        "created_by",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("ix_workspaces_created_at", workspaces.c.created_at.desc())

workspace_members = Table(
    "workspace_members",
    WORKSPACE_METADATA,
    Column(
        "workspace_id",
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("role", String(16), nullable=False),
    Column("joined_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_workspace_members_user", "user_id"),
)

workspace_ingest_credentials = Table(
    "workspace_ingest_credentials",
    WORKSPACE_METADATA,
    Column("id", String(36), primary_key=True),
    Column(
        "workspace_id",
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("credential_hash", CHAR(64), nullable=False),
    Column("credential_prefix", String(12), nullable=False),
    Column(
        "created_by",
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_used_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint(
        "credential_hash",
        name="uq_workspace_ingest_credentials_hash",
    ),
    Index(
        "ix_workspace_ingest_credentials_workspace_revoked",
        "workspace_id",
        "revoked_at",
    ),
)
