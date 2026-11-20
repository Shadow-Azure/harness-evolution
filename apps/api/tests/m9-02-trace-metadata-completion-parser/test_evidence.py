"""M9-02 agent-definition, Skill, and file-read evidence hooks."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, cast

from app.service.acquisition.normalize import ParsedTranscript, normalize_transcript
from app.service.acquisition.parsers import TracePayload
from app.service.acquisition.parsers.factory import TraceParserFactory

ROOT_ID = "50000000-0000-4000-8000-000000000001"
AGENT_ID = "a902000000000001"
DEFINITION = "You are a synthetic reviewer.\nOnly inspect synthetic inputs."
DEFINITION_WITH_SUFFIX = (
    DEFINITION + "\n\n## Subagent Permissions\nThis suffix must not enter the hash."
)


def jsonl(*records: object | str) -> str:
    """Encode deterministic JSONL test input."""
    return (
        "\n".join(
            record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
            for record in records
        )
        + "\n"
    )


def prompt_snapshot(body: str) -> dict[str, object]:
    """Build one injected agent definition snapshot."""
    return {
        "type": "prompt_snapshot",
        "sessionId": ROOT_ID,
        "agentId": AGENT_ID,
        "systemPrompt": [body],
    }


def api_request_shape(body: str) -> dict[str, object]:
    """Build one fallback API request shape record."""
    return {
        "type": "api-request-shape",
        "sessionId": ROOT_ID,
        "agentId": AGENT_ID,
        "system": [{"type": "text", "text": body}],
    }


def read_round_trip(
    *,
    path: str,
    content: str,
    start_line: int,
    num_lines: int,
    total_lines: int,
) -> tuple[dict[str, object], dict[str, object]]:
    """Build a Read call and its file result."""
    tool_id = "tool-read-1"
    assistant: dict[str, object] = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "agentId": AGENT_ID,
        "message": {
            "id": "message-1",
            "model": "claude-sonnet-4-5-20250929",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "Read",
                    "input": {"file_path": path},
                },
            ],
        },
    }
    result: dict[str, object] = {
        "type": "user",
        "sessionId": ROOT_ID,
        "agentId": AGENT_ID,
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": "read result"},
            ],
        },
        "toolUseResult": {
            "type": "text",
            "file": {
                "filePath": path,
                "content": content,
                "startLine": start_line,
                "numLines": num_lines,
                "totalLines": total_lines,
            },
        },
    }
    return assistant, result


def parse(
    content: str,
    *,
    agent_kind: Literal["main", "subagent"] = "subagent",
    meta: dict[str, object] | None = None,
) -> ParsedTranscript:
    """Normalize one evidence payload."""
    return normalize_transcript(
        content,
        root_session_id=ROOT_ID,
        agent_id=AGENT_ID if agent_kind == "subagent" else ROOT_ID,
        agent_kind=agent_kind,
        agent_meta=meta,
    )


def test_definition_hash_is_stable_across_tasks_and_excludes_common_suffix() -> None:
    """The same definition body hashes the same regardless of the delegated task."""
    first = parse(
        jsonl(
            prompt_snapshot(DEFINITION_WITH_SUFFIX),
            {
                "type": "user",
                "sessionId": ROOT_ID,
                "agentId": AGENT_ID,
                "message": {"content": "first task"},
            },
        ),
    )
    second = parse(
        jsonl(
            prompt_snapshot(DEFINITION_WITH_SUFFIX),
            {
                "type": "user",
                "sessionId": ROOT_ID,
                "agentId": AGENT_ID,
                "message": {"content": "a completely different task"},
            },
        ),
    )

    expected = hashlib.sha256(DEFINITION.encode("utf-8")).hexdigest()
    assert first.agent_definition_hash == expected
    assert second.agent_definition_hash == expected
    assert first.definition_source == "prompt_snapshot"


def test_different_definition_body_changes_hash() -> None:
    """A changed agent body produces a different revision evidence hash."""
    parsed = parse(jsonl(prompt_snapshot(DEFINITION + "\nOne more instruction.")))

    assert parsed.agent_definition_hash != hashlib.sha256(DEFINITION.encode()).hexdigest()


def test_api_request_shape_is_a_fallback_source() -> None:
    """Without prompt_snapshot, the api-request-shape body supplies the hash."""
    parsed = parse(jsonl(api_request_shape(DEFINITION_WITH_SUFFIX)))

    assert parsed.definition_source == "api_request_shape"
    assert parsed.agent_definition_hash == hashlib.sha256(DEFINITION.encode()).hexdigest()


def test_builtin_agent_has_no_definition_body_hash() -> None:
    """Builtin agents keep the builtin source and no body hash."""
    parsed = parse(
        jsonl(prompt_snapshot(DEFINITION_WITH_SUFFIX)),
        meta={
            "agentType": "Explore",
            "description": "builtin reviewer",
            "spawnDepth": 1,
            "isBuiltIn": True,
        },
    )

    assert parsed.definition_source == "builtin"
    assert parsed.agent_definition_hash is None
    assert [(item.kind, item.source, item.content_hash) for item in parsed.evidence] == [
        ("agent_definition", "builtin", None),
    ]


def test_skill_injection_records_path_and_body_hash_only() -> None:
    """An isMeta + sourceToolUseID injection yields path and hash, never the body."""
    payload = jsonl(
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "agentId": AGENT_ID,
            "message": {
                "id": "message-1",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-skill-1",
                        "name": "Skill",
                        "input": {"skill": "synthetic-review"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "agentId": AGENT_ID,
            "isMeta": True,
            "sourceToolUseID": "tool-skill-1",
            "message": {
                "content": (
                    "Base directory for this skill: /workspace/.claude/skills/review\n\n"
                    "# Synthetic review\n\n只检查合成输入。\n\n## Notes\nshared suffix"
                ),
            },
        },
    )

    parsed = parse(payload)
    evidence = [item for item in parsed.evidence if item.kind == "skill_definition"]

    assert len(evidence) == 1
    assert evidence[0].tool_use_id == "tool-skill-1"
    assert evidence[0].name == "synthetic-review"
    assert evidence[0].source_path == "/workspace/.claude/skills/review"
    assert evidence[0].content_hash is not None
    assert "# Synthetic review" not in repr(parsed)
    assert "只检查合成输入" not in repr(parsed)


def test_complete_read_records_range_and_content_hash() -> None:
    """A complete Read keeps path, 1-based range, completeness, and body hash."""
    assistant, result = read_round_trip(
        path="/workspace/repository/src/app.py",
        content="print('synthetic')\n",
        start_line=1,
        num_lines=1,
        total_lines=1,
    )

    parsed = parse(jsonl(assistant, result))
    evidence = [item for item in parsed.evidence if item.kind == "file_read"]

    assert len(evidence) == 1
    assert evidence[0].source_path == "/workspace/repository/src/app.py"
    assert (evidence[0].start_line, evidence[0].end_line) == (1, 1)
    assert evidence[0].complete is True
    assert evidence[0].content_hash == hashlib.sha256(b"print('synthetic')\n").hexdigest()
    assert "print('synthetic')" not in repr(parsed)


def test_partial_read_marks_incomplete() -> None:
    """A ranged Read records complete=False and the actual line window."""
    assistant, result = read_round_trip(
        path="/workspace/repository/src/app.py",
        content="part one\npart two\n",
        start_line=2,
        num_lines=2,
        total_lines=10,
    )

    parsed = parse(jsonl(assistant, result))
    evidence = [item for item in parsed.evidence if item.kind == "file_read"]

    assert (evidence[0].start_line, evidence[0].end_line) == (2, 3)
    assert evidence[0].complete is False


def test_empty_complete_read_still_has_a_content_hash() -> None:
    """A complete empty file hashes the empty body instead of becoming unknown."""
    assistant, result = read_round_trip(
        path="/workspace/repository/src/empty.py",
        content="",
        start_line=1,
        num_lines=0,
        total_lines=0,
    )

    parsed = parse(jsonl(assistant, result))
    evidence = [item for item in parsed.evidence if item.kind == "file_read"]

    assert evidence[0].complete is True
    assert evidence[0].content_hash == hashlib.sha256(b"").hexdigest()


def test_edit_records_original_file_hash() -> None:
    """An Edit result records the original file identity without the patch text."""
    payload = jsonl(
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "agentId": AGENT_ID,
            "message": {
                "id": "message-1",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-edit-1",
                        "name": "Edit",
                        "input": {"file_path": "/workspace/repository/src/app.py"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "agentId": AGENT_ID,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool-edit-1", "content": "ok"},
                ],
            },
            "toolUseResult": {
                "type": "update",
                "filePath": "/workspace/repository/src/app.py",
                "originalFile": "print('old')\n",
                "oldString": "old",
                "newString": "new",
            },
        },
    )

    parsed = parse(payload)
    evidence = [item for item in parsed.evidence if item.kind == "file_read"]

    assert len(evidence) == 1
    assert evidence[0].source_path == "/workspace/repository/src/app.py"
    assert evidence[0].complete is True
    assert evidence[0].content_hash == hashlib.sha256(b"print('old')\n").hexdigest()
    assert "print('old')" not in repr(parsed)


def test_extract_evidence_hook_matches_normalized_evidence() -> None:
    """The runtime hook returns the same identities as normalization."""
    assistant, result = read_round_trip(
        path="/workspace/repository/src/app.py",
        content="synthetic\n",
        start_line=1,
        num_lines=1,
        total_lines=1,
    )
    payload = TracePayload(
        content=jsonl(assistant, result),
        root_session_id=ROOT_ID,
        agent_id=AGENT_ID,
        agent_kind="subagent",
        runtime_key="claude-code",
    )

    evidence = TraceParserFactory.for_payload("claude-code", payload).extract_evidence(payload)

    assert [item.kind for item in evidence] == ["file_read"]
    assert cast(str, evidence[0].content_hash) == hashlib.sha256(b"synthetic\n").hexdigest()
