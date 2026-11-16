"""Runtime-agnostic JSONL parsing template and shared parse values."""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import ClassVar, Literal, cast

from app.utils.time import as_shanghai

ExecutionOutcome = Literal["completed", "interrupted", "failed", "legacy_unknown"]
EndReason = Literal[
    "end_turn",
    "tool_use_open",
    "missing_report",
    "external_failed",
    "external_interrupted",
]
DefinitionSource = Literal["prompt_snapshot", "api_request_shape", "builtin", "unknown"]
ModelEvidence = Literal["reported", "requested_only", "unknown"]


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
    definition_hash: str | None = None


@dataclass(frozen=True, slots=True)
class RootMetadata:
    """Root metadata copied from the main payload rather than inferred."""

    cwd: str | None = None
    git_branch: str | None = None
    cli_version: str | None = None
    entrypoint: str | None = None


@dataclass(frozen=True, slots=True)
class TracePayload:
    """One raw payload and the runtime identity that owns its parser."""

    content: str
    root_session_id: str
    agent_id: str
    agent_kind: Literal["main", "subagent"]
    runtime_key: str = "claude-code"
    agent_meta: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AgentMetaFacts:
    """Provider-specific metadata projected onto runtime-agnostic fields."""

    agent_type: str | None = None
    task_kind: str | None = None
    team_name: str | None = None
    name: str | None = None
    skill_name: str | None = None
    requested_model: str | None = None
    picked_effort_model: str | None = None
    is_builtin: bool | None = None
    finished: bool | None = None
    parent_tool_use_id: str | None = None
    parent_agent_id: str | None = None
    spawn_depth: int = 0


@dataclass(frozen=True, slots=True)
class TraceEvidence:
    """One evidence identity that never contains provider source text."""

    kind: Literal["agent_definition", "skill_definition", "file_read"]
    tool_use_id: str | None = None
    source_path: str | None = None
    content_hash: str | None = None
    name: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    complete: bool | None = None
    source: DefinitionSource | None = None


@dataclass(frozen=True, slots=True)
class ParsedTranscript:
    """Derived transcript statistics and anchors without message detail."""

    root_session_id: str
    agent_id: str
    agent_kind: Literal["main", "subagent"]
    runtime_key: str
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
    started_at: datetime | None
    ended_at: datetime | None
    ended_with_assistant: bool
    fatal_error_unrecovered: bool
    parent_agent_id: str | None = None
    reported_model: str | None = None
    model_evidence: ModelEvidence = "unknown"
    execution_outcome: ExecutionOutcome = "legacy_unknown"
    end_reason: EndReason | None = None
    agent_definition_hash: str | None = None
    definition_source: DefinitionSource | None = None
    evidence: tuple[TraceEvidence, ...] = ()

    def agent_meta_dict(self) -> dict[str, object]:
        """Return a detached JSON-compatible copy of provider metadata."""
        return cast(dict[str, object], _thaw_json(self.agent_meta))


