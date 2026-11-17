"""Add attribution Skill revisions, bindings, and run snapshots.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-17
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | None = None
depends_on: str | None = None

PLATFORM_SKILL_ID = "attribution-skill-platform-default"
PLATFORM_REVISION_ID = "attr-skill-platform-default-r1"
PLATFORM_CONTENT_HASH = "7e30d5d3721030420842f9e1f1b08e9a1c33644eb7a78eca82bbd06abbca525d"
RUN_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("attribution_skill_key", sa.String(length=128), nullable=True),
    sa.Column("attribution_skill_revision", sa.Integer(), nullable=True),
    sa.Column("attribution_skill_content_hash", sa.String(length=64), nullable=True),
)


def _has_table(name: str) -> bool:
    """Return whether one table already exists."""
    return inspect(op.get_bind()).has_table(name)


def _columns(name: str) -> set[str]:
    """Return existing column names for one table."""
    return {str(column["name"]) for column in inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    """Create immutable Skill storage and seed the protected platform default."""
    if not _has_table("attribution_skills"):
        op.create_table(
            "attribution_skills",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=True),
            sa.Column("skill_key", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("skill_key", name="uq_attribution_skills_key"),
        )
        op.create_index("ix_attribution_skills_workspace", "attribution_skills", ["workspace_id"])
    if not _has_table("attribution_skill_revisions"):
        op.create_table(
            "attribution_skill_revisions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "skill_id",
                sa.String(length=36),
                sa.ForeignKey("attribution_skills.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("content", sa.JSON(), nullable=False),
            sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
            sa.Column("executor_type", sa.String(length=32), nullable=False),
            sa.Column("output_schema_version", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("skill_id", "revision", name="uq_attribution_skill_revision"),
            sa.UniqueConstraint("skill_id", "content_hash", name="uq_attribution_skill_content"),
        )
        op.create_index(
            "ix_attribution_skill_revisions_status",
            "attribution_skill_revisions",
            ["skill_id", "status"],
        )
    if not _has_table("attribution_skill_bindings"):
        op.create_table(
            "attribution_skill_bindings",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("binding_key", sa.String(length=64), nullable=False),
            sa.Column(
                "target_id",
                sa.String(length=36),
                sa.ForeignKey("evolution_targets.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "skill_revision_id",
                sa.String(length=36),
                sa.ForeignKey("attribution_skill_revisions.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "workspace_id",
                "binding_key",
                name="uq_attribution_skill_binding",
            ),
        )
        op.create_index(
            "ix_attribution_skill_bindings_target",
            "attribution_skill_bindings",
            ["target_id"],
        )
    if _has_table("evolution_runs"):
        existing = _columns("evolution_runs")
        for column in RUN_COLUMNS:
            if str(column.name) not in existing:
                op.add_column("evolution_runs", column)

    now = datetime.now(UTC)
    skills = sa.table(
        "attribution_skills",
        sa.column("id", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("skill_key", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("built_in", sa.Boolean()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    revisions = sa.table(
        "attribution_skill_revisions",
        sa.column("id", sa.String()),
        sa.column("skill_id", sa.String()),
        sa.column("revision", sa.Integer()),
        sa.column("content", sa.JSON()),
        sa.column("content_hash", sa.String()),
        sa.column("executor_type", sa.String()),
        sa.column("output_schema_version", sa.String()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    existing_skill = (
        op.get_bind()
        .execute(
            sa.select(skills.c.id).where(skills.c.id == PLATFORM_SKILL_ID),
        )
        .first()
    )
    if existing_skill is None:
        op.bulk_insert(
            skills,
            [
                {
                    "id": PLATFORM_SKILL_ID,
                    "workspace_id": None,
                    "skill_key": "platform-default",
                    "display_name": "Platform Default Attribution Skill",
                    "description": "Built-in deterministic attribution instructions.",
                    "built_in": True,
                    "enabled": True,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        op.bulk_insert(
            revisions,
            [
                {
                    "id": PLATFORM_REVISION_ID,
                    "skill_id": PLATFORM_SKILL_ID,
                    "revision": 1,
                    "content": {
                        "instructions": "Use platform deterministic attribution rules.",
                        "tools": [],
                    },
                    "content_hash": PLATFORM_CONTENT_HASH,
                    "executor_type": "builtin_rule",
                    "output_schema_version": "probe-report/v2",
                    "status": "published",
                    "created_at": now,
                }
            ],
        )


def downgrade() -> None:
    """Remove Skill storage and run snapshots."""
    if _has_table("evolution_runs"):
        existing = _columns("evolution_runs")
        present = [str(column.name) for column in RUN_COLUMNS if str(column.name) in existing]
        if present and op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("evolution_runs") as batch_op:
                for name in present:
                    batch_op.drop_column(name)
        else:
            for name in present:
                op.drop_column("evolution_runs", name)
    for table in (
        "attribution_skill_bindings",
        "attribution_skill_revisions",
        "attribution_skills",
    ):
        if _has_table(table):
            op.drop_table(table)
