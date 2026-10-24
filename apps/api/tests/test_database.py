"""Database lifecycle, migration, and cross-dialect repository contracts."""

import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.database import SqlAlchemyDatabase
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.mysql import MySqlDatabase
from app.db.sqlite import SqliteDatabase


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

        assert result.scalar_one() == "0001"
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
        assert result.scalar_one() == "0001"
    finally:
        await database.dispose()
