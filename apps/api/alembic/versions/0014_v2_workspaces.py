"""Add V2 workspaces and scope the workspace-owned business tables.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-15
"""

from datetime import UTC, datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import CHAR, inspect

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None

DEFAULT_WORKSPACE_ID = "ws-default"
DEFAULT_WORKSPACE_NAME = "默认空间"
DEFAULT_WORKSPACE_MARK = "迁移回填：无空间上下文的存量数据"  # noqa: RUF001
SHANGHAI = timezone(timedelta(hours=8))

SCOPED_TABLES = (
    "bad_cases",
    "evolution_targets",
    "evolution_runs",
    "evolution_run_events",
)

SCOPED_INDEXES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "bad_cases": (
        ("ix_bad_cases_workspace_created", ("workspace_id", "created_at")),
        (
            "ix_bad_cases_workspace_session",
            ("workspace_id", "bad_case_session_id"),
        ),
        ("ix_bad_cases_workspace_object", ("workspace_id", "object_name")),
        ("ix_bad_cases_workspace_type", ("workspace_id", "bad_case_type")),
    ),
    "evolution_targets": (("ix_evolution_targets_workspace", ("workspace_id",)),),
    "evolution_runs": (),
    "evolution_run_events": (("ix_evolution_run_events_workspace", ("workspace_id",)),),
}

RUN_TARGET_BACKUP = "_v2_run_target_backup"


def _has_table(name: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(name)


def _scoped_tables() -> list[str]:
    """Return the workspace-owned tables that exist in this deployment."""
    return [name for name in SCOPED_TABLES if _has_table(name)]


def _now() -> datetime:
    """Return the application-local timestamp used for migration-owned rows."""
    return datetime.now(UTC).astimezone(SHANGHAI).replace(tzinfo=None)


def _create_workspace_tables() -> None:
    """Create the workspace, member, and ingest-credential tables."""
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("mark", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("quota", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_workspaces_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_workspaces_name"),
    )
    op.execute(
        "CREATE INDEX ix_workspaces_created_at ON workspaces (created_at DESC)",
    )
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_members_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_workspace_members_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_index(
        "ix_workspace_members_user",
        "workspace_members",
        ["user_id"],
    )
    op.create_table(
        "workspace_ingest_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("credential_hash", CHAR(length=64), nullable=False),
        sa.Column("credential_prefix", sa.String(length=12), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_ingest_credentials_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_workspace_ingest_credentials_created_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "credential_hash",
            name="uq_workspace_ingest_credentials_hash",
        ),
    )
    op.create_index(
        "ix_workspace_ingest_credentials_workspace_revoked",
        "workspace_ingest_credentials",
        ["workspace_id", "revoked_at"],
    )


def _extend_users() -> None:
    """Add the provider mapping fields and their identity uniqueness rule."""
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=32),
            nullable=False,
            server_default="password",
        ),
    )
    op.add_column(
        "users",
        sa.Column("external_subject", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "uq_users_auth_provider_external_subject",
        "users",
        ["auth_provider", "external_subject"],
        unique=True,
    )


def _seed_default_workspace() -> None:
    """Insert the migration workspace once, sized from the existing case count."""
    bind = op.get_bind()
    case_count = 0
    if _has_table("bad_cases"):
        case_count = int(
            bind.execute(sa.text("SELECT COUNT(*) FROM bad_cases")).scalar_one(),
        )
    exists = bind.execute(
        sa.text("SELECT 1 FROM workspaces WHERE id = :workspace_id"),
        {"workspace_id": DEFAULT_WORKSPACE_ID},
    ).first()
    if exists is not None:
        return
    now = _now()
    bind.execute(
        sa.text(
            "INSERT INTO workspaces "
            "(id, name, mark, quota, status, created_by, created_at, updated_at) "
            "VALUES (:id, :name, :mark, :quota, 'active', NULL, :now, :now)",
        ),
        {
            "id": DEFAULT_WORKSPACE_ID,
            "name": DEFAULT_WORKSPACE_NAME,
            "mark": DEFAULT_WORKSPACE_MARK,
            "quota": case_count + 50,
            "now": now,
        },
    )


def _add_scope_column(table: str) -> None:
    """Add and backfill workspace_id, then tighten it without rewriting SQLite rows."""
    if op.get_bind().dialect.name == "sqlite":
        op.add_column(
            table,
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                nullable=False,
                server_default=DEFAULT_WORKSPACE_ID,
            ),
        )
    else:
        op.add_column(
            table,
            sa.Column("workspace_id", sa.String(length=36), nullable=True),
        )
    op.execute(
        f"UPDATE {table} SET workspace_id = '{DEFAULT_WORKSPACE_ID}' WHERE workspace_id IS NULL",  # noqa: S608
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            table,
            "workspace_id",
            existing_type=sa.String(length=36),
            nullable=False,
            server_default=DEFAULT_WORKSPACE_ID,
        )


def _create_scope_indexes(table: str) -> None:
    """Create the workspace-leading indexes for one scoped table."""
    if table == "evolution_runs":
        op.execute(
            "CREATE INDEX ix_evolution_runs_workspace_created "
            "ON evolution_runs (workspace_id, created_at DESC)",
        )
        return
    for name, columns in SCOPED_INDEXES[table]:
        op.create_index(name, table, list(columns))


def _drop_scope_indexes(table: str) -> None:
    """Drop the workspace-leading indexes for one scoped table."""
    if table == "evolution_runs":
        op.drop_index("ix_evolution_runs_workspace_created", table_name=table)
        return
    for name, _columns in SCOPED_INDEXES[table]:
        op.drop_index(name, table_name=table)


