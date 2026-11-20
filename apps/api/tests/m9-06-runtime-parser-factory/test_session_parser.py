"""Session-scoped parser selection, members, links, and compatibility contracts."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

import pytest

from app.service.acquisition.agent_tree import assemble_agent_trees
from app.service.acquisition.parsers import (
    AgentLink,
    AgentMetaFacts,
    AmbiguousTraceRuntime,
    BaseTraceParser,
    ParseContext,
    ParsedTranscript,
    SessionParseResult,
    TraceParserFactory,
    TracePayload,
    UnsupportedTraceRuntime,
)

ROOT_ID = "11111111-1111-4111-8111-111111111111"
CALLS: dict[str, str] = {
    "call_agent_codegen": "aaaaaaaaaaaaaaaa",
    "call_agent_spec": "bbbbbbbbbbbbbbbb",
    "call_agent_quality": "cccccccccccccccc",
}


def jsonl(*records: object) -> str:
    """Encode deterministic synthetic JSONL."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def payload(
    content: str,
    *,
    agent_id: str = ROOT_ID,
    agent_kind: str = "main",
    agent_meta: dict[str, object] | None = None,
    runtime_key: str = "claude-code",
) -> TracePayload:
    """Build one session payload with an explicit root identity."""
    return TracePayload(
        content=content,
        root_session_id=ROOT_ID,
        agent_id=agent_id,
        agent_kind=agent_kind,  # type: ignore[arg-type]
        runtime_key=runtime_key,
        agent_meta=agent_meta,
    )


def claude_main() -> str:
    """Build a synthetic root that spawns three Agents and returns their ids."""
    records: list[object] = [
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "timestamp": "2026-11-20T01:00:00Z",
            "message": {"content": "implement the issue"},
        },
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "timestamp": "2026-11-20T01:01:00Z",
            "message": {
                "id": "main-message",
                "model": "claude-main",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": "Agent",
                        "input": {"subagent_type": name, "description": f"spawn {name}"},
                    }
                    for call_id, name in (
                        ("call_agent_codegen", "codegen"),
                        ("call_agent_spec", "spec"),
                        ("call_agent_quality", "quality"),
                    )
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    ]
    for line_no, (call_id, native_agent_id) in enumerate(CALLS.items(), start=2):
        records.append(
            {
                "type": "user",
                "sessionId": ROOT_ID,
                "timestamp": f"2026-11-20T01:0{line_no}:00Z",
                "toolUseResult": {"agentId": native_agent_id},
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": "done",
                        },
                    ],
                },
            },
        )
    return jsonl(*records)


def claude_child(native_agent_id: str, *, agent_id: str | None = None) -> TracePayload:
    """Build one child transcript whose top-level records carry ``agentId``."""
    content = jsonl(
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "agentId": native_agent_id,
            "timestamp": "2026-11-20T02:00:00Z",
            "message": {
                "id": f"child-{native_agent_id}",
                "model": "claude-child",
                "content": [],
                "usage": {"input_tokens": 3, "output_tokens": 1},
            },
        },
    )
    return payload(
        content,
        agent_id=agent_id or native_agent_id,
        agent_kind="subagent",
        agent_meta={"agentType": "Explore", "spawnDepth": 1},
    )


def full_session() -> tuple[TracePayload, ...]:
    """Return one main plus three unlinked-but-evidenced subagents."""
    return (
        payload(claude_main()),
        *(claude_child(native_id) for native_id in CALLS.values()),
    )


def event_payload() -> TracePayload:
    """Return a non-Claude event-shaped payload."""
    return payload(
        jsonl(
            {"event": "user", "prompt": "hello"},
            {"event": "assistant", "id": "m1", "model": "fake"},
        ),
        runtime_key="fake-runtime",
    )


class EventTraceParser(BaseTraceParser):
    """Test runtime whose selection depends only on trace content."""

    runtime_key = "event-runtime"
    parser_version = 3

    @classmethod
    def can_parse(cls, payloads: Sequence[TracePayload]) -> bool:
        """Accept only records carrying the fake ``event`` discriminator."""
        if not payloads:
            return False
        for item in payloads:
            first = json.loads(item.content.splitlines()[0])
            if not isinstance(first, dict) or "event" not in first:
                return False
        return True

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Consume no records: this runtime exists only for selection tests."""

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Return empty facts for the selection-only runtime."""
        return AgentMetaFacts()


