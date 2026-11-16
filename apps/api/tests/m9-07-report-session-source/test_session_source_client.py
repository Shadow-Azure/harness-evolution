"""Per-report session envelope HTTP client, strict validation, and dispatch."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator, Mapping

import httpx
import pytest

from app.errors import AppError
from app.service.acquisition.parsers import (
    AgentMetaFacts,
    BaseTraceParser,
    ParseContext,
    TraceParserFactory,
    UnsupportedTraceRuntime,
)
from app.service.acquisition.parsers.base import _dict, _string
from app.third_party_api.session_source import (
    BaseSessionSourceAdapter,
    HttpSessionSourceClient,
    SessionSourceFactory,
)

ROOT = "root-session-1"
CHILD = "agent-child-1"


def _trajectory() -> tuple[str, int]:
    content = "\n".join(
        [
            json.dumps({"type": "user", "message": {"content": "prompt"}}),
            json.dumps({"type": "assistant", "message": {"id": "m1"}}),
        ],
    )
    return content, 2


def envelope(**overrides: object) -> dict[str, object]:
    content, line_count = _trajectory()
    value: dict[str, object] = {
        "schemaVersion": 1,
        "sessionId": ROOT,
        "runtime": "claude-code",
        "runtimeVersion": "2.0.14",
        "agentKind": "main",
        "parentSessionId": None,
        "childSessionIds": [CHILD],
        "agentMeta": {"agentType": "general-purpose", "spawnDepth": 1},
        "trajectory": {"format": "ndjson", "lineCount": line_count, "content": content},
        "updatedAt": "2026-11-16T18:00:00+08:00",
    }
    value.update(overrides)
    return value


def _client(
    handler: Callable[[httpx.Request], Awaitable[httpx.Response]],
    **kwargs: object,
) -> HttpSessionSourceClient:
    return HttpSessionSourceClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
        **kwargs,
    )


def _error_code(exc: BaseException) -> str:
    assert isinstance(exc, AppError)
    return exc.code.value


def _fixed(body: object) -> Callable[[httpx.Request], Awaitable[httpx.Response]]:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return handler


@pytest.mark.asyncio
async def test_main_envelope_projects_claude_runtime_and_children() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=envelope())

    source = _client(handler)
    info = await source.fetch(
        session_url_template="https://trace.internal/api/sessions/{sessionId}?sig=abc",
        session_id=ROOT,
        expected_parent_id=None,
        declared_runtime="claude-code",
    )

    assert seen == ["https://trace.internal/api/sessions/root-session-1?sig=abc"]
    assert info.runtime_key == "claude-code"
    assert info.agent_kind == "main"
    assert info.child_session_ids == (CHILD,)
    assert info.agent_meta == {"agentType": "general-purpose", "spawnDepth": 1}
    assert info.trajectory.line_count == 2


@pytest.mark.asyncio
async def test_subagent_envelope_adds_parent_agent_metadata() -> None:
    source = _client(
        _fixed(
            envelope(
                sessionId=CHILD,
                agentKind="subagent",
                parentSessionId=ROOT,
                childSessionIds=[],
                agentMeta={"toolUseId": "tool-1"},
            ),
        ),
    )

    info = await source.fetch(
        session_url_template="https://trace.internal/api/sessions/{sessionId}",
        session_id=CHILD,
        expected_parent_id=ROOT,
    )

    assert info.agent_kind == "subagent"
    assert info.agent_meta == {"toolUseId": "tool-1", "parentAgentId": ROOT}


@pytest.mark.asyncio
async def test_schema_version_mismatch_is_stable() -> None:
    source = _client(_fixed(envelope(schemaVersion=2)))

    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_VERSION_INCOMPATIBLE"


@pytest.mark.asyncio
async def test_echoed_session_id_mismatch_is_stable() -> None:
    source = _client(_fixed(envelope(sessionId="another-session")))

    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_SESSION_MISMATCH"


@pytest.mark.asyncio
async def test_subagent_parent_mismatch_is_stable() -> None:
    source = _client(
        _fixed(
            envelope(
                sessionId=CHILD,
                agentKind="subagent",
                parentSessionId="another-parent",
            ),
        ),
    )

    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=CHILD,
            expected_parent_id=ROOT,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_SESSION_MISMATCH"


@pytest.mark.asyncio
async def test_unknown_runtime_fails_without_claude_fallback() -> None:
    source = _client(_fixed(envelope(runtime="opencode")))

    with pytest.raises(UnsupportedTraceRuntime) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert error.value.runtime_key == "opencode"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        pytest.param(
            {"trajectory": {"format": "ndjson", "lineCount": 1, "content": "[]"}},
            id="non-object",
        ),
        pytest.param(
            {"trajectory": {"format": "ndjson", "lineCount": 2, "content": ""}},
            id="empty",
        ),
        pytest.param({"agentMeta": {"unknownField": 1}}, id="unknown-claude-meta"),
        pytest.param(
            {"trajectory": {"format": "json", "lineCount": 0, "content": ""}},
            id="bad-format",
        ),
    ],
)
async def test_bad_envelope_content_is_rejected(override: dict[str, object]) -> None:
    source = _client(_fixed(envelope(**override)))

    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_line_count_mismatch_is_rejected() -> None:
    source = _client(
        _fixed(
            envelope(
                trajectory={
                    "format": "ndjson",
                    "lineCount": 3,
                    "content": _trajectory()[0],
                },
            ),
        ),
    )

    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_malformed_stored_template_is_rejected_without_a_request() -> None:
    called = {"value": False}

    async def handler(_request: httpx.Request) -> httpx.Response:
        called["value"] = True
        return httpx.Response(200, json=envelope())

    source = _client(handler)
    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_INVALID_RESPONSE"
    assert called["value"] is False


@pytest.mark.asyncio
async def test_retryable_status_then_success() -> None:
    calls = {"count": 0}

    async def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=envelope())

    source = _client(handler, max_retries=1, backoff_seconds=0)
    info = await source.fetch(
        session_url_template="https://trace.internal/api/sessions/{sessionId}",
        session_id=ROOT,
        expected_parent_id=None,
    )

    assert info.runtime_key == "claude-code"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_unauthorized_response_is_sanitized() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="secret detail")

    source = _client(handler)
    with pytest.raises(Exception) as error:
        await source.fetch(
            session_url_template="https://trace.internal/api/sessions/{sessionId}",
            session_id=ROOT,
            expected_parent_id=None,
        )

    assert _error_code(error.value) == "SESSION_SOURCE_UNAUTHORIZED"
    assert isinstance(error.value, AppError)
    assert "secret" not in error.value.message


@pytest.mark.asyncio
async def test_envelope_calls_are_serialized() -> None:
    state = {"active": 0, "max_active": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return httpx.Response(200, json=envelope(sessionId=request.url.path.rsplit("/", 1)[-1]))

    source = _client(handler)
    await asyncio.gather(
        *(
            source.fetch(
                session_url_template="https://trace.internal/api/sessions/{sessionId}",
                session_id=name,
                expected_parent_id=None,
            )
            for name in ("a", "b", "c")
        ),
    )

    assert state["max_active"] == 1


class FakeParser(BaseTraceParser):
    """Register the parser half of the fake runtime."""

    runtime_key = "fake-runtime"
    parser_version = 1

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        event = record.get("event")
        timestamp = ctx.observe_timestamp(record.get("at"))
        if event == "user":
            prompt = _string(record.get("prompt"))
            if prompt is not None:
                ctx.record_user_turn(prompt, timestamp, line_no)
            ctx.mark_user_input()
        elif event == "assistant":
            ctx.mark_assistant_record(fatal_error_unrecovered=False)
            ctx.record_assistant_message(
                message_id=_string(record.get("id")),
                model=_string(record.get("model")),
                usage=_dict(record.get("usage")),
            )

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        return AgentMetaFacts()


class FakeAdapter(BaseSessionSourceAdapter):
    """Register a second adapter without editing the factory."""

    runtime_key = "fake-runtime"

    def parse_agent_meta(self, meta: Mapping[str, object]) -> Mapping[str, object]:
        return {"kind": meta.get("kind")}


@pytest.fixture
def fake_adapter() -> Iterator[type[FakeAdapter]]:
    """Register both halves of one test runtime and restore both registries."""
    saved = dict(SessionSourceFactory._adapters)
    saved_parsers = dict(TraceParserFactory._parsers)
    TraceParserFactory.register(FakeParser)
    try:
        SessionSourceFactory.register(FakeAdapter)
        yield FakeAdapter
    finally:
        SessionSourceFactory._adapters.clear()
        SessionSourceFactory._adapters.update(saved)
        TraceParserFactory._parsers.clear()
        TraceParserFactory._parsers.update(saved_parsers)


@pytest.mark.asyncio
async def test_fake_runtime_dispatches_without_factory_edits(
    fake_adapter: type[FakeAdapter],
) -> None:
    source = _client(
        _fixed(
            envelope(
                runtime="fake-runtime",
                agentMeta={"kind": "projection"},
                childSessionIds=[],
            ),
        ),
    )

    info = await source.fetch(
        session_url_template="https://trace.internal/api/sessions/{sessionId}",
        session_id=ROOT,
        expected_parent_id=None,
    )

    assert info.runtime_key == "fake-runtime"
    assert info.agent_meta == {"kind": "projection"}


def test_claude_adapter_is_discovered_and_duplicate_registration_fails() -> None:
    """Package discovery registers Claude; a second owner cannot replace it."""
    from app.third_party_api.session_source.base import BaseSessionSourceAdapter
    from app.third_party_api.session_source.claude_code import (
        ClaudeCodeSessionSourceAdapter,
    )

    assert "claude-code" in SessionSourceFactory.registered_keys()

    class DuplicateAdapter(BaseSessionSourceAdapter):
        runtime_key = "claude-code"

        def parse_agent_meta(self, meta: Mapping[str, object]) -> Mapping[str, object]:
            return {}

    with pytest.raises(RuntimeError, match="duplicate session source runtime: claude-code"):
        SessionSourceFactory.register(DuplicateAdapter)
    assert isinstance(SessionSourceFactory.create("claude-code"), ClaudeCodeSessionSourceAdapter)