def _add_scope_foreign_key(table: str) -> None:
    """Add the workspace foreign key where the design owns that reference."""
    if table == "evolution_run_events" or op.get_bind().dialect.name == "sqlite":
        return
    op.create_foreign_key(
        f"fk_{table}_workspace",
        table,
        "workspaces",
        ["workspace_id"],
        ["id"],
    )


def _backup_run_targets() -> None:
    """Preserve run target references across a SQLite target-table rebuild."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"CREATE TABLE {RUN_TARGET_BACKUP} "
            "(id VARCHAR(36) PRIMARY KEY, target_config_id VARCHAR(36))",
        ),
    )
    bind.execute(
        sa.text(
            f"INSERT INTO {RUN_TARGET_BACKUP} (id, target_config_id) "  # noqa: S608
            "SELECT id, target_config_id FROM evolution_runs "
            "WHERE target_config_id IS NOT NULL",
        ),
    )


def _restore_run_targets() -> None:
    """Restore run target references after a SQLite target-table rebuild."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE evolution_runs SET target_config_id = ("  # noqa: S608
            f"SELECT backup.target_config_id FROM {RUN_TARGET_BACKUP} AS backup "
            "WHERE backup.id = evolution_runs.id) "
            f"WHERE id IN (SELECT id FROM {RUN_TARGET_BACKUP})",
        ),
    )
    bind.execute(sa.text(f"DROP TABLE {RUN_TARGET_BACKUP}"))


def _replace_target_unique() -> None:
    """Move target uniqueness from the global object to its workspace."""
    if op.get_bind().dialect.name == "sqlite":
        _backup_run_targets()
        try:
            with op.batch_alter_table("evolution_targets") as batch_op:
                batch_op.drop_constraint(
                    "uq_evolution_targets_object",
                    type_="unique",
                )
                batch_op.create_unique_constraint(
                    "uq_evolution_targets_workspace_object",
                    ["workspace_id", "object_type", "object_name"],
                )
        finally:
            _restore_run_targets()
        return
    op.drop_constraint(
        "uq_evolution_targets_object",
        "evolution_targets",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_evolution_targets_workspace_object",
        "evolution_targets",
        ["workspace_id", "object_type", "object_name"],
    )


def _join_existing_users() -> None:
    """Give every existing user a viewer row in the default workspace."""
    now = _now()
    op.get_bind().execute(
        sa.text(
            "INSERT INTO workspace_members "
            "(workspace_id, user_id, role, joined_at, updated_at) "
            "SELECT :workspace_id, users.id, 'viewer', :now, :now FROM users",
        ),
        {"workspace_id": DEFAULT_WORKSPACE_ID, "now": now},
    )


def upgrade() -> None:
    """Create the workspace foundation and backfill every scoped table."""
    _extend_users()
    _create_workspace_tables()
    _seed_default_workspace()
    for table in _scoped_tables():
        _add_scope_column(table)
        _create_scope_indexes(table)
        _add_scope_foreign_key(table)
    _replace_target_unique()
    _join_existing_users()


def _foreign_key_names(table: str) -> set[str]:
    """Return the named foreign keys currently attached to one table."""
    return {
        str(foreign_key["name"])
        for foreign_key in inspect(op.get_bind()).get_foreign_keys(table)
        if foreign_key.get("name") is not None
    }


def _drop_scope_column(table: str) -> None:
    """Drop one workspace scope column without losing unrelated rows."""
    foreign_key = f"fk_{table}_workspace"
    if op.get_bind().dialect.name != "sqlite" and foreign_key in _foreign_key_names(
        table,
    ):
        op.drop_constraint(
            foreign_key,
            table,
            type_="foreignkey",
        )
    _drop_scope_indexes(table)
    op.drop_column(table, "workspace_id")


def downgrade() -> None:
    """Remove the workspace foundation and restore the V1 target uniqueness rule."""
    if _has_table("evolution_targets"):
        if op.get_bind().dialect.name == "sqlite":
            _drop_scope_indexes("evolution_targets")
            _backup_run_targets()
            try:
                with op.batch_alter_table("evolution_targets") as batch_op:
                    batch_op.drop_constraint(
                        "uq_evolution_targets_workspace_object",
                        type_="unique",
                    )
                    batch_op.drop_column("workspace_id")
                    batch_op.create_unique_constraint(
                        "uq_evolution_targets_object",
                        ["object_type", "object_name"],
                    )
            finally:
                _restore_run_targets()
        else:
            op.drop_constraint(
                "fk_evolution_targets_workspace",
                "evolution_targets",
                type_="foreignkey",
            )
            op.drop_index(
                "ix_evolution_targets_workspace",
                table_name="evolution_targets",
            )
            op.drop_constraint(
                "uq_evolution_targets_workspace_object",
                "evolution_targets",
                type_="unique",
            )
            op.drop_column("evolution_targets", "workspace_id")
            op.create_unique_constraint(
                "uq_evolution_targets_object",
                "evolution_targets",
                ["object_type", "object_name"],
            )
    for table in ("bad_cases", "evolution_runs", "evolution_run_events"):
        if _has_table(table):
            _drop_scope_column(table)
    op.drop_index(
        "ix_workspace_ingest_credentials_workspace_revoked",
        table_name="workspace_ingest_credentials",
    )
    op.drop_table("workspace_ingest_credentials")
    op.drop_index("ix_workspace_members_user", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index("ix_workspaces_created_at", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index(
        "uq_users_auth_provider_external_subject",
        table_name="users",
    )
    op.drop_column("users", "external_subject")
    op.drop_column("users", "auth_provider")
