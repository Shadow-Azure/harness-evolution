"""HttpTrajectorySource behavior against deterministic mock transport."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, cast

import httpx
import pytest

from app.errors import AppError, ErrorCode
from app.third_party_api.trajectory.http import HttpTrajectorySource
from app.third_party_api.trajectory.models import TrajectoryPackage, TrajectoryWindow

ROOT = "00000000-0000-4000-8000-000000000001"
ROOT_2 = "00000000-0000-4000-8000-000000000002"


def package_json(session_id: str = ROOT) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "metadata": {
            "project": "p",
            "model": "m",
            "startedAt": "2026-10-20T01:00:00+08:00",
            "endedAt": "2026-10-20T01:01:00+08:00",
            "problemFlag": True,
            "problemTags": [],
        },
        "transcripts": [
            {"kind": "main", "agentId": None, "lines": ["{}"]},
        ],
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
    sleeps: list[float] | None = None,
) -> tuple[HttpTrajectorySource, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(cast(Any, handler)),
        base_url="https://upstream.test",
        headers={"Authorization": "Bearer secret"},
        timeout=1,
    )
    observed_sleeps = sleeps if sleeps is not None else []

    async def sleep(delay: float) -> None:
        observed_sleeps.append(delay)
        await asyncio.sleep(0)

    return (
        HttpTrajectorySource(
            client,
            max_retries=3,
            backoff_seconds=0.25,
            sleep=sleep,
            max_pages=10,
        ),
        client,
    )


async def test_fetch_returns_validated_package() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["authorization"] == "Bearer secret"
        return response(200, package_json())

    source, client = await source_for(handler)
    async with client:
        package = await source.fetch(ROOT)
    assert isinstance(package, TrajectoryPackage)
    assert calls == 1


async def test_fetch_rejects_package_for_a_different_session() -> None:
    """Never accept another session's package for the requested identity."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, package_json(ROOT_2))

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError) as raised:
            await source.fetch(ROOT)
    assert raised.value.code is ErrorCode.UPSTREAM_INVALID_RESPONSE


@pytest.mark.parametrize("version", [None, "1", "2.0", "v1"])
async def test_version_incompatibility_fails_before_return(version: str | None) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, package_json(), version=version)

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError) as raised:
            await source.fetch(ROOT)
    assert raised.value.code is ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE


@pytest.mark.parametrize("status", [429, 501, 503])
async def test_retries_transient_failures_three_times_after_initial(status: int) -> None:
    calls = 0
    sleeps: list[float] = []

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 4:
            return response(status, {"error": "busy"})
        return response(200, package_json())

    source, client = await source_for(handler, sleeps)
    async with client:
        package = await source.fetch(ROOT)
    assert package.session_id == ROOT
    assert calls == 4
    assert sleeps == [0.25, 0.5, 1.0]


async def test_retries_timeout_then_succeeds() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow upstream", request=request)
        return response(200, package_json())

    source, client = await source_for(handler)
    async with client:
        package = await source.fetch(ROOT)
    assert package.session_id == ROOT
    assert calls == 2


async def test_rejects_duplicate_json_keys() -> None:
    body = (
        '{"sessionId":"00000000-0000-4000-8000-000000000001",'
        '"sessionId":"00000000-0000-4000-8000-000000000002",'
        '"transcripts":[]}'
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "X-Trajectory-Api-Version": "1.0",
            },
            content=body.encode(),
        )

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError) as raised:
            await source.fetch(ROOT)
    assert raised.value.code is ErrorCode.UPSTREAM_INVALID_RESPONSE


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_non_retryable_errors_stop_after_first_request(status: int) -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(status, {"error": "no"})

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError) as raised:
            await source.fetch(ROOT)
    assert calls == 1
    assert raised.value.code is ErrorCode.UPSTREAM_REQUEST_FAILED


async def test_list_window_follows_cursor_and_rejects_repeats() -> None:
    first = TrajectoryWindow.model_validate(
        {
            "items": [
                {
                    "sessionId": ROOT,
                    "startedAt": "2026-10-20T01:00:00+08:00",
                    "model": "m",
                    "problemFlag": True,
                },
            ],
            "nextCursor": "cursor-2",
        },
    )
    second = TrajectoryWindow.model_validate(
        {
            "items": [
                {
                    "sessionId": ROOT_2,
                    "startedAt": "2026-10-21T01:00:00+08:00",
                    "model": "m2",
                    "problemFlag": True,
                },
            ],
            "nextCursor": "",
        },
    )
    cursors: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        page = first if cursor is None else second
        return response(200, page.model_dump(by_alias=True, mode="json"))

    source, client = await source_for(handler)
    async with client:
        items = await source.list_window(
            from_date=date(2026, 10, 1),
            to_date=date(2026, 10, 31),
            problem_only=True,
            cursor=None,
        )
    assert [item.session_id for item in items] == [ROOT, ROOT_2]
    assert cursors == [None, "cursor-2"]


async def test_list_window_rejects_repeated_cursor() -> None:
    page = {
        "items": [],
        "nextCursor": "same",
    }

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, page)

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError) as raised:
            await source.list_window(
                from_date=date(2026, 10, 1),
                to_date=date(2026, 10, 31),
                problem_only=False,
                cursor=None,
            )
    assert raised.value.code is ErrorCode.UPSTREAM_INVALID_RESPONSE


async def test_version_error_is_not_retried() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(200, package_json(), version="2.0")

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError):
            await source.fetch(ROOT)
    assert calls == 1


async def test_fetch_many_isolates_failures_and_keeps_order() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        session_id = request.url.path.rsplit("/", 1)[-1]
        if session_id == ROOT_2:
            return response(404, {"error": "missing"})
        return response(200, package_json(session_id))

    source, client = await source_for(handler)
    async with client:
        result = await source.fetch_many([ROOT, ROOT_2])
    assert [item.session_id for item in result.packages] == [ROOT]
    assert len(result.issues) == 1
    assert result.issues[0].session_id == ROOT_2
    assert result.issues[0].code == "UPSTREAM_REQUEST_FAILED"
    assert "missing" not in result.issues[0].message


async def test_fetch_many_treats_version_mismatch_as_fatal() -> None:
    """Protocol incompatibility must stop the whole pull, not degrade to one item."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return response(200, package_json(), version="2.0")

    source, client = await source_for(handler)
    async with client:
        with pytest.raises(AppError) as raised:
            await source.fetch_many([ROOT, ROOT_2])
    assert raised.value.code is ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE


async def test_fetch_many_isolates_http_decoding_errors() -> None:
    """A corrupt body for one session must not hide later successful sessions."""

    async def handler(request: httpx.Request) -> httpx.Response:
        session_id = request.url.path.rsplit("/", 1)[-1]
        if session_id == ROOT:
            return httpx.Response(
                200,
                headers={
                    "content-encoding": "gzip",
                    "content-type": "application/json",
                    "X-Trajectory-Api-Version": "1.0",
                },
                content=b"not-gzip",
            )
        return response(200, package_json(ROOT_2))

    source, client = await source_for(handler)
    async with client:
        result = await source.fetch_many([ROOT, ROOT_2])
    assert [item.session_id for item in result.packages] == [ROOT_2]
    assert [item.session_id for item in result.issues] == [ROOT]
    assert result.issues[0].code == "UPSTREAM_INVALID_RESPONSE"
