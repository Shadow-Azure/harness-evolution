"""Pure, privacy-bounded normalization for one Claude Code JSONL payload."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal, cast

from app.utils.time import as_shanghai

CURRENT_PARSER_VERSION = 1

_CONTROL_PREFIXES = (
    "<local-command-caveat>",
    "<command-name>",
    "<task-notification>",
    "<system-reminder>",
)
_TRIGGER_KINDS: dict[str, Literal["skill", "agent", "workflow"]] = {
    "skill": "skill",
    "agent": "agent",
    "workflow": "workflow",
}


@dataclass(frozen=True, slots=True)
class ParsedIssue:
    """One stable parse issue that is safe to persist and expose."""

    session_id: str
    agent_id: str
    line_no: int
    code: str
    message: str

    def as_sync_error(self) -> dict[str, object]:
        """Return the camelCase storage representation."""
        return {
            "sessionId": self.session_id,
            "agentId": self.agent_id,
            "lineNo": self.line_no,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """A content block's non-sensitive structural identity."""

    kind: str
    tool_use_id: str | None = None
    name: str | None = None
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class ParsedUserTurn:
    """One user input anchor derived from the main transcript."""

    seq: int
    prompt_text: str
    started_at: datetime
    line_no: int
    message_offset: int


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    """One Skill, Agent, or Workflow trigger."""

    event_index: int
    line_no: int
    message_offset: int
    kind: Literal["skill", "agent", "workflow"]
    name: str | None
    description: str | None
    tool_use_id: str | None


@dataclass(frozen=True, slots=True)
class RootMetadata:
    """Root metadata copied from the main payload rather than inferred."""

    cwd: str | None = None
    git_branch: str | None = None
    cli_version: str | None = None
    entrypoint: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedTranscript:
    """Derived transcript statistics and anchors without message detail."""

    root_session_id: str
    agent_id: str
    agent_kind: Literal["main", "subagent"]
    parser_version: int
    agent_type: str | None
    task_kind: str | None
    team_name: str | None
    name: str | None
    skill_name: str | None
    model: str | None
    requested_model: str | None
    models: tuple[str, ...]
    parent_tool_use_id: str | None
    spawn_depth: int
    lines: int
    messages_count: int
    tokens_total: int
    tools_count: int
    errors_count: int
    user_turns: tuple[ParsedUserTurn, ...]
    blocks_outside_user_turns: tuple[ParsedBlock, ...]
    events: tuple[ParsedEvent, ...]
    issues: tuple[ParsedIssue, ...]
    agent_meta: Mapping[str, object]
    root_metadata: RootMetadata

    def agent_meta_dict(self) -> dict[str, object]:
        """Return a detached JSON-compatible copy of provider metadata."""
        return cast(dict[str, object], _thaw_json(self.agent_meta))


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


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject keys that normal JSON parsing would silently overwrite."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _physical_lines(content: str) -> list[str]:
    """Split JSONL framing on LF/CRLF while preserving Unicode separators."""
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def _dict(value: object) -> dict[str, object]:
    """Narrow an arbitrary JSON object without exposing it elsewhere."""
    return value if isinstance(value, dict) else {}


def _freeze_json(value: object) -> object:
    """Recursively detach JSON-shaped provider metadata from caller-owned values."""
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()},
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    """Return a detached JSON-compatible copy of recursively frozen metadata."""
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _string(value: object) -> str | None:
    """Return a non-empty scalar string."""
    return value if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> int:
    """Read a non-negative integer token counter."""
    return value if isinstance(value, int) and value >= 0 else 0


