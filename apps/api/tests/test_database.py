"""Database lifecycle, migration, and cross-dialect repository contracts."""

import hashlib
import json
import logging
import os
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    insert,
    inspect,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.pool import QueuePool

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.database import SqlAlchemyDatabase
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    session_families,
    source_records,
    trajectory_payloads,
    user_turns,
)
from app.db.models.jobs import job_runs
from app.db.mysql import MySqlDatabase
from app.db.sqlite import SqliteDatabase
from app.service.acquisition.replay import replay_pending_payloads


class FailingHealthDatabase(SqlAlchemyDatabase):
    """Database double whose health check raises a synthetic driver error."""

    def __init__(self, error: str) -> None:
        """Keep the sensitive driver text available only to the raised exception."""
        super().__init__(dialect="mysql", url="mysql+asyncmy://redacted", echo=False)
        self._error = error

    @property
    def engine(self) -> AsyncEngine:
        """Raise the synthetic driver failure during the health probe."""
        raise RuntimeError(self._error)


def sqlite_settings(tmp_path: Path) -> Settings:
    """Build isolated SQLite settings for one test."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        db_pool_size=2,
        db_max_overflow=1,
    )


def normalized_server_default(column: Mapping[str, object]) -> str | None:
    """Normalize dialect-specific quoting around a reflected server default."""
    default = column["default"]
    if default is None:
        return None
    return str(default).strip().strip("'\"").lower()


def assert_true_server_default(column: Mapping[str, object]) -> None:
    """Assert one reflected column has a truthy boolean server default."""
    default = normalized_server_default(column)
    assert default is not None
    assert default in {"1", "true"}


async def reflected_event_schema(
    connection: AsyncConnection,
) -> tuple[set[str], set[str], set[tuple[str, ...]]]:
    """Inspect the shared event projection through a real dialect connection."""
    columns, indexes, uniques = await connection.run_sync(
        lambda sync_connection: (
            {
                column["name"]
                for column in inspect(sync_connection).get_columns("evolution_run_events")
            },
            {
                index["name"]
                for index in inspect(sync_connection).get_indexes("evolution_run_events")
                if index["name"] is not None
            },
            {
                tuple(constraint["column_names"])
                for constraint in inspect(sync_connection).get_unique_constraints(
                    "evolution_run_events",
                )
            },
        ),
    )
    return columns, indexes, uniques


async def job_recency_index_directions(
    database: Database,
) -> list[tuple[str, bool]]:
    """Return ordered column directions for the kind/recency index."""
    index_name = "ix_job_runs_kind_created_at"
    async with database.session() as session:
        if database.dialect == "sqlite":
            sqlite_rows = (
                await session.execute(text(f"PRAGMA index_xinfo('{index_name}')"))
            ).mappings()
            return [
                (str(row["name"]), bool(row["desc"]))
                for row in sqlite_rows
                if row["name"] is not None and row["key"]
            ]
        mysql_rows = (
            await session.execute(
                text(
                    "SELECT column_name, collation "
                    "FROM information_schema.statistics "
                    "WHERE table_schema = DATABASE() "
                    "AND table_name = 'job_runs' "
                    "AND index_name = :index_name "
                    "ORDER BY seq_in_index",
                ),
                {"index_name": index_name},
            )
        ).all()
        return [(str(row[0]), str(row[1]).upper() == "D") for row in mysql_rows]


@pytest.mark.parametrize(
    ("reflected", "expected"),
    [
        (1, "1"),
        ("'1'", "1"),
        ('"1"', "1"),
        ("true", "true"),
        (None, None),
    ],
)
def test_normalized_server_default_accepts_truthy_dialect_forms(
    reflected: object,
    expected: str | None,
) -> None:
    """SQLite and MySQL reflection may quote the same DEFAULT 1 constraint."""
    assert normalized_server_default({"default": reflected}) == expected


def test_settings_derive_database_urls(tmp_path: Path) -> None:
    """Each dialect has an explicit, credential-free default URL."""
    sqlite = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    mysql = Settings(db_dialect=DatabaseDialect.MYSQL)

    assert sqlite.effective_db_url == f"sqlite+aiosqlite:///{tmp_path / 'harness.db'}"
    assert mysql.effective_db_url.startswith("mysql+asyncmy://")
    assert "password" not in mysql.effective_db_url.lower()


def test_database_factory_selects_both_adapters(tmp_path: Path) -> None:
    """The factory is the only dialect selection point."""
    sqlite = create_database(sqlite_settings(tmp_path))
    mysql = create_database(Settings(db_dialect=DatabaseDialect.MYSQL))

    assert isinstance(sqlite, SqliteDatabase)
    assert isinstance(mysql, MySqlDatabase)


def test_job_index_declares_descending_recency() -> None:
    """The kind/recency index encodes newest-job ordering without table scans."""
    index = next(item for item in job_runs.indexes if item.name == "ix_job_runs_kind_created_at")

    assert [str(expression) for expression in index.expressions] == [
        "job_runs.kind",
        "job_runs.created_at DESC",
    ]


def test_sqlite_adapter_creates_the_default_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented ``./data`` default is usable before the first migration."""
    monkeypatch.chdir(tmp_path)
    settings = Settings(db_dialect=DatabaseDialect.SQLITE)

    SqliteDatabase(settings)

    assert (tmp_path / "data").is_dir()