class BroadTraceParser(BaseTraceParser):
    """Test runtime that claims every trace and proves ambiguity is explicit."""

    runtime_key = "broad-runtime"
    parser_version = 1

    @classmethod
    def can_parse(cls, payloads: Sequence[TracePayload]) -> bool:
        """Claim every non-empty payload to force an ambiguous selection."""
        return bool(payloads)

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Consume no records: this runtime exists only for ambiguity tests."""

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Return empty facts for the ambiguity-only runtime."""
        return AgentMetaFacts()


@contextmanager
def registered(parser_cls: type[BaseTraceParser]) -> Iterator[None]:
    """Register one parser for a test and restore the production registry."""
    saved = dict(TraceParserFactory._parsers)
    TraceParserFactory.register(parser_cls)
    try:
        yield
    finally:
        TraceParserFactory._parsers.clear()
        TraceParserFactory._parsers.update(saved)


def test_claude_can_parse_accepts_claude_shape_and_rejects_others() -> None:
    """The cheap prefix probe recognizes Claude records and never claims fake JSONL."""
    claude_payloads = full_session()
    assert TraceParserFactory.for_trace(claude_payloads).runtime_key == "claude-code"
    assert TraceParserFactory.for_trace((payload(claude_main()),)).runtime_key == "claude-code"

    fake = event_payload()
    with pytest.raises(UnsupportedTraceRuntime):
        TraceParserFactory.for_trace((fake,))

    arbitrary = payload(jsonl({"kind": "mystery"}))
    with pytest.raises(UnsupportedTraceRuntime):
        TraceParserFactory.for_trace((arbitrary,))

    generic_message = payload(
        jsonl({"type": "message", "message": {"content": "not Claude"}}),
        runtime_key="codex",
    )
    with pytest.raises(UnsupportedTraceRuntime):
        TraceParserFactory.for_trace((generic_message,))

    malformed = payload(jsonl("{not-json}", 42))
    with pytest.raises(UnsupportedTraceRuntime):
        TraceParserFactory.for_trace((malformed,))


def test_for_trace_selects_by_content_not_runtime_key() -> None:
    """A correctly shaped trace selects its parser even under a wrong runtime key."""
    with registered(EventTraceParser):
        parser = TraceParserFactory.for_trace((event_payload(),))
    assert isinstance(parser, EventTraceParser)
    assert parser.runtime_key == "event-runtime"


def test_trace_shape_selection_keeps_payload_identity_and_reports_mismatch() -> None:
    """A shape-selected parser records a diagnostic when the payload runtime differs."""
    item = payload(claude_main(), runtime_key="codex")
    parser = TraceParserFactory.for_trace((item,))

    result = parser.normalize_session()

    assert result.transcripts[0].runtime_key == "codex"
    assert any(issue.code == "RUNTIME_SHAPE_MISMATCH" for issue in result.transcripts[0].issues)


def test_for_trace_rejects_ambiguity_without_registration_order_fallback() -> None:
    """Two accepting parsers raise a stable ambiguity instead of picking one."""
    with registered(BroadTraceParser), pytest.raises(AmbiguousTraceRuntime) as error:
        TraceParserFactory.for_trace((payload(claude_main()),))
    assert error.value.runtime_keys == ("broad-runtime", "claude-code")


def test_explicit_create_keeps_single_payload_compatibility() -> None:
    """The explicit entry still instantiates a named parser for one payload."""
    main = payload(claude_main())
    parser = TraceParserFactory.create("claude-code", (main,))
    assert parser.runtime_key == "claude-code"
    assert parser.parser_version == 7


def test_session_parser_exposes_main_and_subagents() -> None:
    """Construction binds the whole root session before normalization starts."""
    main = payload(claude_main())
    children = tuple(claude_child(native_id) for native_id in CALLS.values())
    parser = TraceParserFactory.create("claude-code", (main, *children))
    assert parser.main == main
    assert parser.subagents == children
    assert parser.payloads == (main, *children)


def test_session_parser_rejects_inconsistent_identity() -> None:
    """Duplicate mains, mixed roots, and mixed runtimes are rejected early."""
    main = payload(claude_main())
    child = claude_child(CALLS["call_agent_codegen"])
    with pytest.raises(ValueError, match="exactly one main"):
        TraceParserFactory.create("claude-code", (child,))
    with pytest.raises(ValueError, match="exactly one main"):
        TraceParserFactory.create("claude-code", (main, main))
    other_root = TracePayload(
        content=main.content,
        root_session_id="22222222-2222-4222-8222-222222222222",
        agent_id="22222222-2222-4222-8222-222222222222",
        agent_kind="main",
    )
    with pytest.raises(ValueError, match="one root session"):
        TraceParserFactory.create("claude-code", (main, other_root))
    mixed_runtime = TracePayload(
        content=child.content,
        root_session_id=ROOT_ID,
        agent_id=child.agent_id,
        agent_kind="subagent",
        runtime_key="other-runtime",
    )
    with pytest.raises(ValueError, match="one trace runtime"):
        TraceParserFactory.create("claude-code", (main, mixed_runtime))


