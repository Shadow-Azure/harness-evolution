"""Administrator pull API boundary and no-write guarantees."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import func, select

from app.config import DatabaseDialect, Settings
from app.db.models.domain import source_records, sync_runs, trajectory_payloads
from app.errors import AppError, ErrorCode
from app.main import create_app
from app.third_party_api.trajectory.models import (
    FetchManyResult,
    TrajectoryPackage,
    TrajectoryWindowItem,
    UpstreamItemIssue,
)

ROOT = "00000000-0000-4000-8000-000000000011"


@dataclass
class FakeSource:
    """Deterministic in-process source used to exercise the queued pull handler."""

    package: TrajectoryPackage
    issues: tuple[UpstreamItemIssue, ...] = ()

    async def fetch(self, session_id: str) -> TrajectoryPackage:
        assert session_id == self.package.session_id
        return self.package

    async def list_window(
        self,
        *,
        from_date: date,
        to_date: date,
        problem_only: bool,
        cursor: str | None,
    ) -> tuple[TrajectoryWindowItem, ...]:
        return (
            TrajectoryWindowItem.model_validate(
                {
                    "sessionId": self.package.session_id,
                    "startedAt": "2026-10-20T01:00:00+08:00",
                    "model": "fixture-model",
                    "problemFlag": True,
                },
            ),
        )

    async def fetch_many(self, session_ids: list[str]) -> FetchManyResult:
        assert session_ids == [self.package.session_id]
        return FetchManyResult(packages=(self.package,), issues=self.issues)

    async def close(self) -> None:
        return None


class IssueOnlySource(FakeSource):
    """Return one version issue and no packages."""

    async def fetch_many(self, session_ids: list[str]) -> FetchManyResult:
        assert session_ids == [self.package.session_id]
        return FetchManyResult(packages=(), issues=self.issues)


class VersionFatalSource(FakeSource):
    """Raise a protocol-wide failure instead of a per-session issue."""

    async def fetch_many(self, session_ids: list[str]) -> FetchManyResult:
        assert session_ids == [self.package.session_id]
        raise AppError(
            status_code=502,
            code=ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE,
            message="upstream trajectory API version is incompatible",
        )


def upstream_package() -> TrajectoryPackage:
    lines = [
        json.dumps(
            {
                "type": "user",
                "sessionId": ROOT,
                "timestamp": "2026-10-20T01:00:00+08:00",
                "message": {"content": "upstream prompt"},
            },
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": ROOT,
                "timestamp": "2026-10-20T01:01:00+08:00",
                "message": {
                    "id": "upstream-message",
                    "model": "fixture-model",
                    "content": [{"type": "text", "text": "upstream reply"}],
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                },
            },
        ),
    ]
    return TrajectoryPackage.model_validate(
        {
            "sessionId": ROOT,
            "metadata": {
                "project": "fixture-project",
                "model": "fixture-model",
                "startedAt": "2026-10-20T01:00:00+08:00",
                "endedAt": "2026-10-20T01:01:00+08:00",
                "problemFlag": True,
                "problemTags": [],
            },
            "transcripts": [{"kind": "main", "agentId": None, "lines": lines}],
        },
    )


@pytest_asyncio.fixture
async def pull_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("upstream-contract-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client


async def admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "initial-password"},
    )
    initial = login.json()["accessToken"]
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {initial}"},
        json={
            "oldPassword": "initial-password",
            "newPassword": "replacement-password",
        },
    )
    assert changed.status_code == 204
    authenticated = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "replacement-password"},
    )
    return {"Authorization": f"Bearer {authenticated.json()['accessToken']}"}


async def member_headers(client: httpx.AsyncClient, admin: dict[str, str]) -> dict[str, str]:
    created = await client.post(
        "/api/users",
        headers=admin,
        json={
            "username": "member",
            "displayName": "Member",
            "password": "temporary-password",
            "role": "member",
        },
    )
    assert created.status_code == 201
    login = await client.post(
        "/api/auth/login",
        json={"username": "member", "password": "temporary-password"},
    )
    initial = login.json()["accessToken"]
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {initial}"},
        json={
            "oldPassword": "temporary-password",
            "newPassword": "member-password",
        },
    )
    assert changed.status_code == 204
    authenticated = await client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member-password"},
    )
    return {"Authorization": f"Bearer {authenticated.json()['accessToken']}"}


async def test_pull_requires_exact_one_selector_and_admin(pull_client: httpx.AsyncClient) -> None:
    headers = await admin_headers(pull_client)
    empty = await pull_client.post("/api/acquisition/pull", headers=headers, json={})
    both = await pull_client.post(
        "/api/acquisition/pull",
        headers=headers,
        json={
            "sessionIds": ["00000000-0000-4000-8000-000000000001"],
            "window": {"from": "2026-10-01", "to": "2026-10-31"},
        },
    )
    assert empty.status_code == 422
    assert both.status_code == 422
    assert empty.json()["error"]["code"] == "VALIDATION_INVALID"
    assert both.json()["error"]["code"] == "VALIDATION_INVALID"


async def test_pull_unavailable_returns_stable_conflict(pull_client: httpx.AsyncClient) -> None:
    headers = await admin_headers(pull_client)
    response = await pull_client.post(
        "/api/acquisition/pull",
        headers=headers,
        json={"sessionIds": ["00000000-0000-4000-8000-000000000001"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "UPSTREAM_NOT_AVAILABLE"


async def test_pull_requires_authentication(pull_client: httpx.AsyncClient) -> None:
    response = await pull_client.post(
        "/api/acquisition/pull",
        json={"sessionIds": [ROOT]},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_pull_rejects_member_role(pull_client: httpx.AsyncClient) -> None:
    admin = await admin_headers(pull_client)
    member = await member_headers(pull_client, admin)
    response = await pull_client.post(
        "/api/acquisition/pull",
        headers=member,
        json={"sessionIds": [ROOT]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_pull_upserts_upstream_payload_and_replays(tmp_path: Path) -> None:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("upstream-contract-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    source = FakeSource(package=upstream_package())
    app = create_app(settings, trajectory_source=source)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await admin_headers(client)
        response = await client.post(
            "/api/acquisition/pull",
            headers=headers,
            json={"sessionIds": [ROOT]},
        )
        assert response.status_code == 202
        job_id = response.json()["jobId"]
        terminal = await app.state.jobs.wait(job_id)
        assert terminal.status == "completed"

        async with app.state.database.session() as session:
            payload_count = int(
                (
                    await session.execute(
                        select(func.count()).select_from(trajectory_payloads),
                    )
                ).scalar_one(),
            )
            payload_rows = (await session.execute(select(trajectory_payloads))).mappings().all()
            source_rows = (await session.execute(select(source_records))).mappings().all()
            sync_source_type = (
                await session.execute(
                    select(sync_runs.c.source_type).where(sync_runs.c.id == terminal.id),
                )
            ).scalar_one()
        assert payload_count == 1
        assert payload_rows[0]["source_type"] == "http_api"
        assert len(source_rows) == 1
        assert source_rows[0]["source_type"] == "http_api"
        assert source_rows[0]["processed_at"] is not None
        assert sync_source_type == "http_api"


async def test_admin_window_pull_uses_enumeration(tmp_path: Path) -> None:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("upstream-contract-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    source = FakeSource(package=upstream_package())
    app = create_app(settings, trajectory_source=source)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await admin_headers(client)
        response = await client.post(
            "/api/acquisition/pull",
            headers=headers,
            json={
                "window": {
                    "from": "2026-10-01",
                    "to": "2026-10-31",
                    "problemOnly": True,
                },
            },
        )
        terminal = await app.state.jobs.wait(response.json()["jobId"])
        assert terminal.status == "completed"
        assert terminal.result is not None
        assert terminal.result["sessionsRequested"] == 1


async def test_upstream_item_issue_is_isolated_and_sanitized(tmp_path: Path) -> None:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("upstream-contract-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    source = FakeSource(
        package=upstream_package(),
        issues=(
            UpstreamItemIssue(
                session_id="00000000-0000-4000-8000-000000000099",
                code="UPSTREAM_REQUEST_FAILED",
                message="Upstream session could not be imported",
            ),
        ),
    )
    app = create_app(settings, trajectory_source=source)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await admin_headers(client)
        response = await client.post(
            "/api/acquisition/pull",
            headers=headers,
            json={"sessionIds": [ROOT]},
        )
        terminal = await app.state.jobs.wait(response.json()["jobId"])
        assert terminal.status == "completed"
        assert terminal.result is not None
        assert terminal.result["upstreamIssues"] == 1
        async with app.state.database.session() as session:
            errors = (
                await session.execute(
                    select(sync_runs.c.errors).where(sync_runs.c.id == terminal.id),
                )
            ).scalar_one()
        assert errors[0]["code"] == "UPSTREAM_REQUEST_FAILED"
        assert "must-not-leak" not in json.dumps(errors)


async def test_version_mismatch_fails_job_and_writes_no_payload(tmp_path: Path) -> None:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("upstream-contract-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    source = VersionFatalSource(package=upstream_package())
    app = create_app(settings, trajectory_source=source)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        headers = await admin_headers(client)
        response = await client.post(
            "/api/acquisition/pull",
            headers=headers,
            json={"sessionIds": [ROOT]},
        )
        terminal = await app.state.jobs.wait(response.json()["jobId"])
        assert terminal.status == "failed"
        async with app.state.database.session() as session:
            payload_count = int(
                (
                    await session.execute(
                        select(func.count()).select_from(trajectory_payloads),
                    )
                ).scalar_one(),
            )
        assert payload_count == 0


async def test_repeated_pull_has_zero_payload_side_effects(tmp_path: Path) -> None:
    """Repeating the same pull must preserve stable identities and runtime state."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("upstream-contract-test-signing-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        sync_interval_seconds=0,
    )
    source = FakeSource(package=upstream_package())
    app = create_app(settings, trajectory_source=source)
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
        async with app.state.database.session() as session:
            first_source = (await session.execute(select(source_records))).mappings().one()

        second = await client.post(
            "/api/acquisition/pull",
            headers=headers,
            json={"sessionIds": [ROOT]},
        )
        terminal = await app.state.jobs.wait(second.json()["jobId"])
        assert terminal.result is not None
        assert terminal.result["payloadsInserted"] == 0
        assert terminal.result["payloadsUpdated"] == 0
        assert terminal.result["payloadsUnchanged"] == 1

        async with app.state.database.session() as session:
            payload_count = int(
                (
                    await session.execute(
                        select(func.count()).select_from(trajectory_payloads),
                    )
                ).scalar_one(),
            )
            second_source = (await session.execute(select(source_records))).mappings().one()
        assert payload_count == 1
        assert second_source["id"] == first_source["id"]
        assert second_source["received_at"] == first_source["received_at"]
        assert second_source["processed_at"] == first_source["processed_at"]
        assert second_source["processed_hash"] == first_source["processed_hash"]
        assert second_source["parser_version"] == first_source["parser_version"]
