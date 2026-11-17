"""Read-path diagnostics for the externally owned problem tables."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from app.db.crud.attributions import AttributionRepository
from app.db.crud.bad_cases import BadCaseRepository
from app.db.crud.problems import ProblemRepository
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.external_contract import classify_external_read_error
from app.errors import AppError, ErrorCode
from tests.m12_02_support import (
    CASE_1,
    SESSION_1,
    FailingDatabase,
    as_database,
    generic_database_error,
    missing_column_error,
    permission_error,
)

LOG_NAME = "app.db.external_contract"
SCOPE = WorkspaceReadScope.all_workspaces()


def _failure_events(caplog: pytest.LogCaptureFixture) -> list[Any]:
    return [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "external.read_failed"
    ]


async def test_problem_read_maps_permission_denied_to_a_stable_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A SELECT-denied account yields 503 EXTERNAL_READ_FORBIDDEN, not a 500."""
    repository = ProblemRepository(as_database(FailingDatabase(permission_error())))
    with caplog.at_level(logging.ERROR, logger=LOG_NAME), pytest.raises(AppError) as captured:
        await repository.session_snapshot(SESSION_1, SCOPE)
    assert captured.value.code is ErrorCode.EXTERNAL_READ_FORBIDDEN
    assert captured.value.status_code == 503
    failures = _failure_events(caplog)
    assert failures and failures[-1].table == "bad_cases"
    assert failures[-1].db_code == 1142
    assert "SELECT" not in repr([record.__dict__ for record in caplog.records])


async def test_problem_read_maps_missing_column_to_schema_drift(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A dropped column is schema drift with its own stable code."""
    repository = ProblemRepository(as_database(FailingDatabase(missing_column_error())))
    with caplog.at_level(logging.ERROR, logger=LOG_NAME), pytest.raises(AppError) as captured:
        await repository.case_visible(CASE_1, SCOPE)
    assert captured.value.code is ErrorCode.EXTERNAL_SCHEMA_DRIFT
    assert captured.value.status_code == 503
    failures = _failure_events(caplog)
    assert failures and failures[-1].db_code == 1054


async def test_problem_read_maps_unknown_failures_to_read_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Neither permission nor drift signs stay a generic read failure."""
    repository = ProblemRepository(as_database(FailingDatabase(generic_database_error())))
    with caplog.at_level(logging.ERROR, logger=LOG_NAME), pytest.raises(AppError) as captured:
        await repository.probe_visible("probe-missing", SESSION_1, SCOPE)
    assert captured.value.code is ErrorCode.EXTERNAL_READ_FAILED
    assert captured.value.status_code == 503


async def test_bad_case_repository_and_attribution_reads_are_guarded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every public problem-side read shares the same external boundary."""
    bad_cases = BadCaseRepository(as_database(FailingDatabase(permission_error())))
    attributions = AttributionRepository(as_database(FailingDatabase(permission_error())))
    with caplog.at_level(logging.ERROR, logger=LOG_NAME):
        with pytest.raises(AppError) as case_error:
            await bad_cases.get_case(CASE_1)
        with pytest.raises(AppError) as count_error:
            await attributions.count_links(CASE_1)
    assert case_error.value.code is ErrorCode.EXTERNAL_READ_FORBIDDEN
    assert count_error.value.code is ErrorCode.EXTERNAL_READ_FORBIDDEN
    assert {failure.table for failure in _failure_events(caplog)} == {
        "bad_cases",
        "bad_case_analysis",
    }


async def test_analysis_progress_degrades_to_zero_when_tables_are_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The sync popover keeps working before the external tables exist."""
    repository = BadCaseRepository(as_database(FailingDatabase(missing_column_error())))
    with caplog.at_level(logging.WARNING, logger="app.db.crud.bad_cases"):
        progress = await repository.analysis_progress()
    assert progress.total == 0
    assert progress.pending == 0
    assert any("not provisioned" in record.getMessage() for record in caplog.records)


async def test_app_error_is_not_rewrapped() -> None:
    """Business errors from a read are never mislabelled as database drift."""
    expected = AppError(status_code=404, code=ErrorCode.NOT_FOUND, message="missing")

    class _RaisingDatabase:
        dialect = "sqlite"

        def session(self) -> Any:
            return _RaisingSession(expected)

    class _RaisingSession:
        def __init__(self, error: AppError) -> None:
            self._error = error

        async def __aenter__(self) -> Any:
            raise self._error

        async def __aexit__(self, *args: object) -> bool:
            return False

    repository = BadCaseRepository(as_database(_RaisingDatabase()))
    with pytest.raises(AppError) as captured:
        await repository.get_case(CASE_1)
    assert captured.value is expected


def test_classifier_recognizes_permission_and_drift_signatures() -> None:
    """The classifier exposes the same stable codes used by the API."""
    permission = classify_external_read_error(
        permission_error(),
        table="bad_cases",
        dialect="mysql",
    )
    drift = classify_external_read_error(
        missing_column_error(),
        table="bad_cases",
        dialect="mysql",
    )
    generic = classify_external_read_error(
        generic_database_error(),
        table="bad_cases",
        dialect="mysql",
    )
    assert isinstance(permission, AppError)
    assert permission.code is ErrorCode.EXTERNAL_READ_FORBIDDEN
    assert drift.code is ErrorCode.EXTERNAL_SCHEMA_DRIFT
    assert generic.code is ErrorCode.EXTERNAL_READ_FAILED


def test_classifier_treats_missing_table_as_schema_drift() -> None:
    """SQLite-style missing-table messages map to the same drift code."""
    error = OperationalError(
        "SELECT * FROM bad_cases",
        {},
        Exception("no such table: bad_cases"),
    )
    result = classify_external_read_error(error, table="bad_cases", dialect="sqlite")
    assert result.code is ErrorCode.EXTERNAL_SCHEMA_DRIFT
