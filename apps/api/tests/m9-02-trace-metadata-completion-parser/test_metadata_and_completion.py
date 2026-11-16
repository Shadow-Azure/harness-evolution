"""M9-02 metadata tolerance, completion states, and model evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

import pytest

from app.service.acquisition.local_sessions import (
    LocalSessionSourceError,
    scan_local_sessions,
)
from app.service.acquisition.normalize import (
    CURRENT_PARSER_VERSION,
    ParsedTranscript,
    normalize_transcript,
)
from app.service.sessions import schemas as session_schemas

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures" / "m9-real-shape"
ROOT_ID = "40000000-0000-4000-8000-000000000001"
AGENT_ID = "m902review0001"


def jsonl(*records: object | str) -> str:
    """Encode deterministic JSONL test input."""
    return (
        "\n".join(
            record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
            for record in records
        )
        + "\n"
    )


def assistant(
    message_id: str,
    *,
    stop_reason: str | None = "end_turn",
    model: str = "claude-sonnet-4-5-20250929",
    tools: tuple[tuple[str, str, dict[str, object]], ...] = (),
    api_error: bool = False,
) -> dict[str, object]:
    """Build one assistant record with explicit completion evidence."""
    content: list[dict[str, object]] = [{"type": "text", "text": "private assistant text"}]
    for tool_id, name, tool_input in tools:
        content.append({"type": "tool_use", "id": tool_id, "name": name, "input": tool_input})
    message: dict[str, object] = {
        "id": message_id,
        "model": model,
        "content": content,
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    if stop_reason is not None:
        message["stop_reason"] = stop_reason
    record: dict[str, object] = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-14T02:00:00Z",
        "message": message,
    }
    if api_error:
        record["isApiErrorMessage"] = True
    return record


def tool_result(tool_use_id: str, **tool_use_result: object) -> dict[str, object]:
    """Build one tool result record with optional file evidence."""
    record: dict[str, object] = {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-14T02:00:00Z",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": "private result"},
            ],
        },
    }
    if tool_use_result:
        record["toolUseResult"] = tool_use_result
    return record


def parse(
    content: str,
    *,
    agent_kind: Literal["main", "subagent"] = "main",
    meta: dict[str, object] | None = None,
) -> ParsedTranscript:
    """Normalize one test payload."""
    return normalize_transcript(
        content,
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID if agent_kind == "main" else AGENT_ID,
        agent_kind=agent_kind,
        agent_meta=meta,
    )


def test_parser_version_advances_with_new_evidence() -> None:
    """The parser version changes because normalization semantics changed."""
    assert CURRENT_PARSER_VERSION == 2


def test_task_snapshot_and_open_tool_use_are_explicit() -> None:
    """A trailing tool call with an explicit stop reason reports TOOL_USE_OPEN."""
    payload = jsonl(
        assistant(
            "message-1",
            stop_reason="tool_use",
            tools=(("tool-open", "Agent", {"subagent_type": "Explore"}),),
        ),
        {
            "type": "task_reminder",
            "sessionId": ROOT_ID,
            "tasks": [{"status": "in_progress"}, {"status": "pending"}, {"status": "completed"}],
            "stop_reason": "tool_use",
        },
    )

    parsed = parse(payload, meta=None)

    assert parsed.execution_outcome == "interrupted"
    assert parsed.end_reason == "tool_use_open"
    assert [issue.code for issue in parsed.issues] == [
        "TOOL_USE_OPEN",
        "TASK_SNAPSHOT_PENDING",
    ]
    assert "tool-open" not in repr(parsed.issues)


def test_missing_stop_reason_stays_legacy_unknown() -> None:
    """Legacy payloads without explicit stop evidence are not guessed complete."""
    parsed = parse(jsonl(assistant("message-1", stop_reason=None)))

    assert parsed.execution_outcome == "legacy_unknown"
    assert parsed.end_reason is None
    assert parsed.issues == ()


def test_child_without_end_turn_reports_missing_final_report() -> None:
    """A child that consumed its tools but never reached end_turn stays interrupted."""
    payload = jsonl(
        assistant(
            "message-1",
            stop_reason="tool_use",
            tools=(("tool-read", "Read", {"file_path": "/workspace/file.py"}),),
        ),
        tool_result("tool-read"),
    )

    parsed = parse(payload, agent_kind="subagent")

    assert parsed.execution_outcome == "interrupted"
    assert parsed.end_reason == "missing_report"
    assert [issue.code for issue in parsed.issues] == ["MISSING_FINAL_REPORT"]


def test_end_turn_completes_and_api_error_fails() -> None:
    """Completion and external failure stay separate from parse health."""
    completed = parse(jsonl(assistant("message-1", stop_reason="end_turn")))
    failed = parse(jsonl(assistant("message-2", stop_reason="end_turn", api_error=True)))
    interrupted = parse(jsonl(assistant("message-3", stop_reason="user_interrupt")))

    assert (completed.execution_outcome, completed.end_reason) == ("completed", "end_turn")
    assert (failed.execution_outcome, failed.end_reason) == ("failed", "external_failed")
    assert (interrupted.execution_outcome, interrupted.end_reason) == (
        "interrupted",
        "external_interrupted",
    )


def test_requested_and_reported_models_are_separate() -> None:
    """Concrete model disagreement becomes evidence instead of overwriting a field."""
    parsed = parse(
        jsonl(assistant("message-1", stop_reason="end_turn")),
        meta={"agentType": "Explore", "spawnDepth": 1},
    )

    assert parsed.requested_model is None
    assert parsed.reported_model == "claude-sonnet-4-5-20250929"
    assert parsed.model == parsed.reported_model
    assert parsed.model_evidence == "reported"


def test_concrete_model_conflict_warns_without_overwrite() -> None:
    """A concrete requested model and a different reported model both survive."""
    parsed = parse(
        jsonl(assistant("message-1", stop_reason="end_turn")),
        meta={
            "agentType": "Explore",
            "description": "reviewer",
            "spawnDepth": 1,
            "model": "claude-opus-4-1",
        },
    )

    assert parsed.requested_model == "claude-opus-4-1"
    assert parsed.reported_model == "claude-sonnet-4-5-20250929"
    assert [issue.code for issue in parsed.issues] == ["MODEL_EVIDENCE_CONFLICT"]


def test_alias_model_is_not_treated_as_conflict() -> None:
    """A provider alias such as sonnet is not a conflicting concrete identity."""
    parsed = parse(
        jsonl(assistant("message-1", stop_reason="end_turn")),
        meta={
            "agentType": "Explore",
            "description": "reviewer",
            "spawnDepth": 1,
            "model": "sonnet",
        },
    )

    assert parsed.issues == ()


def test_completion_values_match_public_contract() -> None:
    """Parser completion literals stay inside the closed API sets."""
    assert {
        "completed",
        "interrupted",
        "failed",
        "legacy_unknown",
    } == set(session_schemas.EXECUTION_OUTCOMES)
    assert {"end_turn", "tool_use_open", "missing_report"} <= set(session_schemas.END_REASONS)
    assert {"prompt_snapshot", "api_request_shape", "builtin"} <= set(
        session_schemas.DEFINITION_SOURCES,
    )


def _write_local_tree(
    root: Path,
    *,
    root_id: str,
    root_lines: list[dict[str, object]],
    agent_id: str,
    agent_lines: list[dict[str, object]],
    meta: dict[str, object],
) -> None:
    """Write one local Claude session tree for import tests."""
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{root_id}.jsonl").write_text(jsonl(*root_lines), encoding="utf-8")
    subagents = root / root_id / "subagents"
    subagents.mkdir(parents=True)
    (subagents / f"agent-{agent_id}.jsonl").write_text(jsonl(*agent_lines), encoding="utf-8")
    (subagents / f"agent-{agent_id}.meta.json").write_text(
        json.dumps(meta),
        encoding="utf-8",
    )


def _base_root_lines(root_id: str) -> list[dict[str, object]]:
    """Return a minimal valid root transcript."""
    return [
        {
            "type": "user",
            "sessionId": root_id,
            "timestamp": "2026-11-14T02:00:00Z",
            "cwd": "/workspace/example",
            "message": {"content": "synthetic prompt"},
        },
    ]


def test_unknown_scalar_metadata_is_sanitized_and_imported(tmp_path: Path) -> None:
    """Unknown scalar metadata does not reject a Session and stays bounded."""
    root_id = ROOT_ID
    agent_id = AGENT_ID
    _write_local_tree(
        tmp_path,
        root_id=root_id,
        root_lines=_base_root_lines(root_id),
        agent_id=agent_id,
        agent_lines=[
            {
                "type": "assistant",
                "sessionId": root_id,
                "agentId": agent_id,
                "message": {"id": "m1", "content": []},
            },
        ],
        meta={
            "agentType": "Explore",
            "description": "reviewer",
            "spawnDepth": 1,
            "isBuiltIn": False,
            "pickedEffortModel": "claude-opus-4-1",
            "finished": False,
            "futureFlag": True,
            "futureNested": {"hidden": "drop me"},
            "futureList": [1, 2],
            "futureLongText": "x" * 400,
        },
    )

    corpus = scan_local_sessions(tmp_path)
    child = corpus.payloads[1]

    assert child.agent_meta is not None
    assert child.agent_meta["isBuiltIn"] is False
    assert child.agent_meta["pickedEffortModel"] == "claude-opus-4-1"
    assert child.agent_meta["futureFlag"] is True
    assert "futureNested" not in child.agent_meta
    assert "futureList" not in child.agent_meta
    assert len(cast(str, child.agent_meta["futureLongText"])) == 256


def test_known_metadata_field_still_fails_validation(tmp_path: Path) -> None:
    """Known fields retain strict validation even when unknown fields are tolerated."""
    _write_local_tree(
        tmp_path,
        root_id=ROOT_ID,
        root_lines=_base_root_lines(ROOT_ID),
        agent_id=AGENT_ID,
        agent_lines=[
            {
                "type": "assistant",
                "sessionId": ROOT_ID,
                "agentId": AGENT_ID,
                "message": {"id": "m1", "content": []},
            },
        ],
        meta={
            "agentType": "Explore",
            "description": "reviewer",
            "spawnDepth": -1,
            "futureFlag": True,
        },
    )

    with pytest.raises(LocalSessionSourceError):
        scan_local_sessions(tmp_path)


def test_real_shape_fixture_exposes_explicit_completion() -> None:
    """The sanitized real-shape fixture imports and exposes completion diagnostics."""
    corpus = scan_local_sessions(FIXTURE_ROOT)
    by_agent = {payload.agent_id: payload for payload in corpus.payloads}

    root = normalize_transcript(
        by_agent[ROOT_ID].content,
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )
    child = normalize_transcript(
        by_agent[AGENT_ID].content,
        root_session_id=ROOT_ID,
        agent_id=AGENT_ID,
        agent_kind="subagent",
        agent_meta=by_agent[AGENT_ID].agent_meta,
    )

    assert root.execution_outcome == "interrupted"
    assert root.end_reason == "tool_use_open"
    assert {issue.code for issue in root.issues} == {
        "TOOL_USE_OPEN",
        "TASK_SNAPSHOT_PENDING",
    }
    assert child.execution_outcome == "interrupted"
    assert child.end_reason == "missing_report"
    assert {issue.code for issue in child.issues} == {
        "UNKNOWN_AGENT_METADATA",
        "MISSING_FINAL_REPORT",
        "MODEL_EVIDENCE_CONFLICT",
    }
    assert child.definition_source == "prompt_snapshot"
    assert child.agent_definition_hash is not None
    for secret in (
        "只检查合成输入",
        "You are a synthetic reviewer",
        "futureNested",
        "must not be stored",
    ):
        assert secret not in repr(root)
        assert secret not in repr(child)
