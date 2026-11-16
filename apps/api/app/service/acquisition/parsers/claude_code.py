"""Claude Code trace parser: the only production runtime today."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from app.service.acquisition.parsers._claude_meta import unknown_metadata_fields
from app.service.acquisition.parsers.base import (
    AgentMetaFacts,
    BaseTraceParser,
    DefinitionSource,
    ParseContext,
    TraceEvidence,
    TracePayload,
    _content_blocks,
    _dict,
    _string,
    _text_from_content,
    _timestamp,
    definition_hash,
    normalize_definition_body,
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
_SKILL_PATH = re.compile(
    r"(?:base directory for this skill|skill path|skill file)\s*:\s*(.+)",
    re.IGNORECASE,
)
_TASK_STATUS_PENDING = frozenset({"pending", "queued", "todo"})
_TASK_STATUS_IN_PROGRESS = frozenset({"in_progress", "in-progress", "running", "started"})
_KIND_VERSION_KEYS: dict[str, tuple[str, ...]] = {
    "skill": ("skillVersion", "skill_version"),
    "agent": ("agentVersion", "agent_version"),
    "workflow": (),
}
_GENERIC_VERSION_KEYS = ("objectVersion", "object_version", "version")
_TAG_KEYS = ("tag", "objectTag", "object_tag")
_LISTING_DIGEST = re.compile(r"(?:digest|hash)\s*[:=]\s*([0-9a-fA-F]{16})\b")
_OPAQUE_DIGEST = re.compile(r"^[0-9a-fA-F]{16}$")


def _bounded_version(value: object) -> str | None:
    """Read an explicit object version without guessing or exceeding the column."""
    text = _string(value)
    if text is None:
        return None
    return text.strip()[:64] or None


def _object_version(
    kind: Literal["skill", "agent", "workflow"],
    tool_input: dict[str, object],
) -> str | None:
    """Read explicit version metadata for one trigger kind."""
    for key in (*_KIND_VERSION_KEYS[kind], *_GENERIC_VERSION_KEYS):
        version = _bounded_version(tool_input.get(key))
        if version is not None:
            return version
    return None


def _object_tag(tool_input: dict[str, object]) -> str | None:
    """Read an explicit object tag, if the provider supplied one."""
    for key in _TAG_KEYS:
        tag = _bounded_version(tool_input.get(key))
        if tag is not None:
            return tag
    return None


def _listing_digest(value: object) -> str | None:
    """Read one opaque 16-hex Skill listing digest without interpreting it."""
    text = _string(value)
    if text is None:
        return None
    candidate = text.strip()
    if _OPAQUE_DIGEST.fullmatch(candidate):
        return candidate.lower()
    match = _LISTING_DIGEST.search(candidate)
    return match.group(1).lower() if match is not None else None


def _skill_listing_digests(attachment: dict[str, object]) -> dict[str, str]:
    """Extract name -> opaque digest pairs from one Skill listing attachment."""
    if attachment.get("type") != "skill_listing":
        return {}
    raw_names = attachment.get("names")
    names = (
        [name for name in raw_names if isinstance(name, str) and name.strip()]
        if isinstance(raw_names, list)
        else []
    )
    digests: dict[str, str] = {}
    top_level = _listing_digest(attachment.get("digest"))
    if top_level is not None and len(names) == 1:
        digests[names[0]] = top_level
    digests_value = attachment.get("digests")
    if isinstance(digests_value, dict):
        for name, value in digests_value.items():
            if not isinstance(name, str) or not name.strip():
                continue
            digest = _listing_digest(value)
            if digest is not None:
                digests[name] = digest
    elif isinstance(digests_value, list):
        for name, value in zip(names, digests_value, strict=False):
            digest = _listing_digest(value)
            if digest is not None:
                digests[name] = digest
    skills = attachment.get("skills")
    if isinstance(skills, list):
        for item in skills:
            if not isinstance(item, dict):
                continue
            name = _string(item.get("name"))
            digest = _listing_digest(item.get("digest"))
            if name is not None and digest is not None:
                digests[name] = digest
    content = _string(attachment.get("content"))
    if content is not None:
        current: str | None = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                current = stripped[2:].split(":", 1)[0].strip() or None
            if current is not None:
                digest = _listing_digest(line)
                if digest is not None:
                    digests[current] = digest
    return digests


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


def _meta_bool(meta: Mapping[str, object], key: str) -> bool | None:
    """Read one optional metadata boolean without coercion."""
    value = meta.get(key)
    return value if isinstance(value, bool) else None


def _meta_depth(meta: Mapping[str, object]) -> int:
    """Read a non-negative spawn depth."""
    value = meta.get("spawnDepth")
    return value if isinstance(value, int) and value >= 0 else 0


def _stop_reason(record: dict[str, object], message: dict[str, object]) -> str | None:
    """Read the explicit stop reason from the record or its assistant message."""
    return _string(message.get("stop_reason")) or _string(record.get("stop_reason"))


def _definition_body(record: dict[str, object], record_type: object) -> str | None:
    """Read the injected agent definition body from either snapshot shape."""
    if record_type == "prompt_snapshot":
        system = record.get("systemPrompt")
    elif record_type in {"api-request-shape", "api_request_shape"}:
        system = record.get("system")
    else:
        return None
    if isinstance(system, str):
        return normalize_definition_body(system)
    if isinstance(system, list):
        for item in system:
            if isinstance(item, str):
                return normalize_definition_body(item)
            if isinstance(item, dict):
                text = _string(item.get("text"))
                if text is not None:
                    return normalize_definition_body(text)
    return None


def _skill_injection(record: dict[str, object]) -> tuple[str, str | None, str | None] | None:
    """Read one Skill body injection keyed by its Skill tool-use identity."""
    if record.get("isMeta") is not True:
        return None
    tool_use_id = _string(record.get("sourceToolUseID"))
    if tool_use_id is None:
        return None
    message = _dict(record.get("message"))
    text = _text_from_content(message.get("content")) or _string(record.get("content"))
    if text is None:
        return None
    path: str | None = None
    body = text
    match = _SKILL_PATH.search(text)
    if match is not None:
        path = _string(match.group(1))
        if path is not None:
            path = path.strip().strip("`\"'")
            body = text[match.end() :]
    body_hash = definition_hash(body)
    return tool_use_id, path, body_hash


def _task_counts(record: dict[str, object]) -> tuple[int, int] | None:
    """Count a final task snapshot without retaining task text."""
    tasks: object = record.get("tasks")
    if not isinstance(tasks, list):
        snapshot = _dict(record.get("taskSnapshot"))
        tasks = snapshot.get("tasks")
    if not isinstance(tasks, list):
        result = _dict(record.get("toolUseResult"))
        task = _dict(result.get("task"))
        tasks = [task] if task else None
    if not isinstance(tasks, list):
        return None
    pending = 0
    in_progress = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = _string(task.get("status"))
        if status is None:
            continue
        normalized = status.casefold().replace(" ", "_")
        if normalized in _TASK_STATUS_PENDING:
            pending += 1
        elif normalized in _TASK_STATUS_IN_PROGRESS:
            in_progress += 1
    return pending, in_progress


def _read_line_range(
    result_file: dict[str, object],
) -> tuple[int | None, int | None, bool | None]:
    """Return a 1-based file range start/end and whether the read was complete."""
    start = result_file.get("startLine")
    count = result_file.get("numLines")
    total = result_file.get("totalLines")
    start_line = start if isinstance(start, int) and start >= 1 else None
    line_count = count if isinstance(count, int) and count >= 0 else None
    total_lines = total if isinstance(total, int) and total >= 0 else None
    end_line = (
        start_line + line_count - 1
        if start_line is not None and line_count is not None and line_count > 0
        else None
    )
    complete: bool | None = None
    if start_line is not None and total_lines is not None:
        complete = start_line <= 1 and line_count is not None and line_count >= total_lines
    return start_line, end_line, complete


def _text(value: object) -> str | None:
    """Return a string body, preserving a legitimate empty file."""
    return value if isinstance(value, str) else None


def _sha256(text: str | None) -> str | None:
    """Hash one provider body byte-for-byte without retaining it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None


