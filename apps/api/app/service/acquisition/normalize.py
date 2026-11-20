"""Runtime-dispatched normalization facade over the trace parser registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.service.acquisition.parsers import (
    AgentLink,
    ParsedBlock,
    ParsedEvent,
    ParsedIssue,
    ParsedTranscript,
    ParsedUserTurn,
    RootMetadata,
    SessionParseResult,
    TraceParserFactory,
    TracePayload,
)

CURRENT_PARSER_VERSION = TraceParserFactory.version("claude-code")

__all__ = [
    "CURRENT_PARSER_VERSION",
    "AgentLink",
    "NormalizationAggregate",
    "NormalizationResult",
    "ParsedBlock",
    "ParsedEvent",
    "ParsedIssue",
    "ParsedTranscript",
    "ParsedUserTurn",
    "RootMetadata",
    "SessionParseResult",
    "aggregate_transcripts",
    "normalize_payloads",
    "normalize_transcript",
]

NormalizationResult = ParsedTranscript


@dataclass(frozen=True, slots=True)
class NormalizationAggregate:
    """Aggregate statistics that are safe to emit from local verification."""

    root_sessions: int
    agents: int
    lines: int
    messages_count: int
    tokens_total: int
    tools_count: int
    errors_count: int
    user_turns_count: int
    roots_with_model: int
    roots_with_user_turns: int
    models: tuple[str, ...]
    issues_count: int


def normalize_payloads(payloads: tuple[TracePayload, ...]) -> SessionParseResult:
    """Normalize one root session through the parser selected by trace shape.

    Callers are responsible for loading every payload of exactly one root first;
    the session parser then returns all transcripts and derived parent links.
    """
    parser = TraceParserFactory.for_trace(payloads)
    return parser.normalize_session()


def normalize_transcript(
    content: str,
    *,
    root_session_id: str,
    agent_id: str,
    agent_kind: Literal["main", "subagent"],
    agent_meta: dict[str, object] | None,
    runtime_key: str = "claude-code",
    knowledge_roots: tuple[str, ...] = (),
) -> ParsedTranscript:
    """Normalize one payload through its explicitly named runtime parser.

    This is the single-payload compatibility facade. The default keeps the
    historical Claude Code callers source-compatible; new session-level callers
    should build every root payload and use ``normalize_payloads`` instead.
    """
    payload = TracePayload(
        content=content,
        root_session_id=root_session_id,
        agent_id=agent_id,
        agent_kind=agent_kind,
        runtime_key=runtime_key,
        agent_meta=agent_meta,
        knowledge_roots=knowledge_roots,
    )
    parser = TraceParserFactory.for_payload(runtime_key, payload)
    return parser.normalize(payload)


def aggregate_transcripts(
    transcripts: tuple[ParsedTranscript, ...],
) -> NormalizationAggregate:
    """Return deterministic aggregate-only output for imported local payloads."""
    mains = [transcript for transcript in transcripts if transcript.agent_kind == "main"]
    return NormalizationAggregate(
        root_sessions=len(mains),
        agents=len(transcripts),
        lines=sum(transcript.lines for transcript in transcripts),
        messages_count=sum(transcript.messages_count for transcript in transcripts),
        tokens_total=sum(transcript.tokens_total for transcript in transcripts),
        tools_count=sum(transcript.tools_count for transcript in transcripts),
        errors_count=sum(transcript.errors_count for transcript in transcripts),
        user_turns_count=sum(len(transcript.user_turns) for transcript in mains),
        roots_with_model=sum(transcript.model is not None for transcript in mains),
        roots_with_user_turns=sum(bool(transcript.user_turns) for transcript in mains),
        models=tuple(
            sorted(
                {model for transcript in transcripts for model in transcript.models if model},
            ),
        ),
        issues_count=sum(len(transcript.issues) for transcript in transcripts),
    )