def _timestamp(value: object) -> datetime | None:
    """Parse an ISO timestamp and normalize it to Asia/Shanghai."""
    text = _string(value)
    if text is None:
        return None
    try:
        return as_shanghai(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _content_blocks(message: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Return object-shaped content blocks from one message."""
    content = message.get("content")
    if not isinstance(content, list):
        return ()
    return tuple(block for block in content if isinstance(block, dict))


def _event_name(kind: str, tool_input: dict[str, object], block: dict[str, object]) -> str | None:
    """Resolve the user-facing trigger name from provider input."""
    if kind == "skill":
        return _string(tool_input.get("skill")) or _string(tool_input.get("name"))
    if kind == "agent":
        return _string(tool_input.get("subagent_type")) or _string(tool_input.get("name"))
    return _string(tool_input.get("name")) or _string(block.get("name"))


def _text_from_content(content: object) -> str | None:
    """Extract textual user input while excluding tool-only content."""
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None
    blocks = [block for block in content if isinstance(block, dict)]
    if any(block.get("type") == "tool_result" for block in blocks):
        return None
    text = "".join(
        str(block.get("text", ""))
        for block in blocks
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    ).strip()
    return text or None


def _attachment_prompt(record: dict[str, object]) -> tuple[str | None, datetime | None]:
    """Read the real human attachment shape and its queued-command alias."""
    attachment = _dict(record.get("attachment"))
    if not attachment:
        return None, None
    queued = _dict(attachment.get("queued_command"))
    origin = _dict(attachment.get("origin")) or _dict(queued.get("origin"))
    if origin.get("kind") != "human":
        return None, None
    prompt = _string(attachment.get("prompt")) or _string(queued.get("prompt"))
    return prompt, _timestamp(record.get("timestamp"))


def _meta_string(meta: Mapping[str, object], key: str) -> str | None:
    """Read one optional metadata string."""
    return _string(meta.get(key))


def _meta_depth(meta: Mapping[str, object]) -> int:
    """Read a non-negative spawn depth."""
    value = meta.get("spawnDepth")
    return value if isinstance(value, int) and value >= 0 else 0


def _model(transcript_models: list[str]) -> str | None:
    """Choose the most frequent model, with first occurrence breaking ties."""
    if not transcript_models:
        return None
    counts = Counter(transcript_models)
    highest = max(counts.values())
    return next(model for model in transcript_models if counts[model] == highest)


def normalize_transcript(
    content: str,
    *,
    root_session_id: str,
    agent_id: str,
    agent_kind: Literal["main", "subagent"],
    agent_meta: dict[str, object] | None,
) -> ParsedTranscript:
    """Normalize one payload into counts and anchors, retaining no messages."""
    meta = cast(Mapping[str, object], _freeze_json(dict(agent_meta or {})))
    physical_lines = _physical_lines(content)
    issues: list[ParsedIssue] = []
    user_turns: list[ParsedUserTurn] = []
    blocks_outside_user_turns: list[ParsedBlock] = []
    events: list[ParsedEvent] = []
    seen_messages: set[str] = set()
    usage_by_message: dict[str, int] = {}
    transcript_models: list[str] = []
    model_sequence: list[str] = []
    root_metadata = RootMetadata()
    tokens_total = 0
    tools_count = 0
    errors_count = 0

    for line_no, line in enumerate(physical_lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError):
            issues.append(
                ParsedIssue(
                    session_id=root_session_id,
                    agent_id=agent_id,
                    line_no=line_no,
                    code="INVALID_JSONL_LINE",
                    message="JSONL line could not be parsed",
                ),
            )
            continue
        if not isinstance(raw, dict):
            issues.append(
                ParsedIssue(
                    session_id=root_session_id,
                    agent_id=agent_id,
                    line_no=line_no,
                    code="INVALID_TRANSCRIPT_RECORD",
                    message="JSONL record is not an object",
                ),
            )
            continue
        record = raw
        if not record:
            continue

        if agent_kind == "main":
            cwd = _string(record.get("cwd"))
            branch = _string(record.get("gitBranch"))
            version = _string(record.get("version"))
            entrypoint = _string(record.get("entrypoint"))
            root_metadata = RootMetadata(
                cwd=cwd or root_metadata.cwd,
                git_branch=branch or root_metadata.git_branch,
                cli_version=version or root_metadata.cli_version,
                entrypoint=entrypoint or root_metadata.entrypoint,
            )

        record_type = record.get("type")
        message = _dict(record.get("message"))
        is_user_turn = False
        if record_type == "user" and agent_kind == "main" and record.get("isMeta") is not True:
            prompt = _text_from_content(message.get("content"))
            if prompt is not None and not prompt.startswith(_CONTROL_PREFIXES):
                started_at = _timestamp(record.get("timestamp"))
                if started_at is None:
                    issues.append(
                        ParsedIssue(
                            session_id=root_session_id,
                            agent_id=agent_id,
                            line_no=line_no,
                            code="MISSING_USER_TURN_TIMESTAMP",
                            message="User turn timestamp is missing or invalid",
                        ),
                    )
                else:
                    user_turns.append(
                        ParsedUserTurn(
                            seq=len(user_turns) + 1,
                            prompt_text=prompt,
                            started_at=started_at,
                            line_no=line_no,
                            message_offset=len(seen_messages),
                        ),
                    )
                    is_user_turn = True
        elif agent_kind == "main" and record_type == "attachment":
            prompt, started_at = _attachment_prompt(record)
            if prompt is not None:
                if started_at is None:
                    issues.append(
                        ParsedIssue(
                            session_id=root_session_id,
                            agent_id=agent_id,
                            line_no=line_no,
                            code="MISSING_USER_TURN_TIMESTAMP",
                            message="User turn timestamp is missing or invalid",
                        ),
                    )
                else:
                    user_turns.append(
                        ParsedUserTurn(
                            seq=len(user_turns) + 1,
                            prompt_text=prompt,
                            started_at=started_at,
                            line_no=line_no,
                            message_offset=len(seen_messages),
                        ),
                    )
                    is_user_turn = True

        for block in _content_blocks(message):
            is_error = block.get("is_error") is True
            if is_error:
                errors_count += 1
            if not is_user_turn:
                block_type = str(block.get("type", "unknown"))
                tool_use_id = _string(
                    block.get("tool_use_id") if block_type == "tool_result" else block.get("id"),
                )
                block_name = _string(block.get("name"))
                blocks_outside_user_turns.append(
                    ParsedBlock(
                        kind=block_type,
                        tool_use_id=tool_use_id,
                        name=block_name,
                        is_error=is_error,
                    ),
                )

        if record_type != "assistant":
            continue
        message_id = _string(message.get("id"))
        message_offset = len(seen_messages)
        model = _string(message.get("model"))
        if model is not None:
            transcript_models.append(model)
            if model not in model_sequence:
                model_sequence.append(model)
        if message_id is not None:
            seen_messages.add(message_id)
            usage = _dict(message.get("usage"))
            usage_by_message[message_id] = _integer(
                usage.get("input_tokens"),
            ) + _integer(usage.get("output_tokens"))

        for block in _content_blocks(message):
            block_type = str(block.get("type", "unknown"))
            tool_use_id = _string(block.get("id"))
            block_name = _string(block.get("name"))
            if block_type != "tool_use":
                continue
            tools_count += 1
            kind = _TRIGGER_KINDS.get((block_name or "").casefold())
            if kind is None:
                continue
            tool_input = _dict(block.get("input"))
            events.append(
                ParsedEvent(
                    event_index=len(events),
                    line_no=line_no,
                    message_offset=message_offset,
                    kind=kind,
                    name=_event_name(kind, tool_input, block),
                    description=_string(tool_input.get("description")),
                    tool_use_id=tool_use_id,
                ),
            )

    tokens_total = sum(usage_by_message.values())

    return ParsedTranscript(
        root_session_id=root_session_id,
        agent_id=agent_id,
        agent_kind=agent_kind,
        parser_version=CURRENT_PARSER_VERSION,
        agent_type=_meta_string(meta, "agentType"),
        task_kind=_meta_string(meta, "taskKind"),
        team_name=_meta_string(meta, "teamName"),
        name=_meta_string(meta, "name"),
        skill_name=_meta_string(meta, "skillName"),
        model=_model(transcript_models),
        requested_model=_meta_string(meta, "model"),
        models=tuple(model_sequence),
        parent_tool_use_id=_meta_string(meta, "toolUseId"),
        spawn_depth=_meta_depth(meta),
        lines=len(physical_lines),
        messages_count=len(seen_messages),
        tokens_total=tokens_total,
        tools_count=tools_count,
        errors_count=errors_count,
        user_turns=tuple(user_turns),
        blocks_outside_user_turns=tuple(blocks_outside_user_turns),
        events=tuple(events),
        issues=tuple(issues),
        agent_meta=meta,
        root_metadata=root_metadata,
    )


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