@dataclass(slots=True)
class ParseContext:
    """Mutable state shared by one parser's record handlers and finalizer."""

    payload: TracePayload
    facts: AgentMetaFacts
    physical_lines: tuple[str, ...]
    issues: list[ParsedIssue] = field(default_factory=list)
    user_turns: list[ParsedUserTurn] = field(default_factory=list)
    blocks_outside_user_turns: list[ParsedBlock] = field(default_factory=list)
    events: list[ParsedEvent] = field(default_factory=list)
    seen_messages: set[str] = field(default_factory=set)
    usage_by_message: dict[str, int] = field(default_factory=dict)
    transcript_models: list[str] = field(default_factory=list)
    model_sequence: list[str] = field(default_factory=list)
    root_metadata: RootMetadata = field(default_factory=RootMetadata)
    observed_timestamps: list[datetime] = field(default_factory=list)
    tools_count: int = 0
    errors_count: int = 0
    ended_with_assistant: bool = False
    fatal_error_unrecovered: bool = False
    last_stop_reason: str | None = None
    open_tool_uses: dict[str, int] = field(default_factory=dict)
    tool_inputs: dict[str, tuple[str | None, dict[str, object]]] = field(default_factory=dict)
    evidence: list[TraceEvidence] = field(default_factory=list)
    agent_definition_hash: str | None = None
    definition_source: DefinitionSource | None = None
    task_pending: int = 0
    task_in_progress: int = 0

    def issue(self, line_no: int, code: str, message: str) -> None:
        """Record one stable issue for the current payload identity."""
        self.issues.append(
            ParsedIssue(
                session_id=self.payload.root_session_id,
                agent_id=self.payload.agent_id,
                line_no=line_no,
                code=code,
                message=message,
            ),
        )

    def observe_timestamp(self, value: object) -> datetime | None:
        """Parse, normalize, and remember one record timestamp."""
        timestamp = _timestamp(value)
        if timestamp is not None:
            self.observed_timestamps.append(timestamp)
        return timestamp

    def record_root_metadata(
        self,
        *,
        cwd: object = None,
        git_branch: object = None,
        cli_version: object = None,
        entrypoint: object = None,
    ) -> None:
        """Keep the latest non-empty root metadata from the main transcript."""
        current = self.root_metadata
        self.root_metadata = RootMetadata(
            cwd=_string(cwd) or current.cwd,
            git_branch=_string(git_branch) or current.git_branch,
            cli_version=_string(cli_version) or current.cli_version,
            entrypoint=_string(entrypoint) or current.entrypoint,
        )

    def record_user_turn(
        self,
        prompt: str,
        started_at: datetime | None,
        line_no: int,
    ) -> bool:
        """Append one user turn when its timestamp is usable."""
        if started_at is None:
            self.issue(
                line_no,
                "MISSING_USER_TURN_TIMESTAMP",
                "User turn timestamp is missing or invalid",
            )
            return False
        self.user_turns.append(
            ParsedUserTurn(
                seq=len(self.user_turns) + 1,
                prompt_text=prompt,
                started_at=started_at,
                line_no=line_no,
                message_offset=len(self.seen_messages),
            ),
        )
        return True

    def mark_user_input(self) -> None:
        """Reset the terminal-shape flag after any user-facing record."""
        self.ended_with_assistant = False

    def mark_assistant_record(
        self,
        *,
        fatal_error_unrecovered: bool,
        stop_reason: str | None = None,
    ) -> None:
        """Remember the latest assistant record and its explicit stop reason."""
        self.ended_with_assistant = True
        self.fatal_error_unrecovered = fatal_error_unrecovered
        self.last_stop_reason = stop_reason

    def remember_tool_use(
        self,
        tool_use_id: str | None,
        *,
        name: str | None,
        tool_input: Mapping[str, object] | None,
        line_no: int,
    ) -> None:
        """Retain one pending tool call identity without its source text."""
        if tool_use_id is None:
            return
        self.tool_inputs[tool_use_id] = (name, dict(tool_input or {}))
        self.open_tool_uses[tool_use_id] = line_no

    def record_tool_result(self, tool_use_id: str | None) -> None:
        """Close one pending tool call when its result arrives."""
        if tool_use_id is None:
            return
        self.open_tool_uses.pop(tool_use_id, None)

    def record_task_snapshot(self, *, pending: int, in_progress: int) -> None:
        """Keep the latest bounded task snapshot counts."""
        self.task_pending = max(0, pending)
        self.task_in_progress = max(0, in_progress)

    def add_evidence(self, evidence: TraceEvidence) -> None:
        """Append one privacy-safe evidence identity."""
        self.evidence.append(evidence)

    def set_agent_definition(
        self,
        *,
        content_hash: str | None,
        source: DefinitionSource,
    ) -> None:
        """Keep the strongest agent-definition evidence seen so far."""
        if self.definition_source in {"prompt_snapshot", "builtin"}:
            return
        if content_hash is None and source != "builtin":
            return
        self.agent_definition_hash = content_hash
        self.definition_source = source

    def record_block(
        self,
        *,
        kind: str,
        tool_use_id: str | None,
        name: str | None,
        is_error: bool,
        outside_user_turn: bool,
    ) -> None:
        """Count errors and retain only non-user content-block identity."""
        if is_error:
            self.errors_count += 1
        if not outside_user_turn:
            return
        self.blocks_outside_user_turns.append(
            ParsedBlock(
                kind=kind,
                tool_use_id=tool_use_id,
                name=name,
                is_error=is_error,
            ),
        )

    def record_assistant_message(
        self,
        *,
        message_id: str | None,
        model: str | None,
        usage: Mapping[str, object],
    ) -> int:
        """Deduplicate one assistant message and return its pre-insert offset."""
        message_offset = len(self.seen_messages)
        if model is not None:
            self.transcript_models.append(model)
            if model not in self.model_sequence:
                self.model_sequence.append(model)
        if message_id is None:
            return message_offset
        self.seen_messages.add(message_id)
        self.usage_by_message[message_id] = _integer(usage.get("input_tokens")) + _integer(
            usage.get("output_tokens"),
        )
        return message_offset

    def record_tool_use(
        self,
        *,
        line_no: int,
        message_offset: int,
        tool_use_id: str | None,
        name: str | None,
        trigger_kind: Literal["skill", "agent", "workflow"] | None,
        description: str | None,
        tool_input: Mapping[str, object] | None = None,
    ) -> None:
        """Count a tool call and retain a trigger event when recognized."""
        self.tools_count += 1
        self.remember_tool_use(
            tool_use_id,
            name=name,
            tool_input=tool_input,
            line_no=line_no,
        )
        if trigger_kind is None:
            return
        self.events.append(
            ParsedEvent(
                event_index=len(self.events),
                line_no=line_no,
                message_offset=message_offset,
                kind=trigger_kind,
                name=name,
                description=description,
                tool_use_id=tool_use_id,
            ),
        )