async def test_sqlite_health_and_transaction_rollback(tmp_path: Path) -> None:
    """A rolled-back transaction leaves no residue and health reports the dialect."""
    database = SqliteDatabase(sqlite_settings(tmp_path))
    await database.start()
    metadata = MetaData()
    probe = Table(
        "transaction_probes",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(64), nullable=False),
    )
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

        with pytest.raises(RuntimeError, match="rollback"):
            async with database.transaction() as session:
                await session.execute(insert(probe).values(id=1, name="discard"))
                raise RuntimeError("rollback")

        async with database.session() as session:
            rows = (await session.execute(select(probe))).all()
        health = await database.health()

        assert rows == []
        assert health.ok is True
        assert health.dialect == "sqlite"
        assert health.latency_ms >= 0
    finally:
        await database.dispose()


async def test_sqlite_connection_applies_design_pragmas(tmp_path: Path) -> None:
    """The SQLite adapter applies the concurrency and integrity contract."""
    database = SqliteDatabase(sqlite_settings(tmp_path))
    await database.start()
    try:
        async with database.session() as session:
            pragmas: dict[str, object] = {
                "journal_mode": (await session.execute(text("PRAGMA journal_mode"))).scalar_one(),
                "foreign_keys": (await session.execute(text("PRAGMA foreign_keys"))).scalar_one(),
                "busy_timeout": (await session.execute(text("PRAGMA busy_timeout"))).scalar_one(),
                "synchronous": (await session.execute(text("PRAGMA synchronous"))).scalar_one(),
            }
    finally:
        await database.dispose()

    assert str(pragmas["journal_mode"]).lower() == "wal"
    assert pragmas["foreign_keys"] == 1
    assert pragmas["busy_timeout"] == 5000
    assert pragmas["synchronous"] == 1


def test_fixture_migration_is_frozen_from_mutable_model_metadata() -> None:
    """Historical 0004 must not execute whichever tables the current model holds."""
    migration = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0004_domain_fixtures.py"
    ).read_text(encoding="utf-8")

    assert "DOMAIN_METADATA" not in migration
    assert "op.create_table(" in migration


async def test_sqlite_health_failure_is_sanitized(tmp_path: Path) -> None:
    """Real connection failures expose only the stable unavailable summary."""
    database = SqliteDatabase(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'db.sqlite'}",
        )
    )
    await database.start()
    try:
        health = await database.health()
    finally:
        await database.dispose()

    assert health.ok is False
    assert health.dialect == "sqlite"
    assert health.error == "OperationalError: database is unavailable"


