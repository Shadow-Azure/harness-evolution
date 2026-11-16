"""Add runtime identity to payloads, source cursors, and sessions.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None

DEFAULT_RUNTIME_KEY = "claude-code"
TEMPORARY_SUFFIX = "_runtime_v1"
long_text_type = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")
json_type = sa.JSON()
sqlite_integer = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _trajectory_table(name: str, *, with_runtime: bool) -> None:
    """Create one trajectory payload table in the target identity order."""
    columns: list[sa.Column[object]] = []
    if with_runtime:
        columns.append(
            sa.Column(
                "runtime_key",
                sa.String(32),
                primary_key=True,
                nullable=False,
                server_default=DEFAULT_RUNTIME_KEY,
            ),
        )
    columns.extend(
        [
            sa.Column("root_session_id", sa.String(36), primary_key=True),
            sa.Column("agent_id", sa.String(64), primary_key=True),
            sa.Column("agent_kind", sa.String(16), nullable=False),
            sa.Column("payload", long_text_type, nullable=False),
            sa.Column("agent_meta", json_type, nullable=True),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("line_count", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(16), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ],
    )
    op.create_table(name, *columns)


def _source_table(name: str, *, with_runtime: bool) -> None:
    """Create one processing-index table in the target identity order."""
    columns: list[sa.Column[object]] = [
        sa.Column("id", sqlite_integer, primary_key=True, autoincrement=True),
    ]
    if with_runtime:
        columns.append(
            sa.Column(
                "runtime_key",
                sa.String(32),
                nullable=False,
                server_default=DEFAULT_RUNTIME_KEY,
            ),
        )
    columns.extend(
        [
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
        ],
    )
    if with_runtime:
        columns.append(
            sa.UniqueConstraint(
                "runtime_key",
                "root_session_id",
                "agent_id",
                name="uq_source_records_runtime_root_agent",
            ),
        )
    else:
        columns.append(
            sa.UniqueConstraint(
                "root_session_id",
                "agent_id",
                name="uq_source_records_root_agent",
            ),
        )
    op.create_table(name, *columns)


def _rebuild_sqlite_trajectory(*, with_runtime: bool) -> None:
    """Rebuild the SQLite payload table because primary keys cannot be altered."""
    temporary = f"trajectory_payloads{TEMPORARY_SUFFIX}"
    _trajectory_table(temporary, with_runtime=with_runtime)
    if with_runtime:
        op.execute(
            sa.text(
                "INSERT INTO trajectory_payloads_runtime_v1 "
                "(runtime_key, root_session_id, agent_id, agent_kind, payload, agent_meta, "
                "content_hash, line_count, source_type, updated_at) "
                "SELECT :runtime_key, root_session_id, agent_id, agent_kind, payload, "
                "agent_meta, content_hash, line_count, source_type, updated_at "
                "FROM trajectory_payloads",
            ).bindparams(runtime_key=DEFAULT_RUNTIME_KEY),
        )
    else:
        op.execute(
            "INSERT INTO trajectory_payloads_runtime_v1 "
            "(root_session_id, agent_id, agent_kind, payload, agent_meta, content_hash, "
            "line_count, source_type, updated_at) "
            "SELECT root_session_id, agent_id, agent_kind, payload, agent_meta, "
            "content_hash, line_count, source_type, updated_at FROM trajectory_payloads",
        )
    op.drop_table("trajectory_payloads")
    op.rename_table(temporary, "trajectory_payloads")


def _rebuild_sqlite_source(*, with_runtime: bool) -> None:
    """Rebuild the SQLite processing index without touching referencing tables."""
    temporary = f"source_records{TEMPORARY_SUFFIX}"
    _source_table(temporary, with_runtime=with_runtime)
    if with_runtime:
        op.execute(
            sa.text(
                "INSERT INTO source_records_runtime_v1 "
                "(runtime_key, id, root_session_id, agent_id, kind, source_type, line_count, "
                "received_at, processed_at, processed_hash, parser_version, last_sync_run_id) "
                "SELECT :runtime_key, id, root_session_id, agent_id, kind, source_type, "
                "line_count, received_at, processed_at, processed_hash, parser_version, "
                "last_sync_run_id FROM source_records",
            ).bindparams(runtime_key=DEFAULT_RUNTIME_KEY),
        )
    else:
        op.execute(
            "INSERT INTO source_records_runtime_v1 "
            "(id, root_session_id, agent_id, kind, source_type, line_count, received_at, "
            "processed_at, processed_hash, parser_version, last_sync_run_id) "
            "SELECT id, root_session_id, agent_id, kind, source_type, line_count, "
            "received_at, processed_at, processed_hash, parser_version, last_sync_run_id "
            "FROM source_records",
        )
    op.drop_table("source_records")
    op.rename_table(temporary, "source_records")


def _create_source_indexes(
    *,
    with_runtime: bool,
    include_processed: bool = True,
) -> None:
    """Create the processing-index indexes for the active identity shape."""
    if include_processed:
        op.create_index("ix_source_records_processed_at", "source_records", ["processed_at"])
    columns = ["runtime_key", "parser_version"] if with_runtime else ["parser_version"]
    op.create_index(
        "ix_source_records_parser_version",
        "source_records",
        columns,
    )


def upgrade() -> None:
    """Introduce runtime identity while backfilling every legacy row to Claude."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        _rebuild_sqlite_trajectory(with_runtime=True)
        op.create_index(
            "ix_trajectory_payloads_updated_at",
            "trajectory_payloads",
            ["runtime_key", "updated_at"],
        )
        _rebuild_sqlite_source(with_runtime=True)
        _create_source_indexes(with_runtime=True)
    else:
        op.add_column(
            "trajectory_payloads",
            sa.Column(
                "runtime_key",
                sa.String(32),
                nullable=False,
                server_default=DEFAULT_RUNTIME_KEY,
            ),
        )
        op.drop_index("ix_trajectory_payloads_updated_at", table_name="trajectory_payloads")
        op.execute(
            "ALTER TABLE trajectory_payloads DROP PRIMARY KEY, "
            "ADD PRIMARY KEY (runtime_key, root_session_id, agent_id)",
        )
        op.create_index(
            "ix_trajectory_payloads_updated_at",
            "trajectory_payloads",
            ["runtime_key", "updated_at"],
        )
        op.add_column(
            "source_records",
            sa.Column(
                "runtime_key",
                sa.String(32),
                nullable=False,
                server_default=DEFAULT_RUNTIME_KEY,
            ),
        )
        op.drop_constraint("uq_source_records_root_agent", "source_records", type_="unique")
        op.create_unique_constraint(
            "uq_source_records_runtime_root_agent",
            "source_records",
            ["runtime_key", "root_session_id", "agent_id"],
        )
        op.drop_index("ix_source_records_parser_version", table_name="source_records")
        _create_source_indexes(with_runtime=True, include_processed=False)

    for table in ("session_families", "agents"):
        op.add_column(
            table,
            sa.Column(
                "runtime_key",
                sa.String(32),
                nullable=False,
                server_default=DEFAULT_RUNTIME_KEY,
            ),
        )