def _file_evidence(
    tool_name: str | None,
    tool_input: dict[str, object],
    result: dict[str, object],
) -> TraceEvidence | None:
    """Extract a privacy-safe file identity from one Read or Edit result."""
    if tool_name not in {"Read", "Edit", "Bash"}:
        return None
    result_file = _dict(result.get("file"))
    path = (
        _string(result_file.get("filePath"))
        or _string(result.get("filePath"))
        or _string(tool_input.get("file_path"))
    )
    if tool_name == "Edit":
        original = _text(result.get("originalFile"))
        if path is None and original is None:
            return None
        return TraceEvidence(
            kind="file_read",
            source_path=path,
            content_hash=_sha256(original),
            name=tool_name,
            complete=original is not None,
        )
    content = _text(result_file.get("content"))
    if content is None:
        content = _text(result.get("content"))
    if content is None and tool_name == "Bash":
        return None
    if path is None and content is None:
        return None
    start_line, end_line, complete = _read_line_range(result_file)
    return TraceEvidence(
        kind="file_read",
        source_path=path,
        content_hash=_sha256(content),
        name=tool_name,
        start_line=start_line,
        end_line=end_line,
        complete=complete,
    )


@TraceParserFactory.register
class ClaudeCodeTraceParser(BaseTraceParser):
    """Interpret Claude Code JSONL records and closed subagent metadata."""

    runtime_key = "claude-code"
    parser_version = 4

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Accumulate one Claude Code record into shared parse state."""
        payload = ctx.payload
        record_type = record.get("type")
        message = _dict(record.get("message"))
        ctx.observe_timestamp(record.get("timestamp"))

        if record_type == "assistant":
            ctx.mark_assistant_record(
                fatal_error_unrecovered=record.get("isApiErrorMessage") is True,
                stop_reason=_stop_reason(record, message),
            )
        elif record_type == "task_reminder":
            counts = _task_counts(record)
            if counts is not None:
                ctx.record_task_snapshot(pending=counts[0], in_progress=counts[1])
            stop_reason = _string(record.get("stop_reason"))
            if stop_reason is not None:
                ctx.last_stop_reason = stop_reason
        elif record_type in {"prompt_snapshot", "api-request-shape", "api_request_shape"}:
            self._record_agent_definition(record, record_type, ctx)

        attribution = _string(record.get("attributionSkill"))
        if attribution is not None:
            ctx.attribution_skills.append(attribution.strip()[:255])
        if record_type == "attachment":
            attachment = _dict(record.get("attachment"))
            if attachment:
                ctx.skill_digests.update(_skill_listing_digests(attachment))

        if payload.agent_kind == "main":
            ctx.record_root_metadata(
                cwd=record.get("cwd"),
                git_branch=record.get("gitBranch"),
                cli_version=record.get("version"),
                entrypoint=record.get("entrypoint"),
            )

        injection = _skill_injection(record) if record_type == "user" else None
        if injection is not None:
            skill_tool_use_id, skill_path, skill_hash = injection
            skill_name = ctx.tool_inputs.get(skill_tool_use_id, (None, {}))[1].get("skill")
            ctx.add_evidence(
                TraceEvidence(
                    kind="skill_definition",
                    tool_use_id=skill_tool_use_id,
                    source_path=skill_path,
                    content_hash=skill_hash,
                    name=_string(skill_name),
                ),
            )

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

        tool_results: list[str] = []
        for block in _content_blocks(message):
            block_type = str(block.get("type", "unknown"))
            tool_use_id = _string(block.get("tool_use_id" if block_type == "tool_result" else "id"))
            if block_type == "tool_result" and tool_use_id is not None:
                tool_results.append(tool_use_id)
                ctx.record_tool_result(tool_use_id)
            ctx.record_block(
                kind=block_type,
                tool_use_id=tool_use_id,
                name=_string(block.get("name")),
                is_error=block.get("is_error") is True,
                outside_user_turn=not is_user_turn,
            )

        if tool_results:
            result = _dict(record.get("toolUseResult"))
            if result:
                for tool_use_id in tool_results:
                    tool_name, tool_input = ctx.tool_inputs.get(tool_use_id, (None, {}))
                    evidence = _file_evidence(tool_name, tool_input, result)
                    if evidence is not None:
                        ctx.add_evidence(evidence)

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
            object_version = _object_version(kind, tool_input) if kind is not None else None
            tag = _object_tag(tool_input) if kind is not None else None
            tag = tag or object_version
            ctx.record_tool_use(
                line_no=line_no,
                message_offset=message_offset,
                tool_use_id=_string(block.get("id")),
                name=_event_name(kind, tool_input, block) if kind is not None else block_name,
                trigger_kind=kind,
                description=_string(tool_input.get("description")),
                tool_input=tool_input,
                object_version=object_version,
                object_revision=f"tag:{tag}" if tag is not None else None,
                triggered_at=_timestamp(record.get("timestamp")),
            )

    def _record_agent_definition(
        self,
        record: dict[str, object],
        record_type: object,
        ctx: ParseContext,
    ) -> None:
        """Record the strong agent-definition evidence carried by subagent traces."""
        if ctx.facts.is_builtin is True:
            ctx.set_agent_definition(content_hash=None, source="builtin")
            ctx.add_evidence(
                TraceEvidence(
                    kind="agent_definition",
                    content_hash=None,
                    source="builtin",
                    name=ctx.facts.agent_type,
                ),
            )
            return
        body = _definition_body(record, record_type)
        if body is None:
            return
        source: DefinitionSource = (
            "prompt_snapshot" if record_type == "prompt_snapshot" else "api_request_shape"
        )
        digest = definition_hash(body)
        if digest is None:
            return
        ctx.set_agent_definition(content_hash=digest, source=source)
        ctx.add_evidence(
            TraceEvidence(
                kind="agent_definition",
                content_hash=digest,
                source=source,
                name=ctx.facts.agent_type,
            ),
        )

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Project Claude subagent metadata onto runtime-agnostic facts."""
        return AgentMetaFacts(
            agent_type=_meta_string(meta, "agentType"),
            task_kind=_meta_string(meta, "taskKind"),
            team_name=_meta_string(meta, "teamName"),
            name=_meta_string(meta, "name"),
            skill_name=_meta_string(meta, "skillName"),
            requested_model=_meta_string(meta, "model") or _meta_string(meta, "pickedEffortModel"),
            picked_effort_model=_meta_string(meta, "pickedEffortModel"),
            is_builtin=_meta_bool(meta, "isBuiltIn"),
            finished=_meta_bool(meta, "finished"),
            parent_tool_use_id=(
                _meta_string(meta, "toolUseId") or _meta_string(meta, "parentToolUseId")
            ),
            parent_agent_id=_meta_string(meta, "parentAgentId"),
            spawn_depth=_meta_depth(meta),
        )

    def metadata_warnings(
        self,
        meta: Mapping[str, object],
    ) -> tuple[tuple[str, str], ...]:
        """Report sanitized metadata keys without exposing their values."""
        fields = unknown_metadata_fields(meta)
        if not fields:
            return ()
        return (
            (
                "UNKNOWN_AGENT_METADATA",
                "Unknown agent metadata fields were sanitized: " + ", ".join(fields),
            ),
        )

    def extract_evidence(self, payload: TracePayload) -> tuple[TraceEvidence, ...]:
        """Return the M9 evidence identities discovered in one payload."""
        return self.normalize(payload).evidence