async def test_health_failure_logs_stable_diagnostics_without_driver_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Logs and public health both exclude sensitive driver details."""
    driver_error = (
        "mysql+asyncmy://ops:super-secret@db.internal:3306/private"
        "?charset=utf8mb4 failed at /var/lib/mysql/private"
    )
    database = FailingHealthDatabase(driver_error)

    with caplog.at_level(logging.ERROR, logger="app.db.database"):
        health = await database.health()

    assert health.ok is False
    assert health.error == "RuntimeError: database is unavailable"
    assert "super-secret" not in health.error
    assert "db.internal" not in health.error
    assert "/var/lib/mysql/private" not in health.error
    assert driver_error not in caplog.text
    assert "super-secret" not in caplog.text
    assert "db.internal" not in caplog.text
    assert "/var/lib/mysql/private" not in caplog.text
    record = next(record for record in caplog.records if record.name == "app.db.database")
    assert record.exc_info is None
    assert getattr(record, "error_type", None) == "RuntimeError"


async def test_mysql_engine_uses_the_designed_pool_configuration() -> None:
    """MySQL configuration is applied without requiring a local server."""
    settings = Settings(
        db_dialect=DatabaseDialect.MYSQL,
        db_pool_size=3,
        db_max_overflow=7,
    )
    database = MySqlDatabase(settings)
    await database.start()
    try:
        assert database.engine.dialect.name == "mysql"
        pool = database.engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == 3
        assert pool._max_overflow == 7
        assert pool._pre_ping is True
        assert pool._recycle == 1800
    finally:
        await database.dispose()


async def test_empty_sqlite_database_upgrades_to_head_idempotently(tmp_path: Path) -> None:
    """The baseline migration reaches head and may be rerun safely."""
    settings = sqlite_settings(tmp_path)
    database = create_database(settings)

    await database.start()
    try:
        await upgrade_database(database)
        await upgrade_database(database)

        async with database.session() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))

        assert result.scalar_one() == "0004"
        async with database.engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns("users")
            )

        assert {column["name"] for column in columns} == {
            "id",
            "username",
            "password_hash",
            "display_name",
            "role",
            "is_active",
            "must_change_password",
            "created_at",
            "updated_at",
            "last_login_at",
            "password_changed_at",
        }
        by_name = {column["name"]: column for column in columns}
        assert normalized_server_default(by_name["created_at"]) is None
        assert normalized_server_default(by_name["updated_at"]) is None
        assert_true_server_default(by_name["must_change_password"])
        async with database.engine.connect() as connection:
            job_columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns("job_runs")
            )
            job_indexes, job_foreign_keys = await connection.run_sync(
                lambda sync_connection: (
                    inspect(sync_connection).get_indexes("job_runs"),
                    inspect(sync_connection).get_foreign_keys("job_runs"),
                )
            )

        assert {column["name"] for column in job_columns} == {
            "id",
            "kind",
            "ref_id",
            "status",
            "progress",
            "executor",
            "external_job_id",
            "attempt",
            "payload",
            "result",
            "error",
            "created_by",
            "created_at",
            "started_at",
            "finished_at",
            "updated_at",
        }
        assert {
            "ix_job_runs_status",
            "ix_job_runs_kind_created_at",
            "ix_job_runs_ref_id",
        }.issubset({index["name"] for index in job_indexes if index["name"] is not None})
        assert {
            foreign_key["name"]
            for foreign_key in job_foreign_keys
            if foreign_key["name"] is not None
        } == {"fk_job_runs_created_by_users"}
        assert await job_recency_index_directions(database) == [
            ("kind", False),
            ("created_at", True),
        ]
        async with database.engine.connect() as connection:
            event_columns, event_indexes, event_uniques = await reflected_event_schema(connection)
        assert event_columns == {
            "id",
            "run_id",
            "seq",
            "event_type",
            "level",
            "stage",
            "step_index",
            "cluster_id",
            "evolution_round_id",
            "job_id",
            "message",
            "payload",
            "error_type",
            "error_message",
            "error_detail",
            "created_at",
        }
        assert {name for name in event_indexes if name.startswith("ix_evolution_run_events_")} == {
            "ix_evolution_run_events_run_created",
            "ix_evolution_run_events_event_type",
            "ix_evolution_run_events_level",
            "ix_evolution_run_events_cluster_id",
        }
        assert event_uniques == {("run_id", "seq")}
        async with database.engine.connect() as connection:
            table_names, payload_columns = await connection.run_sync(
                lambda sync_connection: (
                    set(inspect(sync_connection).get_table_names()),
                    {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "trajectory_payloads",
                        )
                    },
                )
            )
        assert {
            "trajectory_payloads",
            "source_records",
            "session_families",
            "agents",
            "agent_events",
            "user_turns",
            "bad_cases",
            "bad_case_analysis",
            "probe_reports",
            "evolution_targets",
        } <= table_names
        assert {
            "root_session_id",
            "agent_id",
            "payload",
            "content_hash",
            "line_count",
        } <= payload_columns
    finally:
        await database.dispose()


class RepositoryContract:
    """Same repository behavior executed against each configured dialect."""

    dialect = ""

    @pytest_asyncio.fixture
    async def database(self, request: pytest.FixtureRequest) -> AsyncIterator[Database]:
        """Provide the dialect selected by the concrete test class."""
        if self.dialect == "sqlite":
            tmp_path = request.getfixturevalue("tmp_path")
            database: Database = SqliteDatabase(sqlite_settings(tmp_path))
        else:
            url = os.environ.get("HE_DB_URL", "")
            if not url.startswith("mysql+asyncmy://"):
                if os.environ.get("HE_REQUIRE_MYSQL") == "1":
                    pytest.fail("HE_DB_URL must point to MySQL when HE_REQUIRE_MYSQL=1")
                pytest.skip("MySQL integration requires HE_DB_URL")
            database = MySqlDatabase(Settings(db_dialect=DatabaseDialect.MYSQL, db_url=url))
        await database.start()
        try:
            yield database
        finally:
            await database.dispose()

    async def test_repository_round_trip_and_rollback(
        self,
        database: Database,
    ) -> None:
        """SQLAlchemy expressions behave identically on both dialects."""
        metadata = MetaData()
        probe = Table(
            "repository_contract_probes",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(64), nullable=False),
        )
        async with database.engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
            await connection.run_sync(metadata.create_all)

        async with database.transaction() as session:
            await session.execute(insert(probe).values(id=1, name="commit"))
        with pytest.raises(RuntimeError, match="discard"):
            async with database.transaction() as session:
                await session.execute(insert(probe).values(id=2, name="discard"))
                raise RuntimeError("discard")

        async with database.session() as session:
            rows = (await session.execute(select(probe).order_by(probe.c.id))).all()
        assert [(row.id, row.name) for row in rows] == [(1, "commit")]
        assert (await database.health()).ok is True

        async with database.engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)


class TestSqliteRepository(RepositoryContract):
    """Run the repository contract against SQLite."""

    dialect = "sqlite"


@pytest.mark.mysql
class TestMySqlRepository(RepositoryContract):
    """Run the same repository contract against a MySQL service."""

    dialect = "mysql"

    async def test_mysql_session_uses_shanghai_time_zone(
        self,
        database: Database,
    ) -> None:
        """Every pooled MySQL connection starts with the Shanghai session zone."""
        async with database.session() as session:
            time_zone: object = (
                await session.execute(text("SELECT @@session.time_zone"))
            ).scalar_one()

        assert time_zone == "+08:00"


@pytest.mark.mysql
async def test_empty_mysql_database_upgrades_to_head_idempotently() -> None:
    """The empty baseline also converges on a real MySQL 8 server."""
    url = os.environ.get("HE_DB_URL", "")
    if not url.startswith("mysql+asyncmy://"):
        if os.environ.get("HE_REQUIRE_MYSQL") == "1":
            pytest.fail("HE_DB_URL must point to MySQL when HE_REQUIRE_MYSQL=1")
        pytest.skip("MySQL integration requires HE_DB_URL")
    settings = Settings(db_dialect=DatabaseDialect.MYSQL, db_url=url)
    database = MySqlDatabase(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await upgrade_database(database)
        async with database.session() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
        assert result.scalar_one() == "0004"
        async with database.engine.connect() as connection:
            mysql_columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns("users")
            )

        assert {column["name"] for column in mysql_columns} == {
            "id",
            "username",
            "password_hash",
            "display_name",
            "role",
            "is_active",
            "must_change_password",
            "created_at",
            "updated_at",
            "last_login_at",
            "password_changed_at",
        }
        by_name = {column["name"]: column for column in mysql_columns}
        assert normalized_server_default(by_name["created_at"]) is None
        assert normalized_server_default(by_name["updated_at"]) is None
        assert_true_server_default(by_name["must_change_password"])
        async with database.engine.connect() as connection:
            job_columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns("job_runs")
            )
            job_indexes, job_foreign_keys = await connection.run_sync(
                lambda sync_connection: (
                    inspect(sync_connection).get_indexes("job_runs"),
                    inspect(sync_connection).get_foreign_keys("job_runs"),
                )
            )

        assert {column["name"] for column in job_columns} == {
            "id",
            "kind",
            "ref_id",
            "status",
            "progress",
            "executor",
            "external_job_id",
            "attempt",
            "payload",
            "result",
            "error",
            "created_by",
            "created_at",
            "started_at",
            "finished_at",
            "updated_at",
        }
        assert {
            "ix_job_runs_status",
            "ix_job_runs_kind_created_at",
            "ix_job_runs_ref_id",
        }.issubset({index["name"] for index in job_indexes if index["name"] is not None})
        assert {
            foreign_key["name"]
            for foreign_key in job_foreign_keys
            if foreign_key["name"] is not None
        } == {"fk_job_runs_created_by_users"}
        assert await job_recency_index_directions(database) == [
            ("kind", False),
            ("created_at", True),
        ]
        async with database.engine.connect() as connection:
            event_columns, event_indexes, event_uniques = await reflected_event_schema(connection)
        assert event_columns == {
            "id",
            "run_id",
            "seq",
            "event_type",
            "level",
            "stage",
            "step_index",
            "cluster_id",
            "evolution_round_id",
            "job_id",
            "message",
            "payload",
            "error_type",
            "error_message",
            "error_detail",
            "created_at",
        }
        assert {name for name in event_indexes if name.startswith("ix_evolution_run_events_")} == {
            "ix_evolution_run_events_run_created",
            "ix_evolution_run_events_event_type",
            "ix_evolution_run_events_level",
            "ix_evolution_run_events_cluster_id",
        }
        assert event_uniques == {("run_id", "seq")}
        async with database.engine.connect() as connection:
            table_names, payload_columns = await connection.run_sync(
                lambda sync_connection: (
                    set(inspect(sync_connection).get_table_names()),
                    {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "trajectory_payloads",
                        )
                    },
                )
            )
        assert {
            "trajectory_payloads",
            "source_records",
            "session_families",
            "agents",
            "agent_events",
            "user_turns",
            "bad_cases",
            "bad_case_analysis",
            "probe_reports",
            "evolution_targets",
        } <= table_names
        assert {"root_session_id", "agent_id", "content_hash", "line_count"} <= payload_columns
    finally:
        await database.dispose()


@pytest.mark.mysql
async def test_mysql_replay_round_trip_is_idempotent() -> None:
    """The root-atomic replay repository works against the real MySQL lane."""
    url = os.environ.get("HE_DB_URL", "")
    if not url.startswith("mysql+asyncmy://"):
        if os.environ.get("HE_REQUIRE_MYSQL") == "1":
            pytest.fail("HE_DB_URL must point to MySQL when HE_REQUIRE_MYSQL=1")
        pytest.skip("HE_DB_URL is not configured for MySQL")
    root_id = "55555555-5555-4555-8555-555555555555"
    child_id = "mysql-child-agent"
    database = create_database(
        Settings(db_dialect=DatabaseDialect.MYSQL, db_url=url),
    )
    await database.start()
    try:
        await upgrade_database(database)
        async with database.transaction() as session:
            child_ids = cast(
                list[str],
                (
                    await session.execute(
                        text("SELECT id FROM agents WHERE root_session_id = :root"),
                        {"root": root_id},
                    )
                )
                .scalars()
                .all(),
            )
            if child_ids:
                await session.execute(
                    delete(agent_events).where(agent_events.c.agent_id.in_(child_ids)),
                )
            await session.execute(
                text("DELETE FROM agents WHERE root_session_id = :root"),
                {"root": root_id},
            )
            await session.execute(
                text("DELETE FROM user_turns WHERE root_session_id = :root"),
                {"root": root_id},
            )
            await session.execute(
                text("DELETE FROM session_families WHERE id = :root"),
                {"root": root_id},
            )
            await session.execute(
                text("DELETE FROM source_records WHERE root_session_id = :root"),
                {"root": root_id},
            )
            await session.execute(
                text("DELETE FROM trajectory_payloads WHERE root_session_id = :root"),
                {"root": root_id},
            )

            main_content = (
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": root_id,
                        "timestamp": "2026-10-20T01:00:00Z",
                        "message": {"content": "mysql replay prompt"},
                    },
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": root_id,
                        "timestamp": "2026-10-20T01:01:00Z",
                        "message": {
                            "id": "mysql-main-message",
                            "model": "mysql-model",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "mysql-tool",
                                    "name": "Agent",
                                    "input": {"subagent_type": "Explore"},
                                },
                            ],
                            "usage": {"input_tokens": 3, "output_tokens": 2},
                        },
                    },
                )
                + "\n"
            )
            child_content = (
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": root_id,
                        "timestamp": "2026-10-20T01:02:00Z",
                        "message": {
                            "id": "mysql-child-message",
                            "model": "mysql-model",
                            "content": [{"type": "text", "text": "child"}],
                            "usage": {"input_tokens": 2, "output_tokens": 1},
                        },
                    },
                )
                + "\n"
            )
            for agent_id, kind, content, meta in (
                (root_id, "main", main_content, None),
                (child_id, "subagent", child_content, {"toolUseId": "mysql-tool"}),
            ):
                await session.execute(
                    trajectory_payloads.insert().values(
                        root_session_id=root_id,
                        agent_id=agent_id,
                        agent_kind=kind,
                        payload=content,
                        agent_meta=meta,
                        content_hash=hashlib.sha256(content.encode()).hexdigest(),
                        line_count=content.count("\n"),
                        source_type="script",
                        updated_at=datetime(2026, 10, 20, 1, tzinfo=UTC),
                    ),
                )

        first = await replay_pending_payloads(database)
        second = await replay_pending_payloads(database)

        expanded_child = child_content + (
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": root_id,
                    "timestamp": "2026-10-20T01:03:00Z",
                    "message": {
                        "id": "mysql-child-message-2",
                        "model": "mysql-model",
                        "content": [{"type": "text", "text": "second child chunk"}],
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                },
            )
            + "\n"
        )
        async with database.transaction() as session:
            await session.execute(
                trajectory_payloads.update()
                .where(
                    trajectory_payloads.c.root_session_id == root_id,
                    trajectory_payloads.c.agent_id == child_id,
                )
                .values(
                    payload=expanded_child,
                    content_hash=hashlib.sha256(expanded_child.encode()).hexdigest(),
                    line_count=expanded_child.count("\n"),
                ),
            )
        changed = await replay_pending_payloads(database)

        async with database.session() as session:
            counts = {
                "families": len(
                    (await session.execute(select(session_families.c.id))).all(),
                ),
                "agents": len((await session.execute(select(agents.c.id))).all()),
                "events": len((await session.execute(select(agent_events.c.id))).all()),
                "turns": len((await session.execute(select(user_turns.c.id))).all()),
                "sources": len(
                    (await session.execute(select(source_records.c.id))).all(),
                ),
            }
            child_source = (
                (
                    await session.execute(
                        select(source_records).where(source_records.c.agent_id == child_id),
                    )
                )
                .mappings()
                .one()
            )
        assert first.imported == 2
        assert second.imported == 0
        assert second.skipped == 2
        assert changed.imported == 1
        assert child_source["line_count"] == 2
        assert counts["families"] == 1
        assert counts["agents"] == 2
        assert counts["events"] == 1
        assert counts["turns"] == 1
        assert counts["sources"] == 2
    finally:
        await database.dispose()