def downgrade() -> None:
    """Remove runtime identity and restore the Claude-only primary keys."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    op.drop_column("agents", "runtime_key")
    op.drop_column("session_families", "runtime_key")

    if dialect == "sqlite":
        op.drop_index("ix_source_records_parser_version", table_name="source_records")
        op.drop_index("ix_source_records_processed_at", table_name="source_records")
        _rebuild_sqlite_source(with_runtime=False)
        _create_source_indexes(with_runtime=False)
        op.drop_index("ix_trajectory_payloads_updated_at", table_name="trajectory_payloads")
        _rebuild_sqlite_trajectory(with_runtime=False)
        op.create_index(
            "ix_trajectory_payloads_updated_at",
            "trajectory_payloads",
            ["updated_at"],
        )
        return

    op.drop_constraint(
        "uq_source_records_runtime_root_agent",
        "source_records",
        type_="unique",
    )
    op.drop_index("ix_source_records_parser_version", table_name="source_records")
    op.create_unique_constraint(
        "uq_source_records_root_agent",
        "source_records",
        ["root_session_id", "agent_id"],
    )
    _create_source_indexes(with_runtime=False, include_processed=False)
    op.drop_column("source_records", "runtime_key")

    op.drop_index("ix_trajectory_payloads_updated_at", table_name="trajectory_payloads")
    op.execute(
        "ALTER TABLE trajectory_payloads DROP PRIMARY KEY, "
        "ADD PRIMARY KEY (root_session_id, agent_id)",
    )
    op.drop_column("trajectory_payloads", "runtime_key")
    op.create_index(
        "ix_trajectory_payloads_updated_at",
        "trajectory_payloads",
        ["updated_at"],
    )
