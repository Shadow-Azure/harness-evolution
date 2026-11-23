"""Add workspace attribution Skill package assets and active bindings.

Revision ID: 0027
Revises: 0026a
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.mysql import LONGTEXT

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create package metadata and the single effective package per workspace."""
    if not inspect(op.get_bind()).has_table("attribution_skill_packages"):
        op.create_table(
            "attribution_skill_packages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("skill_name", sa.String(length=128), nullable=False),
            sa.Column(
                "uploader_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("uploader_name", sa.String(length=255), nullable=False),
            sa.Column("archive_name", sa.String(length=255), nullable=False),
            sa.Column("file_count", sa.Integer(), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("skill_md_path", sa.String(length=512), nullable=False),
            sa.Column("prompt_text", sa.Text().with_variant(LONGTEXT, "mysql"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "workspace_id",
                "skill_name",
                name="uq_attribution_skill_packages_workspace_name",
            ),
        )
        op.create_index(
            "ix_attribution_skill_packages_workspace",
            "attribution_skill_packages",
            ["workspace_id", "created_at"],
        )
    if not inspect(op.get_bind()).has_table("attribution_skill_package_bindings"):
        op.create_table(
            "attribution_skill_package_bindings",
            sa.Column("workspace_id", sa.String(length=36), primary_key=True),
            sa.Column(
                "package_id",
                sa.String(length=36),
                sa.ForeignKey("attribution_skill_packages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "updated_by",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_attribution_skill_package_bindings_package",
            "attribution_skill_package_bindings",
            ["package_id"],
        )


def downgrade() -> None:
    """Drop package bindings before package metadata."""
    inspector = inspect(op.get_bind())
    if inspector.has_table("attribution_skill_package_bindings"):
        op.drop_table("attribution_skill_package_bindings")
    if inspector.has_table("attribution_skill_packages"):
        op.drop_table("attribution_skill_packages")