def test_normalize_session_binds_members_and_returns_transcripts_and_links() -> None:
    """A single call yields every transcript plus the three derived links."""
    parser = TraceParserFactory.for_trace(full_session())
    result = parser.normalize_session()

    assert isinstance(result, SessionParseResult)
    assert {transcript.agent_id for transcript in result.transcripts} == {
        ROOT_ID,
        *CALLS.values(),
    }
    assert len(result.transcripts) == 4
    assert len(result.links) == 3
    assert {link.child_agent_id for link in result.links} == set(CALLS.values())
    assert {link.parent_tool_use_id for link in result.links} == set(CALLS)
    assert all(link.confidence == "derived" for link in result.links)


def test_three_subagents_attach_to_real_parent_calls_as_derived() -> None:
    """toolUseResult.agentId plus child agentId replaces all synthetic edges."""
    parser = TraceParserFactory.for_trace(full_session())
    session = parser.normalize_session()

    assembled = assemble_agent_trees(
        session.transcripts,
        {ROOT_ID: session.links},
    )
    tree = assembled.trees[0]
    by_id = {node.id: node for node in tree.nodes}
    main = by_id[ROOT_ID]
    events = {
        event.tool_use_id: event
        for event in main.events
        if event.kind == "agent" and event.tool_use_id is not None
    }

    for call_id, native_agent_id in CALLS.items():
        node = by_id[native_agent_id]
        assert node.parent_agent_id == ROOT_ID
        assert node.tool_use_id == call_id
        assert events[call_id].relation_confidence == "derived"
        assert (
            events[call_id].name
            == {
                "call_agent_codegen": "codegen",
                "call_agent_spec": "spec",
                "call_agent_quality": "quality",
            }[call_id]
        )

    assert not [
        event
        for node in tree.nodes
        for event in node.events
        if event.name == "synthetic-agent" or (event.tool_use_id or "").startswith("synthetic-")
    ]
    assert not [issue for issue in assembled.issues if issue.code == "MISSING_PARENT_TOOL_USE_ID"]


def test_agent_id_on_a_non_agent_tool_result_is_not_a_link() -> None:
    """Only Agent calls may turn a record-level agentId into a parent claim."""
    main = payload(
        jsonl(
            {
                "type": "assistant",
                "sessionId": ROOT_ID,
                "message": {
                    "id": "main-message",
                    "model": "claude-main",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-read",
                            "name": "Read",
                            "input": {"file_path": "/workspace/read.md"},
                        },
                    ],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
            {
                "type": "user",
                "sessionId": ROOT_ID,
                "toolUseResult": {"agentId": CALLS["call_agent_codegen"]},
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-read",
                            "content": "ok",
                        },
                    ],
                },
            },
        ),
    )
    child = claude_child(CALLS["call_agent_codegen"])
    parser = TraceParserFactory.create("claude-code", (main, child))

    result = parser.normalize_session()

    assert result.links == ()
    assert result.transcripts[0].agent_result_ids == {}


def test_existing_authoritative_parent_is_not_overridden() -> None:
    """A child that carries meta.toolUseId keeps its authoritative edge."""
    main = payload(claude_main())
    authoritative = claude_child(
        CALLS["call_agent_codegen"],
        agent_id="agent-authoritative",
    )
    authoritative = TracePayload(
        content=authoritative.content,
        root_session_id=ROOT_ID,
        agent_id=authoritative.agent_id,
        agent_kind="subagent",
        agent_meta={"agentType": "Explore", "toolUseId": "call_agent_codegen"},
    )
    other_children = tuple(
        claude_child(native_id)
        for call_id, native_id in CALLS.items()
        if call_id != "call_agent_codegen"
    )
    parser = TraceParserFactory.for_trace((main, authoritative, *other_children))
    session = parser.normalize_session()

    assert {link.child_agent_id for link in session.links} == {
        native for call_id, native in CALLS.items() if call_id != "call_agent_codegen"
    }
    tree = assemble_agent_trees(session.transcripts, {ROOT_ID: session.links}).trees[0]
    by_id = {node.id: node for node in tree.nodes}
    assert by_id["agent-authoritative"].parent_agent_id == ROOT_ID
    assert by_id["agent-authoritative"].tool_use_id == "call_agent_codegen"
    main_node = by_id[ROOT_ID]
    authoritative_event = next(
        event
        for event in main_node.events
        if event.kind == "agent" and event.tool_use_id == "call_agent_codegen"
    )
    assert authoritative_event.relation_confidence == "authoritative"