class BaseTraceParser(ABC):
    """Template method parser owning framing, issue safety, counts, and finalize."""

    runtime_key: ClassVar[str]
    parser_version: ClassVar[int]

    def normalize(self, payload: TracePayload) -> ParsedTranscript:
        """Normalize one payload without retaining message or content detail."""
        meta = payload.agent_meta or {}
        ctx = ParseContext(
            payload=payload,
            facts=self.parse_agent_meta(meta),
            physical_lines=self.iter_lines(payload.content),
        )
        for code, message in self.metadata_warnings(meta):
            ctx.issue(0, code, message)
        for line_no, line in enumerate(ctx.physical_lines, start=1):
            if not line.strip():
                continue
            record = self.decode_record(line, ctx, line_no)
            if record is not None:
                self.consume_record(record, ctx, line_no)
        return self.finalize(ctx)

    def iter_lines(self, content: str) -> tuple[str, ...]:
        """Split JSONL framing on LF/CRLF while preserving Unicode separators."""
        return _physical_lines(content)

    def decode_record(
        self,
        line: str,
        ctx: ParseContext,
        line_no: int,
    ) -> dict[str, object] | None:
        """Decode one line into an object or a stable, sanitized issue."""
        try:
            raw = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError):
            ctx.issue(line_no, "INVALID_JSONL_LINE", "JSONL line could not be parsed")
            return None
        if not isinstance(raw, dict):
            ctx.issue(
                line_no,
                "INVALID_TRANSCRIPT_RECORD",
                "JSONL record is not an object",
            )
            return None
        if not raw:
            return None
        return cast(dict[str, object], raw)

    def finalize(self, ctx: ParseContext) -> ParsedTranscript:
        """Build the runtime-agnostic result from accumulated context."""
        payload = ctx.payload
        reported_model = _most_frequent_model(ctx.transcript_models)
        execution_outcome, end_reason = _execution_state(ctx)
        _append_completion_issues(ctx, end_reason=end_reason)
        if _model_conflict(ctx.facts.requested_model, reported_model):
            ctx.issue(
                0,
                "MODEL_EVIDENCE_CONFLICT",
                "Requested and reported models disagree; both were kept separately",
            )
        return ParsedTranscript(
            root_session_id=payload.root_session_id,
            agent_id=payload.agent_id,
            agent_kind=payload.agent_kind,
            runtime_key=self.runtime_key,
            parser_version=self.parser_version,
            agent_type=ctx.facts.agent_type,
            task_kind=ctx.facts.task_kind,
            team_name=ctx.facts.team_name,
            name=ctx.facts.name,
            skill_name=ctx.facts.skill_name,
            model=reported_model,
            requested_model=ctx.facts.requested_model,
            models=tuple(ctx.model_sequence),
            parent_tool_use_id=ctx.facts.parent_tool_use_id,
            parent_agent_id=ctx.facts.parent_agent_id,
            spawn_depth=ctx.facts.spawn_depth,
            lines=len(ctx.physical_lines),
            messages_count=len(ctx.seen_messages),
            tokens_total=sum(ctx.usage_by_message.values()),
            tools_count=ctx.tools_count,
            errors_count=ctx.errors_count,
            user_turns=tuple(ctx.user_turns),
            blocks_outside_user_turns=tuple(ctx.blocks_outside_user_turns),
            events=tuple(ctx.events),
            issues=tuple(ctx.issues),
            agent_meta=cast(
                Mapping[str, object],
                _freeze_json(dict(payload.agent_meta or {})),
            ),
            root_metadata=ctx.root_metadata,
            started_at=min(ctx.observed_timestamps, default=None),
            ended_at=max(ctx.observed_timestamps, default=None),
            ended_with_assistant=ctx.ended_with_assistant,
            fatal_error_unrecovered=ctx.fatal_error_unrecovered,
            reported_model=reported_model,
            model_evidence=_model_evidence(ctx.facts.requested_model, reported_model),
            execution_outcome=execution_outcome,
            end_reason=end_reason,
            agent_definition_hash=ctx.agent_definition_hash,
            definition_source=ctx.definition_source,
            evidence=tuple(ctx.evidence),
        )

    def metadata_warnings(
        self,
        meta: Mapping[str, object],
    ) -> tuple[tuple[str, str], ...]:
        """Return stable warnings for provider metadata that was sanitized."""
        return ()

    @abstractmethod
    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Interpret one decoded provider record into the shared context."""

    @abstractmethod
    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Project provider-specific agent metadata onto shared facts."""

    def extract_evidence(self, payload: TracePayload) -> tuple[TraceEvidence, ...]:
        """Return optional M9 evidence identities; base parsers own none yet."""
        return ()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject keys that normal JSON parsing would silently overwrite."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _physical_lines(content: str) -> tuple[str, ...]:
    """Split JSONL framing on LF/CRLF while preserving Unicode separators."""
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return tuple(line[:-1] if line.endswith("\r") else line for line in lines)


