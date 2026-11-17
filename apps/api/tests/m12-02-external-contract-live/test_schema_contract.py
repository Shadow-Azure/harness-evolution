"""Schema contract checks for the externally owned problem tables."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import String, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import DatabaseDialect, Settings
from app.db import external_contract as contract
from app.db.base import Database
from app.db.external_contract import (
    ColumnContract,
    ExternalContractMonitor,
    ExternalContractReport,
    ExternalContractStatus,
    inspect_external_contract,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import DOMAIN_METADATA
from app.logging import KeyValueFormatter
from tests.m12_02_support import FailingDatabase, as_database, permission_error

LOG_NAME = "app.db.external_contract"


async def _execute(database: Database, statement: str) -> None:
    async with database.engine.begin() as connection:
        await connection.execute(text(statement))


def _report(status: ExternalContractStatus = "ok") -> ExternalContractReport:
    return ExternalContractReport(
        status=status,
        checked_at=datetime(2026, 11, 17, 10, 0, tzinfo=UTC),
        drifts=(),
        error_code=None,
    )


def _events(caplog: pytest.LogCaptureFixture, event: str) -> list[Any]:
    return [record for record in caplog.records if getattr(record, "event", None) == event]


async def test_contract_accepts_provisioned_external_tables(
    external_database: Database,
) -> None:
    """A schema created from the published model matches the contract."""
    report = await inspect_external_contract(external_database)
    assert report.status == "ok"
    assert report.drifts == ()
    assert report.error_code is None


async def test_extra_column_is_degraded_and_logged(
    external_database: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Additive upstream drift stays readable but is recorded as degraded."""
    await _execute(external_database, "ALTER TABLE bad_cases ADD COLUMN upstream_note TEXT")
    monitor = ExternalContractMonitor(external_database, interval_seconds=30)
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        report = await monitor.refresh()
    assert report.status == "degraded"
    assert report.error_code == "EXTERNAL_SCHEMA_DRIFT"
    assert [(drift.kind, drift.field) for drift in report.drifts] == [
        ("extra_column", "upstream_note"),
    ]
    checks = _events(caplog, "external.contract_check")
    assert checks and checks[-1].status == "degraded"
    drift = _events(caplog, "external.contract_drift")
    assert drift and drift[-1].table == "bad_cases"
    assert drift[-1].field == "upstream_note"


async def test_missing_column_is_unavailable(
    external_database: Database,
) -> None:
    """A missing column that the read path selects blocks the whole table."""
    await _execute(external_database, "ALTER TABLE bad_cases DROP COLUMN source")
    report = await inspect_external_contract(external_database)
    assert report.status == "unavailable"
    assert ("missing_column", "source") in [(drift.kind, drift.field) for drift in report.drifts]


async def test_type_mismatch_is_unavailable(external_database: Database) -> None:
    """A narrowed or retyped column is reported with its observed family."""
    await _execute(
        external_database,
        "ALTER TABLE bad_cases RENAME COLUMN source TO source_legacy",
    )
    await _execute(external_database, "ALTER TABLE bad_cases ADD COLUMN source INTEGER")
    report = await inspect_external_contract(external_database)
    assert report.status == "unavailable"
    kinds = {(drift.kind, drift.field) for drift in report.drifts}
    assert ("type_mismatch", "source") in kinds
    assert ("extra_column", "source_legacy") in kinds


async def test_missing_table_is_unavailable(external_database: Database) -> None:
    """Dropping one external table is drift, not an unclassified failure."""
    await _execute(external_database, "DROP TABLE bad_case_analysis")
    report = await inspect_external_contract(external_database)
    assert report.status == "unavailable"
    assert ("missing_table", "") in [(drift.kind, drift.field) for drift in report.drifts]


@pytest_asyncio.fixture
async def unprovisioned_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide an empty database that never bootstrapped external tables."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("m12-02-external-contract-empty-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        yield database
    finally:
        await database.dispose()


