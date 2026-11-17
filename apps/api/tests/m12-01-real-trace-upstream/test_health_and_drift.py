"""Health and drift telemetry for the upstream trajectory client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, cast

import httpx
import pytest

from app.errors import AppError, ErrorCode
from app.third_party_api.trajectory.http import HttpTrajectorySource

ROOT = "00000000-0000-4000-8000-000000000301"
ROOT_2 = "00000000-0000-4000-8000-000000000302"
LOG_NAME = "app.third_party_api.trajectory.http"


def package_json(session_id: str = ROOT) -> dict[str, Any]:
    """Build one minimal package accepted by the runtime contract."""
    return {
        "sessionId": session_id,
        "metadata": {
            "project": "p",
            "model": "m",
            "startedAt": "2026-11-10T01:00:00+08:00",
            "endedAt": "2026-11-10T01:01:00+08:00",
            "problemFlag": True,
            "problemTags": [],
        },
        "transcripts": [{"kind": "main", "agentId": None, "lines": ["{}"]}],
    }


def response(
    status: int,
    body: object,
    *,
    version: str | None = "1.0",
) -> httpx.Response:
    headers = {"content-type": "application/json"}
    if version is not None:
        headers["X-Trajectory-Api-Version"] = version
    return httpx.Response(status, headers=headers, content=json.dumps(body).encode())


async def source_for(
    handler: Callable[[httpx.Request], Awaitable[httpx.Response]],
) -> tuple[HttpTrajectorySource, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(cast(Any, handler)),
        base_url="https://upstream.test",
        headers={"Authorization": "Bearer secret"},
        timeout=1,
    )

    async def sleep(_delay: float) -> None:
        await asyncio.sleep(0)

    return HttpTrajectorySource(client, max_retries=3, backoff_seconds=0.25, sleep=sleep), client


def event_records(caplog: pytest.LogCaptureFixture, event: str) -> list[Any]:
    """Return records carrying one stable event name."""
    return [record for record in caplog.records if getattr(record, "event", None) == event]


async def test_version_observation_and_drift_are_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The first response records the version; a later change is a drift warning."""
    versions = iter(("1.0", "1.1"))

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, package_json(), version=next(versions))

    source, client = await source_for(handler)
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        async with client:
            await source.fetch(ROOT)
            await source.fetch(ROOT)
    observed = event_records(caplog, "upstream.version_observed")
    drift = event_records(caplog, "upstream.version_drift")
    assert len(observed) == 1
    assert observed[0].api_version == "1.0"
    assert len(drift) == 1
    assert drift[0].reason == "version_changed"
    assert drift[0].previous_version == "1.0"
    assert drift[0].current_version == "1.1"


@pytest.mark.parametrize(
    ("version", "reason", "observed_major"),
    [(None, "missing", None), ("v1", "unparseable", None), ("2.0", "incompatible", 2)],
)
async def test_incompatible_versions_log_a_safe_drift_warning(
    caplog: pytest.LogCaptureFixture,
    version: str | None,
    reason: str,
    observed_major: int | None,
) -> None:
    """Log only bounded major numbers, never the raw upstream header."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, package_json(), version=version)

    source, client = await source_for(handler)
    with (
        caplog.at_level(logging.WARNING, logger=LOG_NAME),
        pytest.raises(AppError) as raised,
    ):
        async with client:
            await source.fetch(ROOT)
    assert raised.value.code is ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE
    drift = event_records(caplog, "upstream.version_drift")
    assert len(drift) == 1
    assert drift[0].reason == reason
    assert drift[0].expected_major == 1
    assert drift[0].observed_major == observed_major
    assert "v1" not in caplog.text


async def test_contract_drift_logs_only_the_model_and_error_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Schema drift is observable without echoing upstream payload text."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, {"sessionId": ROOT, "leaked": "must-not-leak"})

    source, client = await source_for(handler)
    with (
        caplog.at_level(logging.WARNING, logger=LOG_NAME),
        pytest.raises(AppError) as raised,
    ):
        async with client:
            await source.fetch(ROOT)
    assert raised.value.code is ErrorCode.UPSTREAM_INVALID_RESPONSE
    drift = event_records(caplog, "upstream.contract_drift")
    assert len(drift) == 1
    assert drift[0].model == "package"
    assert drift[0].reason == "schema_mismatch"
    assert drift[0].error_count >= 1
    assert "must-not-leak" not in caplog.text


async def test_retries_and_exhaustion_are_logged_without_response_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Transient failures are visible without logging the upstream body."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(503, {"error": "must-not-leak"})

    source, client = await source_for(handler)
    with (
        caplog.at_level(logging.INFO, logger=LOG_NAME),
        pytest.raises(AppError),
    ):
        async with client:
            await source.fetch(ROOT)
    retries = event_records(caplog, "upstream.request_retry")
    failures = event_records(caplog, "upstream.request_failed")
    assert len(retries) == 3
    assert [record.status_code for record in retries] == [503, 503, 503]
    assert len(failures) == 1
    assert failures[0].reason == "retry_exhausted"
    assert failures[0].status_code == 503
    assert failures[0].attempts == 4
    assert "must-not-leak" not in caplog.text


async def test_batch_health_reports_degraded_isolation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One isolated session keeps the batch completed but marks health degraded."""

    async def handler(request: httpx.Request) -> httpx.Response:
        session_id = request.url.path.rsplit("/", 1)[-1]
        if session_id == ROOT_2:
            return response(404, {"error": "missing"})
        return response(200, package_json(session_id))

    source, client = await source_for(handler)
    with caplog.at_level(logging.INFO, logger=LOG_NAME):
        async with client:
            result = await source.fetch_many([ROOT, ROOT_2])
    assert [package.session_id for package in result.packages] == [ROOT]
    health = event_records(caplog, "upstream.health")
    assert len(health) == 1
    assert health[0].status == "degraded"
    assert health[0].sessions_requested == 2
    assert health[0].sessions_fetched == 1
    assert health[0].sessions_isolated == 1
    assert ROOT not in caplog.text


async def test_window_request_failure_is_logged_as_a_request_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed enumeration records a bounded health event for operators."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(400, {"error": "must-not-leak"})

    source, client = await source_for(handler)
    with (
        caplog.at_level(logging.WARNING, logger=LOG_NAME),
        pytest.raises(AppError),
    ):
        async with client:
            await source.list_window(
                from_date=date(2026, 11, 1),
                to_date=date(2026, 11, 30),
                problem_only=True,
                cursor=None,
            )
    failures = event_records(caplog, "upstream.request_failed")
    assert len(failures) == 1
    assert failures[0].model == "window"
    assert failures[0].reason == "http_status"
    assert failures[0].status_code == 400
    assert "must-not-leak" not in caplog.text


async def test_mismatched_session_is_logged_as_contract_drift(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A package for another identity is observable as a drift event."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, package_json(ROOT_2))

    source, client = await source_for(handler)
    with (
        caplog.at_level(logging.WARNING, logger=LOG_NAME),
        pytest.raises(AppError) as raised,
    ):
        async with client:
            await source.fetch(ROOT)
    assert raised.value.code is ErrorCode.UPSTREAM_INVALID_RESPONSE
    drift = event_records(caplog, "upstream.contract_drift")
    assert len(drift) == 1
    assert drift[0].model == "package"
    assert drift[0].reason == "session_mismatch"
    assert ROOT not in caplog.text
