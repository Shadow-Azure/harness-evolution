"""Trace parser registry and runtime dispatch contracts."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence

import pytest

from app.service.acquisition.normalize import normalize_transcript
from app.service.acquisition.parsers import (
    AgentMetaFacts,
    BaseTraceParser,
    ParseContext,
    ParsedTranscript,
    TraceParserFactory,
    TracePayload,
    UnsupportedTraceRuntime,
)
from app.service.acquisition.parsers.base import _dict, _string

ROOT_ID = "11111111-1111-4111-8111-111111111111"


def jsonl(*records: object) -> str:
    """Encode deterministic fake-runtime JSONL."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def trace_payload(
    content: str,
    *,
    agent_id: str = ROOT_ID,
    agent_kind: str = "main",
    agent_meta: dict[str, object] | None = None,
    runtime_key: str = "fake-runtime",
) -> TracePayload:
    """Build one session payload for factory and parser tests."""
    return TracePayload(
        content=content,
        root_session_id=ROOT_ID,
        agent_id=agent_id,
        agent_kind=agent_kind,  # type: ignore[arg-type]
        runtime_key=runtime_key,
        agent_meta=agent_meta,
    )


class FakeTraceParser(BaseTraceParser):
    """Minimal second runtime proving only registration is required."""

    runtime_key = "fake-runtime"
    parser_version = 1

    @classmethod
    def can_parse(cls, payloads: Sequence[TracePayload]) -> bool:
        """Accept only the tiny fake event schema, never a Claude transcript."""
        if not payloads:
            return False
        for payload in payloads:
            first_line = next(
                (line for line in payload.content.splitlines() if line.strip()),
                "",
            )
            try:
                first = json.loads(first_line)
            except json.JSONDecodeError:
                return False
            if not isinstance(first, dict) or "event" not in first or "type" in first:
                return False
        return True

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Interpret a tiny event schema independent of Claude field names."""
        event = record.get("event")
        timestamp = ctx.observe_timestamp(record.get("at"))
        if event == "user":
            prompt = _string(record.get("prompt"))
            if prompt is not None:
                ctx.record_user_turn(prompt, timestamp, line_no)
            ctx.mark_user_input()
            return
        if event != "assistant":
            return
        ctx.mark_assistant_record(fatal_error_unrecovered=False)
        message_offset = ctx.record_assistant_message(
            message_id=_string(record.get("id")),
            model=_string(record.get("model")),
            usage=_dict(record.get("usage")),
        )
        tool = _dict(record.get("tool"))
        if tool:
            ctx.record_tool_use(
                line_no=line_no,
                message_offset=message_offset,
                tool_use_id=_string(tool.get("id")),
                name=_string(tool.get("name")),
                trigger_kind="agent",
                description=_string(tool.get("description")),
            )

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Read the same generic subagent hints used by the fake fixture."""
        depth = meta.get("spawnDepth")
        return AgentMetaFacts(
            agent_type=_string(meta.get("agentType")),
            parent_tool_use_id=_string(meta.get("toolUseId")),
            spawn_depth=depth if isinstance(depth, int) and depth >= 0 else 0,
        )


class DuplicateClaudeParser(BaseTraceParser):
    """Attempt to claim an already registered runtime identity."""

    runtime_key = "claude-code"
    parser_version = 99

    @classmethod
    def can_parse(cls, payloads: Sequence[TracePayload]) -> bool:
        """Never reach shape selection: registration fails first."""
        return False

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Unreachable: registration fails before normalization."""

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Return empty facts for the unreachable duplicate."""
        return AgentMetaFacts()


@pytest.fixture
def fake_runtime() -> Iterator[type[FakeTraceParser]]:
    """Register one test runtime and restore the production registry afterwards."""
    saved = dict(TraceParserFactory._parsers)
    TraceParserFactory.register(FakeTraceParser)
    try:
        yield FakeTraceParser
    finally:
        TraceParserFactory._parsers.clear()
        TraceParserFactory._parsers.update(saved)


def test_claude_parser_is_discovered_at_package_import() -> None:
    """Package discovery registers the only production runtime."""
    assert "claude-code" in TraceParserFactory.registered_keys()
    payload = trace_payload(
        jsonl({"type": "user", "sessionId": ROOT_ID, "message": {"content": "hi"}}),
        runtime_key="claude-code",
    )
    parser = TraceParserFactory.create("claude-code", (payload,))
    assert parser.runtime_key == "claude-code"
    assert parser.parser_version == 8


def test_duplicate_runtime_registration_is_rejected() -> None:
    """A second class claiming one runtime fails instead of silently replacing it."""
    with pytest.raises(RuntimeError, match="duplicate trace runtime: claude-code"):
        TraceParserFactory.register(DuplicateClaudeParser)


def test_unknown_runtime_never_falls_back_to_claude() -> None:
    """An unregistered runtime raises its own stable error type."""
    payload = trace_payload(
        jsonl({"event": "user"}),
    )
    with pytest.raises(UnsupportedTraceRuntime) as error:
        TraceParserFactory.create("unknown-runtime", (payload,))
    assert error.value.runtime_key == "unknown-runtime"


def test_fake_runtime_is_selected_by_normalize_facade(
    fake_runtime: type[FakeTraceParser],
) -> None:
    """Registration alone makes the facade dispatch to the new runtime."""
    parsed = normalize_transcript(
        jsonl(
            {
                "event": "user",
                "at": "2026-10-22T01:00:00Z",
                "prompt": "fake prompt",
            },
            {
                "event": "assistant",
                "id": "fake-message",
                "model": "fake-model",
                "at": "2026-10-22T01:01:00Z",
                "usage": {"input_tokens": 4, "output_tokens": 2},
                "tool": {"id": "tool-fake", "name": "fake-agent"},
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
        runtime_key=fake_runtime.runtime_key,
    )

    assert isinstance(parsed, ParsedTranscript)
    assert parsed.runtime_key == "fake-runtime"
    assert parsed.parser_version == 1
    assert parsed.messages_count == 1
    assert parsed.tokens_total == 6
    assert parsed.tools_count == 1
    assert [event.kind for event in parsed.events] == ["agent"]
    assert parsed.user_turns[0].prompt_text == "fake prompt"


def test_parser_versions_are_read_per_runtime(
    fake_runtime: type[FakeTraceParser],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upgrading one runtime's parser does not change another runtime's version."""
    assert TraceParserFactory.versions() == {"claude-code": 8, "fake-runtime": 1}
    monkeypatch.setattr(fake_runtime, "parser_version", 2)
    assert TraceParserFactory.versions() == {"claude-code": 8, "fake-runtime": 2}
