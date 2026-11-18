"""Add isolated attribution evaluation and promotion audit storage.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | None = None
depends_on: str | None = None

QUALITY_COLUMN = sa.Column(
    "quality_status",
    sa.String(length=24),
    nullable=False,
    server_default="candidate",
)


def _has_table(name: str) -> bool:
    """Return whether one table already exists."""
    return inspect(op.get_bind()).has_table(name)


def _columns(name: str) -> set[str]:
    """Return existing column names for one table."""
    return {str(column["name"]) for column in inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    """Store quality state and append-only evaluation/decision evidence."""
    if _has_table("attribution_skill_revisions"):
        if "quality_status" not in _columns("attribution_skill_revisions"):
            op.add_column("attribution_skill_revisions", QUALITY_COLUMN)
        op.execute(
            sa.text(
                "UPDATE attribution_skill_revisions "
                "SET quality_status = CASE "
                "WHEN id = 'attr-skill-platform-default-r1' THEN 'eligible' "
                "ELSE COALESCE(quality_status, 'candidate') END",
            ),
        )
    if not _has_table("attribution_skill_quality_events"):
        op.create_table(
            "attribution_skill_quality_events",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column(
                "skill_revision_id",
                sa.String(length=36),
                sa.ForeignKey("attribution_skill_revisions.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(length=24), nullable=False),
            sa.Column("evaluation_hash", sa.CHAR(length=64), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("actor_id", sa.String(length=36), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_attribution_skill_quality_revision",
            "attribution_skill_quality_events",
            ["skill_revision_id", "created_at"],
        )
        op.create_index(
            "ix_attribution_skill_quality_workspace",
            "attribution_skill_quality_events",
            ["workspace_id", "created_at"],
        )


def downgrade() -> None:
    """Remove promotion audit storage and revision quality state."""
    if _has_table("attribution_skill_quality_events"):
        op.drop_table("attribution_skill_quality_events")
    if not _has_table("attribution_skill_revisions"):
        return
    if "quality_status" not in _columns("attribution_skill_revisions"):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("attribution_skill_revisions") as batch_op:
            batch_op.drop_column("quality_status")
    else:
        op.drop_column("attribution_skill_revisions", "quality_status")
