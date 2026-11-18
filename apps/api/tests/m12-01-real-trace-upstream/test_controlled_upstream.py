"""Controlled real-HTTP upstream integration for the m12-01 slice."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select

from app.db.crud.local_sessions import write_local_payloads
from app.db.models.domain import session_families, trajectory_payloads
from app.main import create_app
from tests.m12_01_support import (
    ROOT,
    UPSTREAM_TOKEN,
    LocalUpstream,
    admin_headers,
    assert_logs_do_not_contain,
    main_payload,
    upstream_settings,
)

WINDOW: dict[str, str] = {"from": "2026-11-01", "to": "2026-11-30"}


def _records(caplog: Any, *, name: str, event: str) -> list[Any]:
    return [
        record
        for record in caplog.records
        if record.name == name and getattr(record, "event", None) == event
    ]


async def _count(app: Any, table: Any) -> int:
    async with app.state.database.session() as session:
        return int((await session.execute(select(func.count()).select_from(table))).scalar_one())


async def test_controlled_upstream_pull_uses_credentials_pagination_and_replay(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """Exercise the real HTTP client and lifecycle against a loopback upstream."""
    with LocalUpstream() as upstream:
        settings = upstream_settings(tmp_path, base_url=upstream.base_url)
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        caplog.set_level(logging.INFO, logger="app.service.acquisition.upstream_pull")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            response = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"window": WINDOW},
            )
            assert response.status_code == 202
            terminal = await app.state.jobs.wait(response.json()["jobId"])
            assert terminal.status == "completed"
            assert terminal.result is not None
            assert terminal.result["sessionsRequested"] == 2
            assert terminal.result["sessionsFetched"] == 2
            assert terminal.result["upstreamIssues"] == 0
            assert terminal.result["payloadsInserted"] == 2
            assert terminal.result["replayed"] == 2
            assert terminal.result["failed"] == 0
            assert await _count(app, trajectory_payloads) == 2
            assert await _count(app, session_families) == 2
        windows = upstream.window_requests()
        assert len(windows) == 2
        assert windows[0].query["problemOnly"] == ["true"]
        assert windows[1].query["cursor"] == ["1"]
        assert all(
            request.authorization == f"Bearer {UPSTREAM_TOKEN}" for request in upstream.requests
        )
        health = _records(
            caplog,
            name="app.service.acquisition.upstream_pull",
            event="upstream.health",
        )
        assert len(health) == 1
        assert health[0].status == "ok"
        assert health[0].sessions_requested == 2
        assert health[0].sessions_isolated == 0


async def test_manual_replay_recovers_a_failed_session(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """A failed session is recovered by an explicit administrator re-pull."""
    with LocalUpstream() as upstream:
        upstream.fail_sessions.add(ROOT)
        settings = upstream_settings(tmp_path, base_url=upstream.base_url)
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        caplog.set_level(logging.INFO, logger="app.service.acquisition.upstream_pull")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            first = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"sessionIds": [ROOT]},
            )
            failed = await app.state.jobs.wait(first.json()["jobId"])
            assert failed.status == "completed"
            assert failed.result is not None
            assert failed.result["upstreamIssues"] == 1
            assert await _count(app, trajectory_payloads) == 0

            upstream.fail_sessions.clear()
            second = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"sessionIds": [ROOT]},
            )
            replayed = await app.state.jobs.wait(second.json()["jobId"])
            assert replayed.status == "completed"
            assert replayed.result is not None
            assert replayed.result["upstreamIssues"] == 0
            assert replayed.result["payloadsInserted"] == 1
            assert replayed.result["replayed"] == 1
            assert await _count(app, trajectory_payloads) == 1
            assert await _count(app, session_families) == 1
        degraded = _records(
            caplog,
            name="app.service.acquisition.upstream_pull",
            event="upstream.health",
        )
        assert [record.status for record in degraded] == ["degraded", "ok"]


async def test_manual_sync_replays_stored_payload(tmp_path: Path) -> None:
    """The administrator sync trigger replays a stored payload on demand."""
    with LocalUpstream() as upstream:
        settings = upstream_settings(tmp_path, base_url=upstream.base_url)
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            await write_local_payloads(app.state.database, (main_payload(ROOT),))
            response = await client.post("/api/acquisition/sync", headers=headers)
            assert response.status_code == 202
            terminal = await app.state.jobs.wait(response.json()["jobId"])
            assert terminal.status == "completed"
            assert terminal.result is not None
            assert terminal.result["imported"] == 1
            assert terminal.result["failed"] == 0
            assert await _count(app, session_families) == 1


async def test_upstream_failure_does_not_block_the_payload_path(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """Acceptance: an unreachable upstream never blocks script payload replay."""
    with LocalUpstream(fail_window=True) as upstream:
        settings = upstream_settings(
            tmp_path,
            base_url=upstream.base_url,
            upstream_retry_attempts=0,
        )
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        caplog.set_level(logging.INFO, logger="app.service.acquisition.upstream_pull")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            await write_local_payloads(app.state.database, (main_payload(ROOT),))
            pull = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"window": WINDOW},
            )
            blocked = await app.state.jobs.wait(pull.json()["jobId"])
            assert blocked.status == "failed"
            sync = await client.post("/api/acquisition/sync", headers=headers)
            replayed = await app.state.jobs.wait(sync.json()["jobId"])
            assert replayed.status == "completed"
            assert replayed.result is not None
            assert replayed.result["imported"] == 1
            assert await _count(app, session_families) == 1
        failures = _records(
            caplog,
            name="app.service.acquisition.upstream_pull",
            event="upstream.health",
        )
        assert len(failures) == 1
        assert failures[0].status == "failed"
        assert failures[0].error_code == "UPSTREAM_REQUEST_FAILED"
        assert_logs_do_not_contain(caplog, ROOT)


MISSING = "00000000-0000-4000-8000-000000000299"


async def test_loopback_isolates_a_missing_session_over_http(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """A 404 for one session stays isolated and is logged at INFO."""
    with LocalUpstream() as upstream:
        settings = upstream_settings(tmp_path, base_url=upstream.base_url)
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        caplog.set_level(logging.INFO, logger="app.third_party_api.trajectory.http")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            response = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"sessionIds": [ROOT, MISSING]},
            )
            terminal = await app.state.jobs.wait(response.json()["jobId"])
            assert terminal.status == "completed"
            assert terminal.result is not None
            assert terminal.result["upstreamIssues"] == 1
            assert terminal.result["payloadsInserted"] == 1
            assert terminal.result["replayed"] == 1
            assert await _count(app, trajectory_payloads) == 1
            assert await _count(app, session_families) == 1
        isolated = [
            record
            for record in _records(
                caplog,
                name="app.third_party_api.trajectory.http",
                event="upstream.request_failed",
            )
            if record.status_code == 404
        ]
        assert len(isolated) == 1
        assert isolated[0].levelno == logging.INFO
        assert isolated[0].isolated is True
        health = _records(
            caplog,
            name="app.third_party_api.trajectory.http",
            event="upstream.health",
        )
        assert health[0].component == "client"
        assert health[0].status == "degraded"
        assert health[0].sessions_isolated == 1


async def test_repeated_pull_is_idempotent_over_http(tmp_path: Path) -> None:
    """A second manual pull of the same session has zero payload side effects."""
    with LocalUpstream() as upstream:
        settings = upstream_settings(tmp_path, base_url=upstream.base_url)
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            first = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"sessionIds": [ROOT]},
            )
            await app.state.jobs.wait(first.json()["jobId"])
            second = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"sessionIds": [ROOT]},
            )
            terminal = await app.state.jobs.wait(second.json()["jobId"])
            assert terminal.status == "completed"
            assert terminal.result is not None
            assert terminal.result["payloadsInserted"] == 0
            assert terminal.result["payloadsUpdated"] == 0
            assert terminal.result["payloadsUnchanged"] == 1
            assert await _count(app, trajectory_payloads) == 1
            assert await _count(app, session_families) == 1


async def test_window_fetch_version_failure_reports_requested_count(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """A fatal package version mismatch records the enumerated session count."""
    with LocalUpstream(package_api_version="2.0") as upstream:
        settings = upstream_settings(tmp_path, base_url=upstream.base_url)
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        caplog.set_level(logging.INFO, logger="app.service.acquisition.upstream_pull")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
        ):
            headers = await admin_headers(client)
            response = await client.post(
                "/api/acquisition/pull",
                headers=headers,
                json={"window": WINDOW},
            )
            failed = await app.state.jobs.wait(response.json()["jobId"])
            assert failed.status == "failed"
            assert await _count(app, trajectory_payloads) == 0
        health = _records(
            caplog,
            name="app.service.acquisition.upstream_pull",
            event="upstream.health",
        )
        assert len(health) == 1
        assert health[0].component == "pull"
        assert health[0].status == "failed"
        assert health[0].sessions_requested == 2
        assert health[0].error_code == "UPSTREAM_VERSION_INCOMPATIBLE"
