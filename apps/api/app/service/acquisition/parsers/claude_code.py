"""Claude Code trace parser: the only production runtime today."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from app.service.acquisition.parsers.base import (
    AgentMetaFacts,
    BaseTraceParser,
    ParseContext,
    TraceEvidence,
    TracePayload,
    _content_blocks,
    _dict,
    _string,
    _text_from_content,
    _timestamp,
)
from app.service.acquisition.parsers.factory import TraceParserFactory

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


def _event_name(
    kind: Literal["skill", "agent", "workflow"],
    tool_input: dict[str, object],
    block: dict[str, object],
) -> str | None:
    """Resolve the user-facing trigger name from provider input."""
    if kind == "skill":
        return _string(tool_input.get("skill")) or _string(tool_input.get("name"))
    if kind == "agent":
        return _string(tool_input.get("subagent_type")) or _string(tool_input.get("name"))
    return _string(tool_input.get("name")) or _string(block.get("name"))


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


@TraceParserFactory.register
class ClaudeCodeTraceParser(BaseTraceParser):
    """Interpret Claude Code JSONL records and closed subagent metadata."""

    runtime_key = "claude-code"
    parser_version = 1

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Accumulate one Claude Code record into shared parse state."""
        payload = ctx.payload
        record_type = record.get("type")
        if record_type == "assistant":
            ctx.mark_assistant_record(
                fatal_error_unrecovered=record.get("isApiErrorMessage") is True,
            )
        ctx.observe_timestamp(record.get("timestamp"))

        if payload.agent_kind == "main":
            ctx.record_root_metadata(
                cwd=record.get("cwd"),
                git_branch=record.get("gitBranch"),
                cli_version=record.get("version"),
                entrypoint=record.get("entrypoint"),
            )

        message = _dict(record.get("message"))
        is_user_turn = False
        is_attachment_user_turn = False
        if (
            record_type == "user"
            and payload.agent_kind == "main"
            and record.get("isMeta") is not True
        ):
            prompt = _text_from_content(message.get("content"))
            if prompt is not None and not prompt.startswith(_CONTROL_PREFIXES):
                is_user_turn = ctx.record_user_turn(
                    prompt,
                    _timestamp(record.get("timestamp")),
                    line_no,
                )
        elif payload.agent_kind == "main" and record_type == "attachment":
            prompt, started_at = _attachment_prompt(record)
            if prompt is not None:
                is_attachment_user_turn = True
                is_user_turn = ctx.record_user_turn(prompt, started_at, line_no)

        if (record_type == "user" and record.get("isMeta") is not True) or (
            record_type == "attachment" and is_attachment_user_turn
        ):
            ctx.mark_user_input()

        for block in _content_blocks(message):
            block_type = str(block.get("type", "unknown"))
            if block_type == "tool_result":
                tool_use_id = _string(block.get("tool_use_id"))
            else:
                tool_use_id = _string(block.get("id"))
            ctx.record_block(
                kind=block_type,
                tool_use_id=tool_use_id,
                name=_string(block.get("name")),
                is_error=block.get("is_error") is True,
                outside_user_turn=not is_user_turn,
            )

        if record_type != "assistant":
            return
        message_offset = ctx.record_assistant_message(
            message_id=_string(message.get("id")),
            model=_string(message.get("model")),
            usage=_dict(message.get("usage")),
        )
        for block in _content_blocks(message):
            if block.get("type") != "tool_use":
                continue
            block_name = _string(block.get("name"))
            kind = _TRIGGER_KINDS.get((block_name or "").casefold())
            tool_input = _dict(block.get("input"))
            ctx.record_tool_use(
                line_no=line_no,
                message_offset=message_offset,
                tool_use_id=_string(block.get("id")),
                name=_event_name(kind, tool_input, block) if kind is not None else block_name,
                trigger_kind=kind,
                description=_string(tool_input.get("description")),
            )

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Project Claude subagent metadata onto runtime-agnostic facts."""
        return AgentMetaFacts(
            agent_type=_meta_string(meta, "agentType"),
            task_kind=_meta_string(meta, "taskKind"),
            team_name=_meta_string(meta, "teamName"),
            name=_meta_string(meta, "name"),
            skill_name=_meta_string(meta, "skillName"),
            requested_model=_meta_string(meta, "model"),
            parent_tool_use_id=(
                _meta_string(meta, "toolUseId") or _meta_string(meta, "parentToolUseId")
            ),
            parent_agent_id=_meta_string(meta, "parentAgentId"),
            spawn_depth=_meta_depth(meta),
        )

    def extract_evidence(self, payload: TracePayload) -> tuple[TraceEvidence, ...]:
        """Claude evidence hooks land in M9-02/M9-04; none are emitted yet."""
        return ()