_COMMON_DEFINITION_SUFFIX = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"(?:subagent\s+permissions?|permission\s+notes?|agent\s+notes?|notes|token\s+budget)\b",
    re.IGNORECASE,
)


def normalize_definition_body(text: str) -> str | None:
    """Strip runtime-added common suffixes before hashing a definition body."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    lines = normalized.split("\n")
    cut = len(lines)
    for index, line in enumerate(lines):
        if _COMMON_DEFINITION_SUFFIX.match(line):
            cut = index
            break
    body = "\n".join(lines[:cut]).rstrip()
    return body or None


def definition_hash(text: str) -> str | None:
    """Hash a normalized definition body without retaining its source text."""
    body = normalize_definition_body(text)
    if body is None:
        return None
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _execution_state(ctx: ParseContext) -> tuple[ExecutionOutcome, EndReason | None]:
    """Derive completion only from explicit provider evidence."""
    if ctx.fatal_error_unrecovered:
        return "failed", "external_failed"
    reason = ctx.last_stop_reason
    if reason == "end_turn":
        return "completed", "end_turn"
    if reason in {"interrupted", "user_interrupt"}:
        return "interrupted", "external_interrupted"
    if reason == "tool_use":
        if ctx.open_tool_uses:
            return "interrupted", "tool_use_open"
        return "interrupted", "missing_report"
    return "legacy_unknown", None


def _append_completion_issues(
    ctx: ParseContext,
    *,
    end_reason: EndReason | None,
) -> None:
    """Expose stable completion diagnostics without changing the outcome."""
    if end_reason == "tool_use_open":
        ctx.issue(
            max(ctx.open_tool_uses.values(), default=0),
            "TOOL_USE_OPEN",
            f"{len(ctx.open_tool_uses)} tool call(s) did not return before the transcript ended",
        )
    elif end_reason == "missing_report":
        ctx.issue(
            0,
            "MISSING_FINAL_REPORT",
            "Transcript ended without an end_turn final report",
        )
    if ctx.task_pending or ctx.task_in_progress:
        ctx.issue(
            0,
            "TASK_SNAPSHOT_PENDING",
            "Final task snapshot still has "
            f"{ctx.task_pending} pending and {ctx.task_in_progress} in-progress item(s)",
        )


def _model_evidence(requested: str | None, reported: str | None) -> ModelEvidence:
    """Describe which independent model source is available."""
    if reported is not None:
        return "reported"
    if requested is not None:
        return "requested_only"
    return "unknown"


def _model_conflict(requested: str | None, reported: str | None) -> bool:
    """Warn only when two concrete model identities disagree."""
    if requested is None or reported is None:
        return False
    left = requested.casefold()
    right = reported.casefold()
    if left == right or left.startswith(right) or right.startswith(left):
        return False
    return "-" in left and "-" in right


def _dict(value: object) -> dict[str, object]:
    """Narrow an arbitrary JSON object without exposing it elsewhere."""
    return value if isinstance(value, dict) else {}


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


def _content_blocks(message: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Return object-shaped content blocks from one message."""
    content = message.get("content")
    if not isinstance(content, list):
        return ()
    return tuple(block for block in content if isinstance(block, dict))


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


def _most_frequent_model(models: list[str]) -> str | None:
    """Choose the most frequent model, with first occurrence breaking ties."""
    if not models:
        return None
    counts = Counter(models)
    highest = max(counts.values())
    return next(model for model in models if counts[model] == highest)


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