def test_missing_or_ambiguous_link_keeps_synthetic_fallback() -> None:
    """No derived link leaves the existing synthetic edge and stable issue."""
    parser = TraceParserFactory.for_trace(full_session())
    session = parser.normalize_session()

    without_links = assemble_agent_trees(session.transcripts)
    tree = without_links.trees[0]
    synthetic = [
        event for node in tree.nodes for event in node.events if event.name == "synthetic-agent"
    ]
    assert len(synthetic) == 3
    assert {
        issue.agent_id
        for issue in without_links.issues
        if issue.code == "MISSING_PARENT_TOOL_USE_ID"
    } == set(CALLS.values())

    duplicated = (
        *full_session(),
        claude_child(CALLS["call_agent_quality"], agent_id="agent-duplicate"),
    )
    duplicated_parser = TraceParserFactory.for_trace(duplicated)
    duplicated_session = duplicated_parser.normalize_session()
    assert not any(
        link.child_agent_id in {"agent-duplicate", CALLS["call_agent_quality"]}
        for link in duplicated_session.links
    )
    duplicated_tree = assemble_agent_trees(
        duplicated_session.transcripts,
        {ROOT_ID: duplicated_session.links},
    ).trees[0]
    assert any(
        event.name == "synthetic-agent" for node in duplicated_tree.nodes for event in node.events
    )


def test_link_resolution_ignores_multiply_claimed_child() -> None:
    """Two parent calls claiming one child identity produce no derived link."""
    content = jsonl(
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "agentId": CALLS["call_agent_codegen"],
            "message": {"id": "child", "model": "claude-child", "content": []},
        },
    )
    # Same native id is returned by two different parent calls.
    claims = jsonl(
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "toolUseResult": {"agentId": CALLS["call_agent_codegen"]},
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "call_agent_codegen"},
                    {"type": "tool_result", "tool_use_id": "call_agent_spec"},
                ],
            },
        },
    )
    parser = TraceParserFactory.for_trace(
        (
            payload(claude_main() + claims),
            payload(
                content,
                agent_id="agent-multi-claimed",
                agent_kind="subagent",
            ),
        ),
    )
    session = parser.normalize_session()
    assert session.links == ()


def test_compatibility_normalize_and_extract_evidence_still_work() -> None:
    """The single-payload facade keeps normalize and evidence behavior."""
    content = jsonl(
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "agentId": CALLS["call_agent_codegen"],
            "timestamp": "2026-11-20T02:00:00Z",
            "message": {
                "id": "read-message",
                "model": "claude-child",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-read",
                        "name": "Read",
                        "input": {"file_path": "/workspace/knowledge.md"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "agentId": CALLS["call_agent_codegen"],
            "timestamp": "2026-11-20T02:01:00Z",
            "toolUseResult": {
                "file": {"filePath": "/workspace/knowledge.md", "content": "body\n"},
            },
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool-read", "content": "ok"},
                ],
            },
        },
    )
    item = payload(
        content,
        agent_id=CALLS["call_agent_codegen"],
        agent_kind="subagent",
        agent_meta={"agentType": "Explore", "toolUseId": "call_agent_codegen"},
    )
    parser = TraceParserFactory.for_payload("claude-code", item)

    parsed = parser.normalize(item)
    assert isinstance(parsed, ParsedTranscript)
    assert parsed.agent_id == CALLS["call_agent_codegen"]
    assert parsed.native_agent_id == CALLS["call_agent_codegen"]
    assert parsed.parent_tool_use_id == "call_agent_codegen"
    assert [evidence.kind for evidence in parsed.evidence] == ["file_read"]
    assert parser.extract_evidence(item) == parsed.evidence

    session = parser.normalize_session()
    assert session.transcripts == (parsed,)
    assert session.links == ()


def test_agent_link_contract_is_explicit() -> None:
    """The link value object carries child, real parent call, and confidence."""
    link = AgentLink(child_agent_id="agent-a", parent_tool_use_id="call-a")
    assert link == AgentLink(
        child_agent_id="agent-a",
        parent_tool_use_id="call-a",
        confidence="derived",
    )
