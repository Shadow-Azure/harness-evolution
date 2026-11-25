"""Add label rules and explicit workspace badcase assignments."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0033"
down_revision = "0032"


def upgrade() -> None:
    """Create routing tables and preserve every legacy workspace owner."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("bad_cases"):
        bad_case_columns = {str(column["name"]) for column in inspector.get_columns("bad_cases")}
        if "catalog_label" not in bad_case_columns:
            with op.batch_alter_table("bad_cases") as batch_op:
                batch_op.add_column(sa.Column("catalog_label", sa.String(128)))
                batch_op.add_column(
                    sa.Column(
                        "catalog_synced",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("0"),
                    ),
                )
                batch_op.create_index(
                    "ix_bad_cases_catalog_label",
                    ["catalog_label"],
                    unique=False,
                )
                batch_op.create_index(
                    "ix_bad_cases_catalog_synced",
                    ["catalog_synced"],
                    unique=False,
                )

    # Project the stored label onto pre-existing catalog facts so rules can
    # route historical data without replaying the catalog cursor. Invalid or
    # missing labels stay NULL, matching the sync-time contract.
    if inspector.has_table("bad_cases"):
        if bind.dialect.name == "sqlite":
            op.execute(
                sa.text(
                    """
                    UPDATE bad_cases
                    SET catalog_label = CASE
                        WHEN meta_data IS NOT NULL
                         AND json_valid(meta_data)
                         AND json_type(meta_data, '$.label') = 'text'
                         AND length(json_extract(meta_data, '$.label')) BETWEEN 1 AND 128
                         AND json_extract(meta_data, '$.label')
                             = trim(json_extract(meta_data, '$.label'))
                        THEN json_extract(meta_data, '$.label')
                        ELSE NULL
                    END,
                    catalog_synced = 1
                    WHERE origin = 'catalog'
                    """,
                ),
            )
        elif bind.dialect.name == "mysql":
            op.execute(
                sa.text(
                    """
                    UPDATE bad_cases
                    SET catalog_label = CASE
                        WHEN JSON_TYPE(JSON_EXTRACT(meta_data, '$.label')) = 'STRING'
                         AND CHAR_LENGTH(JSON_UNQUOTE(JSON_EXTRACT(meta_data, '$.label')))
                             BETWEEN 1 AND 128
                         AND JSON_UNQUOTE(JSON_EXTRACT(meta_data, '$.label'))
                             = TRIM(JSON_UNQUOTE(JSON_EXTRACT(meta_data, '$.label')))
                        THEN JSON_UNQUOTE(JSON_EXTRACT(meta_data, '$.label'))
                        ELSE NULL
                    END,
                    catalog_synced = 1
                    WHERE origin = 'catalog'
                    """,
                ),
            )

    if inspector.has_table("bad_case_catalog_sync"):
        sync_columns = {
            str(column["name"]) for column in inspector.get_columns("bad_case_catalog_sync")
        }
        missing_sync_columns = [
            name
            for name in ("assigned_count", "unassigned_count", "invalid_label_count")
            if name not in sync_columns
        ]
        if missing_sync_columns:
            with op.batch_alter_table("bad_case_catalog_sync") as batch_op:
                for name in missing_sync_columns:
                    batch_op.add_column(
                        sa.Column(
                            name,
                            sa.Integer(),
                            nullable=False,
                            server_default="0",
                        ),
                    )

    if not inspector.has_table("workspace_bad_case_labels"):
        op.create_table(
            "workspace_bad_case_labels",
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("label", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id"],
                ["workspaces.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("workspace_id", "label"),
        )
        op.create_index(
            "ix_workspace_bad_case_labels_label",
            "workspace_bad_case_labels",
            ["label"],
            unique=False,
        )

    if not inspector.has_table("workspace_bad_cases"):
        op.create_table(
            "workspace_bad_cases",
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("bad_case_id", sa.String(64), nullable=False),
            sa.Column("assignment_source", sa.String(24), nullable=False),
            sa.Column("label", sa.String(128), nullable=True),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id"],
                ["workspaces.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["bad_case_id"],
                ["bad_cases.bad_case_id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint(
                "workspace_id",
                "bad_case_id",
                "assignment_source",
            ),
        )
        op.create_index(
            "ix_workspace_bad_cases_bad_case",
            "workspace_bad_cases",
            ["bad_case_id"],
            unique=False,
        )
        op.create_index(
            "ix_workspace_bad_cases_label",
            "workspace_bad_cases",
            ["label"],
            unique=False,
        )

    inspector = inspect(bind)
    if inspector.has_table("bad_cases") and inspector.has_table("workspace_bad_cases"):
        assignment_select = """
                INTO workspace_bad_cases (
                  workspace_id, bad_case_id, assignment_source, label, assigned_at
                )
                SELECT bc.workspace_id,
                       bc.bad_case_id,
                       CASE WHEN bc.origin = 'report'
                            THEN 'direct_ingest' ELSE 'legacy_owner' END,
                       NULL,
                       CURRENT_TIMESTAMP
                FROM bad_cases bc
                WHERE bc.workspace_id IS NOT NULL
"""
        if bind.dialect.name == "sqlite":
            op.execute(sa.text("INSERT OR IGNORE" + assignment_select))
        else:
            op.execute(sa.text("INSERT IGNORE" + assignment_select))


def downgrade() -> None:
    """Remove routing state without deleting canonical badcase facts."""
    inspector = inspect(op.get_bind())
    if inspector.has_table("bad_case_catalog_sync"):
        sync_columns = {
            str(column["name"]) for column in inspector.get_columns("bad_case_catalog_sync")
        }
        with op.batch_alter_table("bad_case_catalog_sync") as batch_op:
            for name in ("invalid_label_count", "unassigned_count", "assigned_count"):
                if name in sync_columns:
                    batch_op.drop_column(name)
    if inspector.has_table("workspace_bad_cases"):
        op.drop_table("workspace_bad_cases")
    if inspector.has_table("workspace_bad_case_labels"):
        op.drop_table("workspace_bad_case_labels")
    if inspector.has_table("bad_cases"):
        columns = {str(column["name"]) for column in inspector.get_columns("bad_cases")}
        if "catalog_label" in columns:
            with op.batch_alter_table("bad_cases") as batch_op:
                batch_op.drop_index("ix_bad_cases_catalog_synced")
                batch_op.drop_index("ix_bad_cases_catalog_label")
                batch_op.drop_column("catalog_synced")
                batch_op.drop_column("catalog_label")