async def test_unprovisioned_tables_are_logged_as_expected(
    unprovisioned_database: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A fresh database logs an informational status instead of an alert storm."""
    monitor = ExternalContractMonitor(unprovisioned_database, interval_seconds=30)
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        report = await monitor.refresh()
    assert report.status == "unavailable"
    assert all(drift.kind == "missing_table" for drift in report.drifts)
    checks = _events(caplog, "external.contract_check")
    assert checks and checks[-1].status == "unavailable"
    assert not _events(caplog, "external.contract_drift")


async def test_permission_failure_is_forbidden_and_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A read-only account without SELECT yields a stable forbidden report."""
    database = as_database(FailingDatabase(permission_error()))
    monitor = ExternalContractMonitor(database, interval_seconds=30)
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        report = await monitor.refresh()
    assert report.status == "forbidden"
    assert report.error_code == "EXTERNAL_READ_FORBIDDEN"
    failures = _events(caplog, "external.read_failed")
    assert failures and failures[-1].db_code == 1142
    rendered = repr([record.__dict__ for record in caplog.records])
    assert "SELECT command denied" not in rendered
    assert "SELECT * FROM bad_cases" not in rendered


async def test_monitor_caches_until_the_interval_elapses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated reads reuse one report until the configured interval passes."""
    calls = 0
    now = [0.0]

    async def fake_inspect(_database: Database, **_kwargs: object) -> ExternalContractReport:
        nonlocal calls
        calls += 1
        return _report()

    monkeypatch.setattr(contract, "inspect_external_contract", fake_inspect)
    monitor = ExternalContractMonitor(
        as_database(FailingDatabase(permission_error())),
        interval_seconds=30,
        monotonic=lambda: now[0],
    )
    await monitor.report()
    await monitor.report()
    assert calls == 1
    now[0] = 30.0
    await monitor.report()
    assert calls == 2
    await monitor.refresh()
    assert calls == 3


async def test_monitor_start_and_stop_cancel_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background loop runs and shuts down without leaking a task."""
    calls = 0

    async def fake_inspect(_database: Database, **_kwargs: object) -> ExternalContractReport:
        nonlocal calls
        calls += 1
        return _report()

    monkeypatch.setattr(contract, "inspect_external_contract", fake_inspect)
    monitor = ExternalContractMonitor(
        as_database(FailingDatabase(permission_error())),
        interval_seconds=30,
    )
    monitor._interval = 0.01
    await monitor.start()
    await asyncio.sleep(0.05)
    await monitor.stop()
    assert calls >= 2
    assert monitor._task is None


def test_contract_events_render_with_the_deployed_formatter() -> None:
    """Operators can grep one physical line for the structured event."""
    record = logging.LogRecord(LOG_NAME, logging.WARNING, __file__, 1, "drift", (), None)
    record.event = "external.contract_drift"
    record.table = "bad_cases"
    record.kind = "extra_column"
    record.field = "upstream_note"
    line = KeyValueFormatter("%(levelname)s %(message)s").format(record)
    assert "event='external.contract_drift'" in line
    assert "table='bad_cases'" in line
    assert "kind='extra_column'" in line
    assert "\n" not in line


def test_schema_can_be_recreated_from_the_published_model() -> None:
    """The contract tables are declared in one metadata for fixture bootstrap."""
    names = set(DOMAIN_METADATA.tables)
    assert {"bad_cases", "bad_case_analysis", "probe_reports"}.issubset(names)


async def test_inspection_survives_unexpected_sqlalchemy_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-DBAPI SQLAlchemy failure still yields a bounded report."""
    database = as_database(FailingDatabase(SQLAlchemyError("inspection exploded")))
    monitor = ExternalContractMonitor(database, interval_seconds=30)
    with caplog.at_level(logging.ERROR, logger=LOG_NAME):
        report = await monitor.refresh()
    assert report.status == "unavailable"
    assert report.error_code == "EXTERNAL_READ_FAILED"
    failures = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "external.read_failed"
    ]
    assert failures and cast(Any, failures[-1]).code == "EXTERNAL_READ_FAILED"


async def test_start_and_stop_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeated start keeps one task, and stop before start is a no-op."""
    calls = 0

    async def fake_inspect(_database: Database, **_kwargs: object) -> ExternalContractReport:
        nonlocal calls
        calls += 1
        return _report()

    monkeypatch.setattr(contract, "inspect_external_contract", fake_inspect)
    monitor = ExternalContractMonitor(
        as_database(FailingDatabase(permission_error())),
        interval_seconds=30,
    )
    await monitor.stop()
    assert monitor._task is None
    await monitor.start()
    task = monitor._task
    await monitor.start()
    assert monitor._task is task
    for _ in range(3):
        await asyncio.sleep(0)
    await monitor.stop()
    assert calls == 1


async def test_loop_recovers_after_one_failed_iteration(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A transient monitor failure is logged and the next tick continues."""
    calls = 0

    async def flaky_inspect(_database: Database, **_kwargs: object) -> ExternalContractReport:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("transient inspection failure")
        return _report()

    monkeypatch.setattr(contract, "inspect_external_contract", flaky_inspect)
    now = [0.0]

    def jumping_monotonic() -> float:
        now[0] += 31.0
        return now[0]

    async def fast_sleep(_delay: float) -> None:
        await asyncio.sleep(0)

    monitor = ExternalContractMonitor(
        as_database(FailingDatabase(permission_error())),
        interval_seconds=30,
        monotonic=jumping_monotonic,
        sleep=fast_sleep,
    )
    with caplog.at_level(logging.ERROR, logger=LOG_NAME):
        await monitor.start()
        for _ in range(8):
            await asyncio.sleep(0)
        await monitor.stop()
    assert calls >= 3
    assert any(
        "external contract monitor iteration failed" in record.getMessage()
        for record in caplog.records
    )


def test_type_drift_rejects_a_narrowed_column() -> None:
    """A shorter text column cannot carry every value the read path accepts."""
    expected = ColumnContract("bad_case_id", "varchar", False, 64)
    assert contract._type_drift(expected, String(64)) is None
    assert contract._type_drift(expected, String(8)) == "varchar(8)"


def test_type_family_accepts_mysql_text_and_case_insensitive_names() -> None:
    """MySQL reflection and case-insensitive DDL must not create false drift."""
    from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT, TINYTEXT

    assert contract._family(LONGTEXT()) == "text"
    assert contract._family(MEDIUMTEXT()) == "text"
    assert contract._family(TINYTEXT()) == "varchar"
    assert contract._family(String(64)) == "varchar"


async def test_case_insensitive_column_names_do_not_drift(
    external_database: Database,
) -> None:
    """SQLite/MySQL resolve identifiers case-insensitively; the checker follows."""
    await _execute(
        external_database,
        "ALTER TABLE bad_cases RENAME COLUMN source TO SOURCE",
    )
    report = await inspect_external_contract(external_database)
    assert report.status == "ok"
    assert report.drifts == ()


@pytest.mark.mysql
async def test_mysql_reflected_schema_matches_the_contract() -> None:
    """The real MySQL reflection types match 06 §4, including TEXT and CHAR."""
    url = os.environ.get("HE_DB_URL", "")
    if not url.startswith("mysql+asyncmy://"):
        pytest.skip("MySQL integration requires HE_DB_URL")
    settings = Settings(
        db_dialect=DatabaseDialect.MYSQL,
        db_url=url,
        jwt_secret=SecretStr("m12-02-mysql-contract-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        report = await inspect_external_contract(database)
        assert report.status == "ok", report.drifts
    finally:
        await database.dispose()
