"""Read-only contract monitoring for the externally owned problem tables.

The problem tables are provisioned outside this service. A deployment can point
the API at a database whose schema lags the contract in 06 §4, or grant only
SELECT on those tables. This module turns both cases into bounded, structured
diagnostics instead of an unclassified 500: a periodic contract check for
schema drift and a read guard that maps database failures to stable codes.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, ParamSpec, TypeVar, cast

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    DateTime,
    Double,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    inspect,
    text,
)
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Database
from app.errors import AppError, ErrorCode
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

ExternalContractStatus = Literal["ok", "degraded", "unavailable", "forbidden"]
DriftKind = Literal[
    "missing_table",
    "missing_column",
    "extra_column",
    "type_mismatch",
    "nullability_mismatch",
]

_P = ParamSpec("_P")
_R = TypeVar("_R")

_PERMISSION_DB_CODES = frozenset({1044, 1045, 1142, 1143, 1227})
_MISSING_DB_CODES = frozenset({1054, 1146})
_PERMISSION_MARKERS = (
    "access denied",
    "permission denied",
    "readonly database",
    "read-only database",
    "not authorized",
)
_MISSING_MARKERS = (
    "no such table",
    "no such column",
    "unknown column",
    "doesn't exist",
    "does not exist",
)


@dataclass(frozen=True, slots=True)
class ColumnContract:
    """One column the problem read path expects from an external table."""

    name: str
    family: str
    nullable: bool
    min_length: int | None = None


@dataclass(frozen=True, slots=True)
class TableContract:
    """One externally owned table and the columns this service reads."""

    name: str
    columns: tuple[ColumnContract, ...]


# Mirrors 06 §4 and the query model in ``app.db.models.domain``. Lengths are the
# minimum that can carry every value the read path accepts; broader columns are
# compatible, narrower ones can truncate and count as drift.
EXTERNAL_TABLES: tuple[TableContract, ...] = (
    TableContract(
        name="bad_cases",
        columns=(
            ColumnContract("bad_case_id", "varchar", False, 64),
            ColumnContract("workspace_id", "varchar", False, 36),
            ColumnContract("bad_case_session_id", "varchar", False, 36),
            ColumnContract("bad_case_type", "varchar", False, 16),
            ColumnContract("object_name", "varchar", False, 128),
            ColumnContract("object_type", "varchar", False, 16),
            ColumnContract("object_version", "varchar", True, 64),
            ColumnContract("bad_case_agent_id", "varchar", True, 64),
            ColumnContract("title", "varchar", False, 255),
            ColumnContract("bad_case_description", "text", False),
            ColumnContract("meta_data", "json", True),
            ColumnContract("source", "varchar", True, 64),
            ColumnContract("session_source", "json", True),
            ColumnContract("created_at", "datetime", False),
            ColumnContract("updated_at", "datetime", False),
        ),
    ),
    TableContract(
        name="bad_case_analysis",
        columns=(
            ColumnContract("id", "integer", False),
            ColumnContract("bad_case_id", "varchar", False, 64),
            ColumnContract("analysis_status", "varchar", True, 32),
            ColumnContract("probe_id", "varchar", True, 64),
            ColumnContract("analysis_result", "json", True),
            ColumnContract("updated_at", "datetime", False),
        ),
    ),
    TableContract(
        name="probe_reports",
        columns=(
            ColumnContract("probe_id", "varchar", False, 64),
            ColumnContract("workspace_id", "varchar", False, 36),
            ColumnContract("session_id", "varchar", False, 36),
            ColumnContract("probe_type", "varchar", False, 16),
            ColumnContract("probe_object", "varchar", False, 128),
            ColumnContract("object_version", "varchar", True, 96),
            ColumnContract("attribute_type", "varchar", True, 16),
            ColumnContract("conclusion", "varchar", False, 16),
            ColumnContract("confidence", "float", False),
            ColumnContract("probe_description", "text", False),
            ColumnContract("probe_analysis", "text", False),
            ColumnContract("policy_version", "varchar", False, 16),
            ColumnContract("attribution_engine", "varchar", False, 64),
            ColumnContract("cache_key", "char", True, 64),
            ColumnContract("created_run_id", "varchar", True, 36),
            ColumnContract("last_reused_run_id", "varchar", True, 36),
            ColumnContract("reused_count", "integer", False),
            ColumnContract("created_at", "datetime", False),
            ColumnContract("updated_at", "datetime", False),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ExternalContractDrift:
    """One bounded schema difference, containing names but no row data."""

    table: str
    kind: DriftKind
    field: str
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True, slots=True)
class ExternalContractReport:
    """Outcome of one read-only comparison against the external schema."""

    status: ExternalContractStatus
    checked_at: datetime
    drifts: tuple[ExternalContractDrift, ...]
    error_code: str | None = None

    @property
    def drift_count(self) -> int:
        """Return the number of recorded schema differences."""
        return len(self.drifts)


_TEXT_TYPE_NAMES = frozenset({"TEXT", "MEDIUMTEXT", "LONGTEXT"})
_INTEGER_TYPE_NAMES = frozenset(
    {"TINYINT", "SMALLINT", "MEDIUMINT", "INTEGER", "BIGINT"},
)
_FLOAT_TYPE_NAMES = frozenset({"FLOAT", "DOUBLE", "REAL", "DECIMAL", "NUMERIC"})
_CHAR_TYPE_NAMES = frozenset({"CHAR", "NCHAR"})
_VARCHAR_TYPE_NAMES = frozenset({"VARCHAR", "NVARCHAR", "STRING"})
_JSON_TYPE_NAMES = frozenset({"JSON"})
_DATETIME_TYPE_NAMES = frozenset({"DATETIME", "TIMESTAMP", "DATE"})


def _family(value: object) -> str:
    """Map a SQLAlchemy type instance to the contract's logical family.

    MySQL reflects ``MEDIUMTEXT`` / ``LONGTEXT`` as ``String`` subclasses rather
    than ``Text``; classify by the concrete type name first so a widened text
    column is not reported as varchar drift.
    """
    name = type(value).__name__.upper()
    if name in _TEXT_TYPE_NAMES:
        return "text"
    if name in _INTEGER_TYPE_NAMES:
        return "integer"
    if name in _FLOAT_TYPE_NAMES:
        return "float"
    if name in _CHAR_TYPE_NAMES:
        return "char"
    if name in _VARCHAR_TYPE_NAMES:
        return "varchar"
    if name in _JSON_TYPE_NAMES:
        return "json"
    if name in _DATETIME_TYPE_NAMES:
        return "datetime"
    if isinstance(value, JSON):
        return "json"
    if isinstance(value, CHAR):
        return "char"
    if isinstance(value, Text):
        return "text"
    if isinstance(value, String):
        return "varchar"
    if isinstance(value, DateTime):
        return "datetime"
    if isinstance(value, Boolean):
        return "boolean"
    if isinstance(value, (Float, Numeric, Double)):
        return "float"
    if isinstance(value, Integer):
        return "integer"
    return name.lower()


def _observed_type(type_: object) -> str:
    """Render the observed type without length details from the database."""
    family = _family(type_)
    length = getattr(type_, "length", None)
    return f"{family}({length})" if isinstance(length, int) else family


def _type_drift(
    expected: ColumnContract,
    observed_type: object,
) -> str | None:
    """Return a bounded observed type when the column cannot carry the contract."""
    family = _family(observed_type)
    if family != expected.family:
        return _observed_type(observed_type)
    length = getattr(observed_type, "length", None)
    if expected.min_length is not None and isinstance(length, int) and length < expected.min_length:
        return _observed_type(observed_type)
    return None


def _inspect_schema(sync_connection: Any) -> list[ExternalContractDrift]:
    """Compare every contract table to the live database in one sync callback."""
    inspector = inspect(sync_connection)
    drifts: list[ExternalContractDrift] = []
    for table in EXTERNAL_TABLES:
        if not inspector.has_table(table.name):
            # information_schema hides tables the account cannot read. Probe with
            # a zero-row SELECT so a missing privilege surfaces as forbidden
            # instead of a false "not provisioned" report.
            try:
                sync_connection.execute(
                    text(f"SELECT 1 FROM {table.name} LIMIT 0"),  # noqa: S608
                )
            except (OperationalError, ProgrammingError) as exc:
                if _classify_failure(exc) is ErrorCode.EXTERNAL_READ_FORBIDDEN:
                    raise
            drifts.append(
                ExternalContractDrift(
                    table=table.name,
                    kind="missing_table",
                    field="",
                ),
            )
            continue
        observed = {
            cast(str, column["name"]).lower(): column
            for column in inspector.get_columns(table.name)
        }
        observed_names = {
            cast(str, column["name"]).lower(): cast(str, column["name"])
            for column in inspector.get_columns(table.name)
        }
        expected_names: set[str] = set()
        for column in table.columns:
            expected_names.add(column.name.lower())
            current = observed.get(column.name.lower())
            if current is None:
                drifts.append(
                    ExternalContractDrift(
                        table=table.name,
                        kind="missing_column",
                        field=column.name,
                        expected=column.family,
                    ),
                )
                continue
            observed_type = current.get("type")
            mismatch = _type_drift(column, observed_type)
            if mismatch is not None:
                drifts.append(
                    ExternalContractDrift(
                        table=table.name,
                        kind="type_mismatch",
                        field=column.name,
                        expected=column.family,
                        observed=mismatch,
                    ),
                )
            if bool(current.get("nullable")) != column.nullable:
                drifts.append(
                    ExternalContractDrift(
                        table=table.name,
                        kind="nullability_mismatch",
                        field=column.name,
                        expected="nullable" if column.nullable else "not null",
                        observed="nullable" if current.get("nullable") else "not null",
                    ),
                )
        for name in sorted(set(observed) - expected_names):
            drifts.append(
                ExternalContractDrift(
                    table=table.name,
                    kind="extra_column",
                    field=observed_names.get(name, name),
                ),
            )
    return drifts


def _db_error_code(exc: BaseException) -> int | None:
    """Return the driver error code when the exception carries one."""
    original = getattr(exc, "orig", None)
    args = getattr(original, "args", None) or exc.args
    if args and isinstance(args[0], int):
        return args[0]
    return None


def _error_text(exc: BaseException) -> str:
    """Return only the driver message used for stable classification."""
    return str(getattr(exc, "orig", exc)).lower()


def _log_read_failure(
    exc: BaseException,
    *,
    table: str,
    dialect: str,
    code: ErrorCode,
) -> None:
    """Record one sanitized external read failure without SQL text or parameters."""
    logger.error(
        "external problem table read failed",
        extra={
            "event": "external.read_failed",
            "table": table,
            "dialect": dialect,
            "error_class": type(exc).__name__,
            "db_code": _db_error_code(exc),
            "code": code.value,
        },
    )


def _classify_failure(exc: BaseException) -> ErrorCode:
    """Return the stable code for one external-table database failure."""
    db_code = _db_error_code(exc)
    text = _error_text(exc)
    if (
        isinstance(exc, PermissionError)
        or db_code in _PERMISSION_DB_CODES
        or any(marker in text for marker in _PERMISSION_MARKERS)
    ):
        return ErrorCode.EXTERNAL_READ_FORBIDDEN
    if db_code in _MISSING_DB_CODES or any(marker in text for marker in _MISSING_MARKERS):
        return ErrorCode.EXTERNAL_SCHEMA_DRIFT
    return ErrorCode.EXTERNAL_READ_FAILED


_FAILURE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.EXTERNAL_READ_FORBIDDEN: ("database account cannot read the external problem tables"),
    ErrorCode.EXTERNAL_SCHEMA_DRIFT: "external problem table schema is missing or drifted",
    ErrorCode.EXTERNAL_READ_FAILED: "external problem tables could not be read",
}


def classify_external_failure(exc: BaseException) -> ErrorCode:
    """Return the stable code for one external-table database failure."""
    return _classify_failure(exc)


def classify_external_read_error(
    exc: BaseException,
    *,
    table: str,
    dialect: str,
) -> AppError:
    """Translate a database read failure into a stable, actionable AppError."""
    code = _classify_failure(exc)
    _log_read_failure(exc, table=table, dialect=dialect, code=code)
    return AppError(status_code=503, code=code, message=_FAILURE_MESSAGES[code])


def _mentions_external_table(exc: BaseException) -> bool:
    """Return whether a database error names one of the external tables.

    The driver message may omit the table (for example a missing column), so the
    failing statement is included for detection and never written to the log.
    """
    statement = str(getattr(exc, "statement", "") or "")
    text = f"{_error_text(exc)} {statement}".lower()
    return any(table.name in text for table in EXTERNAL_TABLES)


def read_only_guard(
    table: str,
    *,
    strict: bool = True,
) -> Callable[
    [Callable[_P, Coroutine[Any, Any, _R]]],
    Callable[_P, Coroutine[Any, Any, _R]],
]:
    """Decorate one read method with the external table error boundary.

    ``strict`` is for methods that only read the three external tables. Mixed
    reads (session tree plus problem rows) pass ``strict=False`` so a missing or
    mis-granted internal table is not mislabelled as external-table drift.
    """

    def decorate(
        operation: Callable[_P, Coroutine[Any, Any, _R]],
    ) -> Callable[_P, Coroutine[Any, Any, _R]]:
        @functools.wraps(operation)
        async def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return await operation(*args, **kwargs)
            except AppError:
                raise
            except (OperationalError, ProgrammingError, DBAPIError) as exc:
                if not strict and not (
                    isinstance(exc, TimeoutError) or _mentions_external_table(exc)
                ):
                    raise
                repository = args[0] if args else None
                database = getattr(repository, "_database", None)
                dialect = getattr(database, "dialect", "unknown")
                raise classify_external_read_error(
                    exc,
                    table=table,
                    dialect=dialect,
                ) from None
            except SQLAlchemyError as exc:
                if not strict and not (
                    isinstance(exc, TimeoutError) or _mentions_external_table(exc)
                ):
                    raise
                repository = args[0] if args else None
                database = getattr(repository, "_database", None)
                dialect = getattr(database, "dialect", "unknown")
                raise classify_external_read_error(
                    exc,
                    table=table,
                    dialect=dialect,
                ) from None

        return guarded

    return decorate


async def inspect_external_contract(
    database: Database,
    *,
    clock: Callable[[], datetime] = now_shanghai,
) -> ExternalContractReport:
    """Compare the live external schema with the published read contract."""
    try:
        engine: AsyncEngine = database.engine
        async with engine.connect() as connection:
            drifts = await connection.run_sync(_inspect_schema)
    except (OperationalError, ProgrammingError, DBAPIError) as exc:
        code = _classify_failure(exc)
        tables = ",".join(table.name for table in EXTERNAL_TABLES)
        _log_read_failure(exc, table=tables, dialect=database.dialect, code=code)
        return ExternalContractReport(
            status="forbidden" if code == ErrorCode.EXTERNAL_READ_FORBIDDEN else "unavailable",
            checked_at=clock(),
            drifts=(),
            error_code=code.value,
        )
    except SQLAlchemyError as exc:
        tables = ",".join(table.name for table in EXTERNAL_TABLES)
        _log_read_failure(
            exc,
            table=tables,
            dialect=database.dialect,
            code=ErrorCode.EXTERNAL_READ_FAILED,
        )
        return ExternalContractReport(
            status="unavailable",
            checked_at=clock(),
            drifts=(),
            error_code=ErrorCode.EXTERNAL_READ_FAILED.value,
        )
    observed_drifts = tuple(drifts)
    if any(
        drift.kind in {"missing_table", "missing_column", "type_mismatch"}
        for drift in observed_drifts
    ):
        status: ExternalContractStatus = "unavailable"
        error_code: str | None = ErrorCode.EXTERNAL_SCHEMA_DRIFT.value
    elif observed_drifts:
        status = "degraded"
        error_code = ErrorCode.EXTERNAL_SCHEMA_DRIFT.value
    else:
        status = "ok"
        error_code = None
    return ExternalContractReport(
        status=status,
        checked_at=clock(),
        drifts=observed_drifts,
        error_code=error_code,
    )


def _log_report(
    report: ExternalContractReport,
    *,
    dialect: str,
    duration_ms: float,
) -> None:
    """Emit one aggregate check record and bounded per-drift warnings."""
    missing_tables = [drift for drift in report.drifts if drift.kind == "missing_table"]
    only_missing_tables = bool(missing_tables) and len(missing_tables) == len(EXTERNAL_TABLES)
    extra = {
        "event": "external.contract_check",
        "status": report.status,
        "dialect": dialect,
        "tables_checked": len(EXTERNAL_TABLES),
        "drift_count": report.drift_count,
        "duration_ms": round(duration_ms, 3),
        "error_code": report.error_code,
    }
    if report.status == "ok":
        logger.info("external problem table contract check passed", extra=extra)
        return
    if report.status == "forbidden":
        logger.error("external problem tables are unreadable", extra=extra)
        return
    if report.status == "unavailable" and not report.drifts:
        logger.warning("external problem table contract check failed", extra=extra)
        return
    if only_missing_tables:
        logger.info(
            "external problem tables are not provisioned yet",
            extra=extra,
        )
        return
    logger.warning("external problem table contract drift detected", extra=extra)
    for drift in report.drifts:
        logger.warning(
            "external problem table contract drift",
            extra={
                "event": "external.contract_drift",
                "table": drift.table,
                "kind": drift.kind,
                "field": drift.field,
                "expected": drift.expected,
                "observed": drift.observed,
            },
        )


class ExternalContractMonitor:
    """Periodically check the external schema and keep the latest report."""

    def __init__(
        self,
        database: Database,
        *,
        interval_seconds: float = 300.0,
        clock: Callable[[], datetime] = now_shanghai,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind one database, one bounded interval, and one sleep seam."""
        self._database = database
        self._interval = max(30.0, interval_seconds)
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep or asyncio.sleep
        self._lock = asyncio.Lock()
        self._report: ExternalContractReport | None = None
        self._checked_at: float | None = None
        self._task: asyncio.Task[None] | None = None

    async def report(self) -> ExternalContractReport:
        """Return a fresh report, refreshing the cached one after the interval."""
        async with self._lock:
            if self._report is None or self._is_stale():
                self._report = await self._check()
                self._checked_at = self._monotonic()
            return self._report

    async def refresh(self) -> ExternalContractReport:
        """Run one check immediately and replace the cached report."""
        async with self._lock:
            self._report = await self._check()
            self._checked_at = self._monotonic()
            return self._report

    async def start(self) -> None:
        """Schedule the first check and the periodic loop without blocking startup."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(initial=True))

    async def stop(self) -> None:
        """Cancel the periodic loop without failing application shutdown."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _is_stale(self) -> bool:
        if self._checked_at is None:
            return True
        return self._monotonic() - self._checked_at >= self._interval

    async def _check(self) -> ExternalContractReport:
        started = self._monotonic()
        report = await inspect_external_contract(self._database, clock=self._clock)
        _log_report(
            report,
            dialect=self._database.dialect,
            duration_ms=(self._monotonic() - started) * 1000,
        )
        return report

    async def _loop(self, *, initial: bool = False) -> None:
        if initial:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Monitoring must never turn a failed check into a startup outage.
                logger.exception("external contract monitor startup check failed")
        while True:
            try:
                await self._sleep(self._interval)
                await self.report()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("external contract monitor iteration failed")
