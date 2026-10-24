"""Database lifecycle, migration, and cross-dialect repository contracts."""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select, text
from sqlalchemy.pool import QueuePool

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.mysql import MySqlDatabase
from app.db.sqlite import SqliteDatabase


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


async def test_health_failure_is_sanitized(tmp_path: Path) -> None:
    """Connection failures become structured health rather than escaping."""
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
    assert health.error
    assert "password" not in health.error.lower()


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
    finally:
        await database.dispose()


async def test_empty_sqlite_database_upgrades_to_head_idempotently(tmp_path: Path) -> None:
    """The baseline migration reaches head and may be rerun safely."""
    settings = sqlite_settings(tmp_path)
    database = create_database(settings)

    await database.start()
    try:
        await upgrade_database(database, settings)
        await upgrade_database(database, settings)

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
        await upgrade_database(database, settings)
        await upgrade_database(database, settings)
        async with database.session() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
        assert result.scalar_one() == "0001"
    finally:
        await database.dispose()
