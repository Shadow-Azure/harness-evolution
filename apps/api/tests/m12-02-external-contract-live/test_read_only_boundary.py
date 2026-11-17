"""Read-only boundary and row-level degradation for the problem tables."""

from __future__ import annotations

import logging
from typing import Any, cast

import pytest
from sqlalchemy import update

from app.db.models.domain import bad_cases
from tests.m12_02_support import (
    CASE_1,
    PROBE_1,
    SESSION_1,
    assert_read_only,
    record_statements,
)

PROBLEM_LOG_NAME = "app.service.bad_cases.service"


async def test_problem_reads_issue_only_selects(seeded_environment: Any) -> None:
    """Every public problem read is a SELECT; no path repairs external rows."""
    environment = seeded_environment
    paths = [
        f"/api/sessions/{SESSION_1}/bad-cases",
        f"/api/bad-cases/{CASE_1}",
        f"/api/sessions/{SESSION_1}/probes",
        f"/api/probes/{PROBE_1}",
        f"/api/bad-cases/{CASE_1}/analysis",
        f"/api/workspaces/{environment.workspace_id}/bad-cases/{CASE_1}/attributions",
        f"/api/workspaces/{environment.workspace_id}/bad-cases/{CASE_1}/attributions/{PROBE_1}",
        "/api/acquisition/status",
    ]
    with record_statements(environment.database) as statements:
        for path in paths:
            response = await environment.client.get(
                path,
                headers=environment.authorization,
            )
            assert response.status_code == 200, (path, response.text)
    assert_read_only(statements)
    assert any("bad_cases" in statement for statement in statements)


async def test_contract_monitor_issues_only_reads(seeded_environment: Any) -> None:
    """The periodic schema check reads metadata, never the external rows."""
    environment = seeded_environment
    monitor = environment.app.state.external_contract
    with record_statements(environment.database) as statements:
        report = await monitor.refresh()
    assert report.status == "ok"
    assert_read_only(statements)


async def test_row_drift_degrades_the_public_card_and_is_logged(
    seeded_environment: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid external fields keep the card visible with a degraded marker."""
    environment = seeded_environment
    async with environment.database.transaction() as session:
        await session.execute(
            update(bad_cases)
            .where(bad_cases.c.bad_case_id == CASE_1)
            .values(bad_case_type="drifted", meta_data=[1, 2]),
        )
    with caplog.at_level(logging.WARNING, logger=PROBLEM_LOG_NAME):
        response = await environment.client.get(
            f"/api/sessions/{SESSION_1}/bad-cases",
            headers=environment.authorization,
        )
    assert response.status_code == 200
    items = {item["badCaseId"]: item for item in response.json()["items"]}
    degraded = items[CASE_1]
    assert degraded["degraded"] is True
    assert degraded["diagnosticCode"] == "EXTERNAL_FIELD_INVALID"
    summary = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "external.row_drift"
    ]
    assert summary
    drift = cast(Any, summary[-1])
    assert drift.warning_count >= 2
    assert "EXTERNAL_FIELD_INVALID" in drift.codes


async def test_status_popover_degrades_when_external_tables_are_missing(
    seeded_environment: Any,
) -> None:
    """A missing external table never turns the data-sync popover into a 500."""
    environment = seeded_environment
    async with environment.database.engine.begin() as connection:
        await connection.exec_driver_sql("DROP TABLE bad_case_analysis")
    response = await environment.client.get(
        "/api/acquisition/status",
        headers=environment.authorization,
    )
    assert response.status_code == 200
    assert response.json()["badCaseAnalysis"]["total"] == 0
