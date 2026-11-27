"""Persist multiple same-repository members per evolution target."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0035"
down_revision = "0034"


def _uuid() -> str:
    """Return one 36-character identifier independent of the application runtime."""
    return str(uuid.uuid4())


def _existing_columns(bind: object, table: str) -> set[str]:
    """Return the reflected column names of an existing table."""
    return {str(column["name"]) for column in inspect(bind).get_columns(table)}


def _member_definition(target: Mapping[str, Any]) -> dict[str, Any] | None:
    """Read the frozen definition snapshot stored on a legacy target row."""
    snapshot = target.get("attribution_snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    definition = snapshot.get("definition")
    return dict(definition) if isinstance(definition, Mapping) else None


def upgrade() -> None:
    """Create member tables, backfill history, and relax legacy target columns."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("evolution_target_members"):
        op.create_table(
            "evolution_target_members",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column(
                "workspace_id",
                sa.String(36),
                nullable=False,
                server_default="ws-default",
            ),
            sa.Column("target_id", sa.String(36), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("object_type", sa.String(16), nullable=False),
            sa.Column("object_name", sa.String(128), nullable=False),
            sa.Column("sub_dir", sa.String(512), nullable=False),
            sa.Column("definition", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["target_id"],
                ["evolution_targets.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "target_id",
                "object_type",
                "object_name",
                name="uq_evolution_target_members_target_object",
            ),
            sa.UniqueConstraint(
                "target_id",
                "seq",
                name="uq_evolution_target_members_target_seq",
            ),
            sa.UniqueConstraint(
                "workspace_id",
                "object_type",
                "object_name",
                name="uq_evolution_target_members_workspace_object",
            ),
        )
        op.create_index(
            "ix_evolution_target_members_object",
            "evolution_target_members",
            ["object_type", "object_name"],
            unique=False,
        )
        op.create_index(
            "ix_evolution_target_members_workspace",
            "evolution_target_members",
            ["workspace_id"],
            unique=False,
        )
        op.create_index(
            "ix_evolution_target_members_target",
            "evolution_target_members",
            ["target_id"],
            unique=False,
        )

    inspector = inspect(bind)
    if not inspector.has_table("evolution_run_targets"):
        op.create_table(
            "evolution_run_targets",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("target_config_id", sa.String(36), nullable=True),
            sa.Column("member_id", sa.String(36), nullable=True),
            sa.Column("object_type", sa.String(16), nullable=False),
            sa.Column("object_name", sa.String(128), nullable=False),
            sa.Column("target_version", sa.String(96), nullable=False),
            sa.Column("target_revision", sa.String(96), nullable=True),
            sa.Column("sub_dir", sa.String(512), nullable=False),
            sa.Column("base_commit", sa.String(40), nullable=True),
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["evolution_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["target_config_id"],
                ["evolution_targets.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "run_id",
                "seq",
                name="uq_evolution_run_targets_run_seq",
            ),
            sa.UniqueConstraint(
                "run_id",
                "object_type",
                "object_name",
                name="uq_evolution_run_targets_run_object",
            ),
        )
        op.create_index(
            "ix_evolution_run_targets_run",
            "evolution_run_targets",
            ["run_id"],
            unique=False,
        )

    if inspector.has_table("evolution_run_candidates"):
        candidate_columns = _existing_columns(bind, "evolution_run_candidates")
        missing = [
            name
            for name in ("object_type", "object_name", "object_revision")
            if name not in candidate_columns
        ]
        if missing:
            with op.batch_alter_table("evolution_run_candidates") as batch_op:
                if "object_type" in missing:
                    batch_op.add_column(sa.Column("object_type", sa.String(16)))
                if "object_name" in missing:
                    batch_op.add_column(sa.Column("object_name", sa.String(128)))
                if "object_revision" in missing:
                    batch_op.add_column(sa.Column("object_revision", sa.String(96)))

    inspector = inspect(bind)
    metadata = sa.MetaData()
    if inspector.has_table("evolution_targets") and inspector.has_table("evolution_target_members"):
        targets = sa.Table("evolution_targets", metadata, autoload_with=bind)
        members = sa.Table("evolution_target_members", metadata, autoload_with=bind)
        existing_targets = set(
            bind.execute(sa.select(members.c.target_id).distinct()).scalars().all(),
        )
        rows = (
            bind.execute(
                sa.select(
                    targets.c.id,
                    targets.c.workspace_id,
                    targets.c.object_type,
                    targets.c.object_name,
                    targets.c.sub_dir,
                    targets.c.attribution_snapshot,
                    targets.c.created_at,
                ),
            )
            .mappings()
            .all()
        )
        pending = [
            {
                "id": _uuid(),
                "workspace_id": row["workspace_id"] or "ws-default",
                "target_id": row["id"],
                "seq": 0,
                "object_type": row["object_type"],
                "object_name": row["object_name"],
                "sub_dir": row["sub_dir"],
                "definition": _member_definition(row),
                "created_at": row["created_at"],
            }
            for row in rows
            if row["id"] not in existing_targets
            and row["object_type"]
            and row["object_name"]
            and row["sub_dir"]
        ]
        if pending:
            bind.execute(sa.insert(members), pending)

    if inspector.has_table("evolution_runs") and inspector.has_table("evolution_run_targets"):
        runs = sa.Table("evolution_runs", metadata, autoload_with=bind)
        run_targets = sa.Table("evolution_run_targets", metadata, autoload_with=bind)
        existing_runs = set(
            bind.execute(sa.select(run_targets.c.run_id).distinct()).scalars().all(),
        )
        run_rows = (
            bind.execute(
                sa.select(
                    runs.c.id,
                    runs.c.target_config_id,
                    runs.c.target_type,
                    runs.c.target_name,
                    runs.c.target_version,
                    runs.c.target_revision,
                    runs.c.sub_dir,
                    runs.c.base_commit,
                ),
            )
            .mappings()
            .all()
        )
        pending_runs = [
            {
                "id": _uuid(),
                "run_id": row["id"],
                "seq": 0,
                "target_config_id": row["target_config_id"],
                "member_id": None,
                "object_type": row["target_type"],
                "object_name": row["target_name"],
                "target_version": row["target_version"],
                "target_revision": row["target_revision"],
                "sub_dir": row["sub_dir"],
                "base_commit": row["base_commit"],
            }
            for row in run_rows
            if row["id"] not in existing_runs
        ]
        if pending_runs:
            bind.execute(sa.insert(run_targets), pending_runs)

    if inspector.has_table("evolution_targets"):
        target_columns = inspect(bind).get_columns("evolution_targets")
        by_name = {str(column["name"]): column for column in target_columns}
        relax = [
            name
            for name in ("object_type", "object_name", "sub_dir")
            if name in by_name and by_name[name].get("nullable") is False
        ]
        if relax:
            with op.batch_alter_table("evolution_targets") as batch_op:
                for name in relax:
                    batch_op.alter_column(name, existing_type=by_name[name]["type"], nullable=True)


def downgrade() -> None:
    """Remove member snapshots and restore the single-object write contract."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("evolution_targets"):
        columns = _existing_columns(bind, "evolution_targets")
        nullable = [name for name in ("object_type", "object_name", "sub_dir") if name in columns]
        if nullable:
            targets = sa.Table("evolution_targets", sa.MetaData(), autoload_with=bind)
            bind.execute(
                sa.update(targets)
                .where(targets.c.object_type.is_(None))
                .values(object_type="skill"),
            )
            bind.execute(
                sa.update(targets)
                .where(targets.c.object_name.is_(None))
                .values(object_name="unknown"),
            )
            bind.execute(
                sa.update(targets).where(targets.c.sub_dir.is_(None)).values(sub_dir="."),
            )
            reflected = {
                str(column["name"]): column
                for column in inspect(bind).get_columns("evolution_targets")
            }
            with op.batch_alter_table("evolution_targets") as batch_op:
                for name in nullable:
                    batch_op.alter_column(
                        name,
                        existing_type=reflected[name]["type"],
                        nullable=False,
                    )
    if inspector.has_table("evolution_run_targets"):
        op.drop_table("evolution_run_targets")
    if inspector.has_table("evolution_target_members"):
        op.drop_table("evolution_target_members")
    if inspector.has_table("evolution_run_candidates"):
        columns = _existing_columns(bind, "evolution_run_candidates")
        drop = [
            name for name in ("object_type", "object_name", "object_revision") if name in columns
        ]
        if drop:
            with op.batch_alter_table("evolution_run_candidates") as batch_op:
                for name in drop:
                    batch_op.drop_column(name)
