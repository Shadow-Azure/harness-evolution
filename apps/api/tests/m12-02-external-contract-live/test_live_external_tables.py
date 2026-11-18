"""Opt-in live check for real external problem tables.

CI must never reach production. This module skips unless
``HE_EXTERNAL_CONTRACT_LIVE=1`` is set together with a read-only database
target (``HE_EXTERNAL_DB_DIALECT`` + ``HE_EXTERNAL_DB_URL``, or the app's
``HE_DB_DIALECT`` + ``HE_DB_URL``). The check only reads metadata and rows.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.crud.problems import ProblemRepository
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.external_contract import inspect_external_contract
from app.db.factory import create_database
from app.db.models.domain import bad_cases
from app.errors import AppError, ErrorCode
from tests.m12_02_support import assert_read_only, record_statements

pytestmark = pytest.mark.live_external


def _env(name: str) -> str | None:
    """Return a trimmed optional environment value."""
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _target() -> tuple[str, str] | None:
    """Return the read-only dialect/URL pair or ``None`` when not configured."""
    if _env("HE_EXTERNAL_CONTRACT_LIVE") != "1":
        return None
    url = _env("HE_EXTERNAL_DB_URL") or _env("HE_DB_URL")
    dialect = _env("HE_EXTERNAL_DB_DIALECT") or _env("HE_DB_DIALECT") or "mysql"
    if not url:
        return None
    return dialect, url


async def test_live_external_tables_match_the_contract_and_are_read_only() -> None:
    """A real deployment's external tables are readable and need only SELECT."""
    target = _target()
    if target is None:
        pytest.skip(
            "set HE_EXTERNAL_CONTRACT_LIVE=1 with a read-only "
            "HE_EXTERNAL_DB_DIALECT/HE_EXTERNAL_DB_URL (or HE_DB_*) target",
        )
    dialect, url = target
    settings = Settings(
        db_dialect=DatabaseDialect(dialect),
        db_url=url,
        jwt_secret=SecretStr("m12-02-live-external-contract-secret"),
        data_dir=Path("."),
        db_pool_size=1,
        db_max_overflow=0,
    )
    database = create_database(settings)
    await database.start()
    try:
        with record_statements(database) as statements:
            report = await inspect_external_contract(database)
        assert report.status == "ok", report.drifts
        assert_read_only(statements)
        async with database.session() as session:
            row = (
                await session.execute(
                    select(bad_cases.c.bad_case_session_id).limit(1),
                )
            ).first()
        if row is None:
            pytest.skip("external bad_cases is empty; the schema check still passed")
        with record_statements(database) as read_statements:
            try:
                snapshot = await ProblemRepository(database).session_snapshot(
                    row[0],
                    WorkspaceReadScope.all_workspaces(),
                )
            except AppError as exc:
                if exc.code is ErrorCode.EXTERNAL_SCHEMA_DRIFT:
                    pytest.skip(
                        "target has the external tables but not the full app schema; "
                        "the contract check passed",
                    )
                raise
        assert_read_only(read_statements)
        if snapshot is not None:
            assert snapshot.session.id == row[0]
    finally:
        await database.dispose()
