"""Pure JSONL normalization contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import DatabaseDialect, Settings
from app.fixture_corpus import load_fixture_corpus
from app.service.acquisition.local_sessions import normalize_local_sessions
from app.service.acquisition.normalize import (
    CURRENT_PARSER_VERSION,
    normalize_transcript,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CORPUS_PATH = REPOSITORY_ROOT / "fixtures" / "m2-synthetic" / "corpus.json"
ROOT_ID = "11111111-1111-4111-8111-111111111111"


def jsonl(*records: object | str) -> str:
    """Encode deterministic JSONL test input, including deliberate bad lines."""
    return (
        "\n".join(
            record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
            for record in records
        )
        + "\n"
    )


def mixed_transcript() -> str:
    """Exercise user, assistant, tool, attachment, and bad-line variants."""
    return jsonl(
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "timestamp": "2026-10-20T01:00:00Z",
            "cwd": "/workspace/example",
            "gitBranch": "main",
            "version": "1.2.3",
            "entrypoint": "cli",
            "message": {"content": "first prompt"},
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "isMeta": True,
            "message": {"content": "metadata prompt"},
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "message": {"content": "<system-reminder>ignore me</system-reminder>"},
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "timestamp": "2026-10-20T01:01:00Z",
            "message": {
                "content": [
                    {"type": "text", "text": "second prompt"},
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "timestamp": "2026-10-20T01:02:00Z",
            "message": {
                "id": "message-a",
                "model": "claude-a",
                "content": [
                    {"type": "thinking", "thinking": "THINKING_SECRET"},
                    {"type": "text", "text": "ASSISTANT_SECRET"},
                    {
                        "type": "tool_use",
                        "id": "tool-skill",
                        "name": "Skill",
                        "input": {
                            "skill": "review-skill",
                            "description": "Review the change",
                        },
                    },
                    {
                        "type": "tool_use",
                        "id": "tool-agent",
                        "name": "Agent",
                        "input": {
                            "description": "Explore files",
                            "subagent_type": "Explore",
                        },
                    },
                    {
                        "type": "server_tool_use",
                        "id": "server-tool",
                        "name": "WebSearch",
                    },
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "message": {
                "id": "message-a",
                "model": "claude-a",
                "content": [{"type": "text", "text": "REPEATED_SECRET"}],
                "usage": {"input_tokens": 999, "output_tokens": 999},
            },
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-agent",
                        "content": "TOOL_RESULT_SECRET",
                        "is_error": True,
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "message": {
                "id": "message-b",
                "model": "claude-b",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-workflow",
                        "name": "Workflow",
                        "input": {"name": "review-workflow"},
                    },
                ],
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        },
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "message": {
                "id": "message-c",
                "model": "claude-a",
                "content": [{"type": "text", "text": "LATEST_SECRET"}],
                "usage": {"input_tokens": 7, "output_tokens": 1},
            },
        },
        "{not-json}",
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "timestamp": "2026-10-20T01:03:00Z",
            "message": {"content": [{"type": "text", "text": "third prompt"}]},
        },
        {
            "type": "attachment",
            "sessionId": ROOT_ID,
            "timestamp": "2026-10-20T01:04:00Z",
            "attachment": {
                "origin": {"kind": "human"},
                "prompt": "attachment prompt",
            },
        },
        {
            "type": "attachment",
            "sessionId": ROOT_ID,
            "attachment": {
                "origin": {"kind": "peer"},
                "prompt": "peer prompt",
            },
        },
        {
            "type": "queue-operation",
            "sessionId": ROOT_ID,
            "message": {"content": "queue operation"},
        },
    )


def test_normalizes_mixed_transcript_without_persisting_message_detail() -> None:
    """All derived counts and anchors are deterministic and privacy-bounded."""
    parsed = normalize_transcript(
        mixed_transcript(),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert CURRENT_PARSER_VERSION == 1
    assert parsed.root_session_id == ROOT_ID
    assert parsed.agent_id == ROOT_ID
    assert parsed.lines == 14
    assert parsed.messages_count == 3
    assert parsed.tokens_total == 2011
    assert parsed.tools_count == 3
    assert parsed.errors_count == 1
    assert parsed.model == "claude-a"
    assert parsed.models == ("claude-a", "claude-b")
    assert parsed.root_metadata.cwd == "/workspace/example"
    assert parsed.root_metadata.git_branch == "main"
    assert parsed.root_metadata.cli_version == "1.2.3"
    assert parsed.root_metadata.entrypoint == "cli"

    assert [turn.seq for turn in parsed.user_turns] == [1, 2, 3, 4]
    assert [turn.prompt_text for turn in parsed.user_turns] == [
        "first prompt",
        "second prompt",
        "third prompt",
        "attachment prompt",
    ]
    assert [turn.line_no for turn in parsed.user_turns] == [1, 4, 11, 12]
    assert [turn.message_offset for turn in parsed.user_turns] == [0, 0, 3, 3]
    for turn in parsed.user_turns:
        assert turn.started_at is not None
        offset = turn.started_at.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 8 * 60 * 60

    assert [event.event_index for event in parsed.events] == [0, 1, 2]
    assert [(event.kind, event.line_no, event.message_offset) for event in parsed.events] == [
        ("skill", 5, 0),
        ("agent", 5, 0),
        ("workflow", 8, 1),
    ]
    assert [event.tool_use_id for event in parsed.events] == [
        "tool-skill",
        "tool-agent",
        "tool-workflow",
    ]

    assert len(parsed.issues) == 1
    issue = parsed.issues[0]
    assert issue.line_no == 10
    assert issue.code == "INVALID_JSONL_LINE"
    assert issue.session_id == ROOT_ID
    assert issue.agent_id == ROOT_ID

    rendered = repr(parsed)
    for secret in (
        "THINKING_SECRET",
        "ASSISTANT_SECRET",
        "REPEATED_SECRET",
        "TOOL_RESULT_SECRET",
        "LATEST_SECRET",
    ):
        assert secret not in rendered


def test_bad_line_does_not_abort_later_records() -> None:
    """A line-local parse failure preserves all later valid statistics."""
    payload = jsonl(
        '{"type":"assistant","message":',
        {
            "type": "assistant",
            "sessionId": ROOT_ID,
            "message": {
                "id": "after-bad",
                "model": "valid-model",
                "content": [],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        },
        {
            "type": "user",
            "sessionId": ROOT_ID,
            "timestamp": "2026-10-20T01:00:00Z",
            "message": {"content": "still parsed"},
        },
    )

    parsed = normalize_transcript(
        payload,
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.lines == 3
    assert parsed.messages_count == 1
    assert parsed.tokens_total == 3
    assert parsed.user_turns[0].prompt_text == "still parsed"
    assert parsed.issues[0].line_no == 1


def test_multi_model_tie_uses_first_seen_and_child_metadata() -> None:
    """Node model selection is stable while all models remain available."""
    payload = jsonl(
        {
            "type": "assistant",
            "message": {
                "id": "one",
                "model": "model-first",
                "content": [],
            },
        },
        {
            "type": "assistant",
            "message": {
                "id": "two",
                "model": "model-second",
                "content": [],
            },
        },
    )

    parsed = normalize_transcript(
        payload,
        root_session_id=ROOT_ID,
        agent_id="agent-child",
        agent_kind="subagent",
        agent_meta={
            "agentType": "Explore",
            "taskKind": "forked_skill",
            "teamName": "review-team",
            "name": "reviewer",
            "skillName": "review-skill",
            "model": "requested-model",
            "spawnDepth": 2,
            "toolUseId": "tool-agent",
        },
    )

    assert parsed.model == "model-first"
    assert parsed.models == ("model-first", "model-second")
    assert parsed.requested_model == "requested-model"
    assert parsed.agent_type == "Explore"
    assert parsed.task_kind == "forked_skill"
    assert parsed.team_name == "review-team"
    assert parsed.name == "reviewer"
    assert parsed.skill_name == "review-skill"
    assert parsed.spawn_depth == 2
    assert parsed.parent_tool_use_id == "tool-agent"
    assert parsed.user_turns == ()


def test_preserves_agent_meta_as_an_immutable_copy() -> None:
    """Later tree assembly can persist provider metadata without aliasing input."""
    custom_provider_field: dict[str, list[str]] = {"labels": ["one", "two"]}
    meta: dict[str, object] = {
        "agentType": "Explore",
        "customProviderField": custom_provider_field,
    }

    parsed = normalize_transcript(
        jsonl(
            {
                "type": "assistant",
                "message": {
                    "id": "metadata-message",
                    "model": "metadata-model",
                    "content": [],
                },
            },
        ),
        root_session_id=ROOT_ID,
        agent_id="agent-meta",
        agent_kind="subagent",
        agent_meta=meta,
    )

    assert parsed.agent_meta["agentType"] == "Explore"
    assert parsed.agent_meta_dict()["customProviderField"] == {
        "labels": ["one", "two"],
    }

    meta["agentType"] = "Mutated"
    custom_provider_field["labels"].append("three")
    assert parsed.agent_meta["agentType"] == "Explore"
    assert parsed.agent_meta_dict()["customProviderField"] == {
        "labels": ["one", "two"],
    }


def test_records_only_blocks_outside_user_turns() -> None:
    """User prompt text never becomes a structural content block."""
    parsed = normalize_transcript(
        jsonl(
            {
                "type": "user",
                "timestamp": "2026-10-20T01:00:00Z",
                "message": {
                    "content": [{"type": "text", "text": "USER_TURN_SECRET"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "block-message",
                    "model": "block-model",
                    "content": [{"type": "text", "text": "ASSISTANT_SECRET"}],
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "content": "TOOL_RESULT_SECRET",
                        },
                    ],
                },
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert not hasattr(parsed, "blocks")
    assert [
        (block.kind, block.tool_use_id, block.name, block.is_error)
        for block in parsed.blocks_outside_user_turns
    ] == [
        ("text", None, None, False),
        ("tool_result", "tool-1", None, False),
    ]
    rendered = repr(parsed)
    assert "ASSISTANT_SECRET" not in rendered
    assert "TOOL_RESULT_SECRET" not in rendered


def test_error_count_includes_blocks_inside_user_turns() -> None:
    """Error counting is independent from block-detail boundaries."""
    parsed = normalize_transcript(
        jsonl(
            {
                "type": "user",
                "timestamp": "2026-10-20T01:00:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "USER_PROMPT"},
                        {"type": "document", "is_error": True},
                    ],
                },
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert len(parsed.user_turns) == 1
    assert parsed.errors_count == 1
    assert parsed.blocks_outside_user_turns == ()
    assert parsed.user_turns[0].prompt_text == "USER_PROMPT"


def test_non_object_json_records_are_isolated_without_hiding_later_records() -> None:
    """Scalar JSON is valid JSON syntax but not a transcript record."""
    parsed = normalize_transcript(
        jsonl(
            42,
            ["FORBIDDEN_SCALAR"],
            None,
            {
                "type": "assistant",
                "message": {
                    "id": "message-after-invalid-records",
                    "model": "test-model",
                    "content": [{"type": "text", "text": "PRIVATE_TEXT"}],
                    "usage": {"input_tokens": 2, "output_tokens": 3},
                },
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.messages_count == 1
    assert parsed.tokens_total == 5
    assert [(issue.line_no, issue.code, issue.message) for issue in parsed.issues] == [
        (1, "INVALID_TRANSCRIPT_RECORD", "JSONL record is not an object"),
        (2, "INVALID_TRANSCRIPT_RECORD", "JSONL record is not an object"),
        (3, "INVALID_TRANSCRIPT_RECORD", "JSONL record is not an object"),
    ]
    rendered = repr(parsed)
    assert "FORBIDDEN_SCALAR" not in rendered
    assert "PRIVATE_TEXT" not in rendered


@pytest.mark.parametrize("record_type", ["queue-operation", "last-prompt"])
def test_non_attachment_records_do_not_create_user_turns(record_type: str) -> None:
    """Human-attachment-shaped metadata outside attachment records is ignored."""
    parsed = normalize_transcript(
        jsonl(
            {
                "type": record_type,
                "timestamp": "2026-10-20T01:00:00Z",
                "attachment": {
                    "origin": {"kind": "human"},
                    "prompt": "NOT_A_USER_TURN",
                },
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.user_turns == ()
    assert parsed.issues == ()


@pytest.mark.parametrize("timestamp", [None, "not-a-timestamp"])
def test_user_turn_without_valid_timestamp_is_reported_and_skipped(
    timestamp: str | None,
) -> None:
    """A non-null database timestamp is required for every persisted turn."""
    record = {
        "type": "user",
        "message": {"content": "UNPERSISTABLE_PROMPT"},
    }
    if timestamp is not None:
        record["timestamp"] = timestamp

    parsed = normalize_transcript(
        jsonl(record),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.user_turns == ()
    assert len(parsed.issues) == 1
    assert parsed.issues[0].line_no == 1
    assert parsed.issues[0].code == "MISSING_USER_TURN_TIMESTAMP"
    assert "UNPERSISTABLE_PROMPT" not in repr(parsed.issues)


def test_attachment_turn_without_timestamp_is_reported_and_skipped() -> None:
    """Attachment input follows the same non-null timestamp rule."""
    parsed = normalize_transcript(
        jsonl(
            {
                "type": "attachment",
                "attachment": {
                    "origin": {"kind": "human"},
                    "prompt": "UNPERSISTABLE_ATTACHMENT",
                },
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.user_turns == ()
    assert [issue.code for issue in parsed.issues] == ["MISSING_USER_TURN_TIMESTAMP"]
    assert "UNPERSISTABLE_ATTACHMENT" not in repr(parsed.issues)


@pytest.mark.parametrize(
    "control",
    [
        "<local-command-caveat>hidden</local-command-caveat>",
        "<command-name>hidden</command-name>",
        "<task-notification>hidden</task-notification>",
        "<system-reminder>hidden</system-reminder>",
    ],
)
def test_control_messages_do_not_create_user_turns(control: str) -> None:
    """Provider control records are not user input anchors."""
    parsed = normalize_transcript(
        jsonl(
            {
                "type": "user",
                "sessionId": ROOT_ID,
                "timestamp": "2026-10-20T01:00:00Z",
                "message": {"content": control},
            },
        ),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.user_turns == ()


def test_synthetic_payloads_are_the_normalizer_golden_oracle() -> None:
    """Every manifest-derived statistic and event is reproducible from payloads."""
    corpus = load_fixture_corpus(CORPUS_PATH)

    for session in corpus.root_sessions:
        for agent in session.agents:
            record = agent.record
            if not agent.has_payload:
                continue
            parsed = normalize_transcript(
                agent.content,
                root_session_id=session.id,
                agent_id=record.id,
                agent_kind="main" if record.kind == "main" else "subagent",
                agent_meta=record.meta,
            )
            assert parsed.lines == agent.line_count
            assert parsed.messages_count == record.messages_count
            assert parsed.tokens_total == record.tokens_total
            assert parsed.tools_count == record.tools_count
            assert parsed.errors_count == record.errors_count
            assert parsed.model == record.model
            assert parsed.requested_model == record.requested_model
            assert parsed.spawn_depth == record.spawn_depth
            assert parsed.parent_tool_use_id == record.tool_use_id
            assert [
                (
                    event.event_index,
                    event.line_no,
                    event.message_offset,
                    event.kind,
                    event.name,
                    event.description,
                    event.tool_use_id,
                )
                for event in parsed.events
            ] == [
                (
                    event.event_index,
                    event.line_no,
                    event.message_offset,
                    event.kind,
                    event.name,
                    event.description,
                    event.tool_use_id,
                )
                for event in record.events
            ]
            if record.kind == "main":
                assert [
                    (
                        turn.seq,
                        turn.prompt_text,
                        turn.line_no,
                        turn.message_offset,
                        turn.started_at,
                    )
                    for turn in parsed.user_turns
                ] == [
                    (
                        turn.seq,
                        turn.prompt_text,
                        turn.line_no,
                        turn.message_offset,
                        turn.started_at,
                    )
                    for turn in record.user_turns
                ]


def test_local_aggregate_is_content_free_and_requires_root_coverage(tmp_path: Path) -> None:
    """The local verification output contains counts and model names only."""
    source = tmp_path / "sessions"
    source.mkdir()
    for index, suffix in enumerate(("one", "two")):
        session_id = f"11111111-1111-4111-8111-11111111111{index}"
        (source / f"{session_id}.jsonl").write_text(
            jsonl(
                {
                    "type": "user",
                    "sessionId": session_id,
                    "timestamp": "2026-10-20T01:00:00Z",
                    "message": {"content": f"prompt-{suffix}"},
                },
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "message": {
                        "id": f"message-{suffix}",
                        "model": "aggregate-model",
                        "content": [{"type": "text", "text": "private-content"}],
                        "usage": {"input_tokens": 1, "output_tokens": 2},
                    },
                },
            ),
            encoding="utf-8",
        )

    aggregate = normalize_local_sessions(
        Settings(db_dialect=DatabaseDialect.SQLITE),
        source,
    )

    assert aggregate.root_sessions == 2
    assert aggregate.agents == 2
    assert aggregate.lines == 4
    assert aggregate.messages_count == 2
    assert aggregate.tokens_total == 6
    assert aggregate.user_turns_count == 2
    assert aggregate.roots_with_model == 2
    assert aggregate.roots_with_user_turns == 2
    assert aggregate.models == ("aggregate-model",)
    assert "private-content" not in repr(aggregate)
    assert str(tmp_path) not in repr(aggregate)
