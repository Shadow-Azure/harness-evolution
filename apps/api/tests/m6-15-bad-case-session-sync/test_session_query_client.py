"""HTTP query-service adapter: bare-array children, NDJSON trajectories, serial calls."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.third_party_api.session_query.http import HttpSessionQuerySource


def _client(
    handler: Callable[[httpx.Request], Awaitable[httpx.Response]],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://query.test",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        headers={"Authorization": "Bearer test-token"},
    )


@pytest.mark.asyncio
async def test_list_children_accepts_bare_array() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sessions/root-1/children"
        return httpx.Response(200, json=["child-a", "child-b"])

    client = _client(handler)
    source = HttpSessionQuerySource(client)
    try:
        assert await source.list_children("root-1") == ("child-a", "child-b")
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_list_children_rejects_object_wrapper_and_non_strings() -> None:
    async def wrapped(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sessionIds": ["child-a"]})

    source = HttpSessionQuerySource(_client(wrapped))
    try:
        with pytest.raises(AppError) as error:
            await source.list_children("root-1")
        assert error.value.code is ErrorCode.SESSION_QUERY_INVALID_RESPONSE
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_trajectory_parses_ndjson_and_canonicalizes_lines() -> None:
    body = "\n".join(
        [
            json.dumps({"type": "assistant", "n": 1, "text": "你好"}),
            "",
            json.dumps({"type": "user", "n": 2}),
        ],
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sessions/agent-a/trajectory"
        return httpx.Response(200, text=body, headers={"content-type": "application/x-ndjson"})

    source = HttpSessionQuerySource(_client(handler))
    try:
        trajectory = await source.fetch_trajectory("agent-a")
        assert trajectory.line_count == 2
        assert trajectory.content.splitlines() == [
            '{"type":"assistant","n":1,"text":"你好"}',
            '{"type":"user","n":2}',
        ]
    finally:
        await source.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("", ErrorCode.TRAJECTORY_EMPTY),
        ("[1, 2]", ErrorCode.SESSION_QUERY_INVALID_RESPONSE),
        ('{"a": 1}\n[2]', ErrorCode.SESSION_QUERY_INVALID_RESPONSE),
        ('{"a": 1, "a": 2}', ErrorCode.SESSION_QUERY_INVALID_RESPONSE),
    ],
)
async def test_trajectory_rejects_empty_or_non_object(body: str, code: ErrorCode) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    source = HttpSessionQuerySource(_client(handler))
    try:
        with pytest.raises(AppError) as error:
            await source.fetch_trajectory("agent-a")
        assert error.value.code is code
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_trajectory_calls_are_serialized() -> None:
    state = {"active": 0, "max_active": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return httpx.Response(200, text='{"type":"assistant"}')

    source = HttpSessionQuerySource(_client(handler))
    try:
        await asyncio.gather(
            source.fetch_trajectory("agent-a"),
            source.fetch_trajectory("agent-b"),
            source.fetch_trajectory("agent-c"),
        )
        assert state["max_active"] == 1
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_retries_retryable_status_then_succeeds() -> None:
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=["child-a"])

    source = HttpSessionQuerySource(_client(handler), max_retries=1, backoff_seconds=0)
    try:
        assert await source.list_children("root-1") == ("child-a",)
        assert calls["count"] == 2
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_unauthorized_is_stable_and_sanitized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="secret upstream detail")

    source = HttpSessionQuerySource(_client(handler))
    try:
        with pytest.raises(AppError) as error:
            await source.list_children("root-1")
        assert error.value.code is ErrorCode.SESSION_QUERY_UNAUTHORIZED
        assert "secret" not in error.value.message
    finally:
        await source.close()


def test_settings_expose_available_only_with_url_and_token() -> None:
    without = Settings(jwt_secret=SecretStr("settings-test-secret"))
    assert without.session_query_configured is False

    configured = Settings(
        jwt_secret=SecretStr("settings-test-secret"),
        session_query_base_url="http://query.test",
        session_query_token=SecretStr("token"),
    )
    assert configured.session_query_configured is True
