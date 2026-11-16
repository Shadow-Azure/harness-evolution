"""Knowledge-root path rules and file-read trigger gating."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

import pytest

from app.service.acquisition.normalize import ParsedTranscript, normalize_transcript
from app.utils.knowledge_paths import (
    MAX_KNOWLEDGE_ROOT_LENGTH,
    MAX_KNOWLEDGE_ROOTS,
    KnowledgeRootError,
    canonical_knowledge_path,
    decode_knowledge_roots,
    knowledge_document_id,
    match_knowledge_root,
    merge_knowledge_roots,
    normalize_knowledge_roots,
)

ROOT_ID = "90000000-0000-4000-8000-000000000001"
KNOWLEDGE_ROOT = "/workspace/knowledge"
SOURCE_ROOT = "/workspace/repository"


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(
    text: str = "synthetic task",
    *,
    timestamp: str = "2026-11-16T01:00:00Z",
) -> dict[str, object]:
    """Build one user turn with an explicit timestamp."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {"content": text},
    }


def read_call(
    tool_id: str,
    path: str,
    *,
    timestamp: str = "2026-11-16T01:01:00Z",
) -> dict[str, object]:
    """Build one assistant record holding a single Read call."""
    return {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": f"message-{tool_id}",
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {"type": "text", "text": "synthetic answer"},
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": "Read",
                    "input": {"file_path": path},
                },
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    }


def read_result(
    tool_id: str,
    path: str,
    content: str,
    *,
    start_line: int = 1,
    num_lines: int = 2,
    total_lines: int = 2,
    timestamp: str = "2026-11-16T01:02:00Z",
) -> dict[str, object]:
    """Build one Read tool result carrying range and body evidence."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
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


def parse(
    records: tuple[object, ...],
    *,
    roots: tuple[str, ...] = (KNOWLEDGE_ROOT,),
    agent_kind: Literal["main", "subagent"] = "main",
) -> ParsedTranscript:
    """Normalize one deterministic transcript with configured knowledge roots."""
    return normalize_transcript(
        jsonl(*records),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind=agent_kind,
        agent_meta=None,
        knowledge_roots=roots,
    )


def test_normalize_knowledge_roots_canonicalizes_dedupes_and_keeps_order() -> None:
    """One canonical form is stored: forward slashes, no trailing slash, stable order."""
    assert normalize_knowledge_roots(
        [
            "  /workspace/knowledge/  ",
            "\\workspace\\shared\\kb",
            "/workspace/knowledge",
            "",
            "/opt/docs/",
        ],
    ) == (
        "/workspace/knowledge",
        "/workspace/shared/kb",
        "/opt/docs",
    )


def test_normalize_knowledge_roots_rejects_the_filesystem_root() -> None:
    """A root must be absolute and narrower than the whole filesystem."""
    with pytest.raises(KnowledgeRootError) as too_broad:
        normalize_knowledge_roots(["/"])
    with pytest.raises(KnowledgeRootError) as trailing:
        normalize_knowledge_roots(["///"])
    assert too_broad.value.reason == "too_broad"
    assert trailing.value.reason == "too_broad"


def test_normalize_knowledge_roots_rejects_relative_parent_and_nul_paths() -> None:
    """Relative, traversal, and NUL roots never reach storage."""
    with pytest.raises(KnowledgeRootError) as relative:
        normalize_knowledge_roots(["knowledge/docs"])
    with pytest.raises(KnowledgeRootError) as traversal:
        normalize_knowledge_roots(["/workspace/../secrets"])
    with pytest.raises(KnowledgeRootError) as nul:
        normalize_knowledge_roots(["/workspace/know\x00ledge"])
    assert relative.value.reason == "not_absolute"
    assert traversal.value.reason == "parent_traversal"
    assert nul.value.reason == "nul_byte"


def test_merge_knowledge_roots_has_no_per_workspace_count_limit() -> None:
    """The read-side union normalizes and dedupes without the write-side limit."""
    first = [f"/kb-a/{index}" for index in range(11)]
    second = [f"/kb-b/{index}" for index in range(11)]

    merged = merge_knowledge_roots([*first, *second, "/kb-a/0/", "relative/ignored", "/"])

    assert len(merged) == 22
    assert merged[:11] == tuple(first)
    assert merged[11:] == tuple(second)


def test_merge_knowledge_roots_ignores_invalid_values() -> None:
    """One bad stored value never breaks the read-side union."""
    assert merge_knowledge_roots(
        ["/kb/team", "relative", "/workspace/../secrets", 42, None, "/kb/team/"],
    ) == ("/kb/team",)


def test_decode_knowledge_roots_canonicalizes_stored_values() -> None:
    """A legacy row never returns non-canonical or invalid roots."""
    assert decode_knowledge_roots(["/kb/", "relative", "/kb", "/", 7, None]) == ("/kb",)
    assert decode_knowledge_roots('["/kb//team/"]') == ("/kb/team",)
    assert decode_knowledge_roots("not-json") == ()
    assert decode_knowledge_roots(None) == ()


def test_canonical_knowledge_path_normalizes_spelling() -> None:
    """The public canonical path is the single identity input."""
    assert canonical_knowledge_path("/kb//guides/a.md/") == "/kb/guides/a.md"
    assert canonical_knowledge_path("\\kb\\guides\\a.md") == "/kb/guides/a.md"
    assert canonical_knowledge_path("relative/a.md") is None
    assert canonical_knowledge_path("/kb/../a.md") is None
    assert canonical_knowledge_path("/kb/a\x00.md") is None


def test_normalize_knowledge_roots_enforces_count_and_length_limits() -> None:
    """At most 20 roots and 512 characters each are allowed."""
    too_many = [f"/kb/{index}" for index in range(MAX_KNOWLEDGE_ROOTS + 1)]
    assert len(normalize_knowledge_roots(too_many[:MAX_KNOWLEDGE_ROOTS])) == (MAX_KNOWLEDGE_ROOTS)
    with pytest.raises(KnowledgeRootError) as count:
        normalize_knowledge_roots(too_many)
    assert count.value.reason == "too_many"

    with pytest.raises(KnowledgeRootError) as length:
        normalize_knowledge_roots(["/" + "a" * MAX_KNOWLEDGE_ROOT_LENGTH])
    assert length.value.reason == "too_long"


def test_match_knowledge_root_uses_longest_boundary_matched_prefix() -> None:
    """A root matches only whole path segments and the longest root wins."""
    roots = normalize_knowledge_roots(["/kb", "/kb/team", "/kb2"])

    assert match_knowledge_root("/kb/guide.md", roots) == "/kb"
    assert match_knowledge_root("/kb/team/guide.md", roots) == "/kb/team"
    assert match_knowledge_root("/kb2/guide.md", roots) == "/kb2"
    assert match_knowledge_root("/kb-other/guide.md", roots) is None
    assert match_knowledge_root("kb/guide.md", roots) is None
    assert match_knowledge_root("/workspace/repository/src/app.py", roots) is None


def test_knowledge_document_id_is_stable_and_root_relative() -> None:
    """The document id hashes the canonical root-relative path, not the body."""
    first = knowledge_document_id("/workspace/knowledge/guides/a.md", KNOWLEDGE_ROOT)
    repeat = knowledge_document_id("/workspace/knowledge/guides/a.md", KNOWLEDGE_ROOT)
    other = knowledge_document_id("/workspace/knowledge/guides/b.md", KNOWLEDGE_ROOT)

    assert first == repeat
    assert first != other
    assert first.startswith("doc:")
    assert first == "doc:" + hashlib.sha256(b"guides/a.md").hexdigest()[:32]


def test_knowledge_document_id_folds_path_spelling() -> None:
    """Windows slashes, duplicate slashes, and trailing slashes share one identity."""
    canonical = knowledge_document_id("/workspace/knowledge/guides/a.md", KNOWLEDGE_ROOT)

    assert knowledge_document_id("/workspace/knowledge//guides/a.md", KNOWLEDGE_ROOT) == canonical
    assert knowledge_document_id("/workspace/knowledge/guides/a.md/", KNOWLEDGE_ROOT) == canonical
    assert (
        knowledge_document_id("\\workspace\\knowledge\\guides\\a.md", KNOWLEDGE_ROOT) == canonical
    )


def test_read_inside_a_knowledge_root_emits_a_document_event() -> None:
    """A Read under a configured root becomes one knowledge event with identity."""
    content = "# Runbook\n\nRestart the worker.\n"
    parsed = parse(
        (
            user(),
            read_call("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md"),
            read_result("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md", content),
        ),
    )

    assert len(parsed.events) == 1
    event = parsed.events[0]
    assert event.kind == "knowledge"
    assert event.name == "runbook.md"
    assert event.retrieval_kind == "file_read"
    assert event.retrieval_scope == KNOWLEDGE_ROOT
    assert event.source_path == f"{KNOWLEDGE_ROOT}/guides/runbook.md"
    assert event.document_id == knowledge_document_id(
        f"{KNOWLEDGE_ROOT}/guides/runbook.md",
        KNOWLEDGE_ROOT,
    )
    assert event.document_revision == "digest:" + hashlib.sha256(content.encode()).hexdigest()
    assert event.object_revision == event.document_revision
    assert event.tool_use_id == "tool-read"
    evidence = next(item for item in parsed.evidence if item.tool_use_id == "tool-read")
    assert evidence.content_hash == hashlib.sha256(content.encode()).hexdigest()
    assert evidence.complete is True


def test_read_outside_every_knowledge_root_emits_no_event() -> None:
    """The paired ordinary source Read still records evidence but no trigger."""
    parsed = parse(
        (
            user(),
            read_call("tool-read", f"{SOURCE_ROOT}/src/app.py"),
            read_result("tool-read", f"{SOURCE_ROOT}/src/app.py", "print('app')\n"),
        ),
    )

    assert parsed.events == ()
    assert [item.kind for item in parsed.evidence if item.kind == "file_read"] == ["file_read"]


def test_read_without_configured_roots_emits_no_event() -> None:
    """Without a workspace knowledge root, every Read stays ordinary."""
    parsed = parse(
        (
            user(),
            read_call("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md"),
            read_result("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md", "body"),
        ),
        roots=(),
    )

    assert parsed.events == ()


def test_read_without_tool_result_emits_no_event() -> None:
    """A Read call whose result never arrived has no document evidence."""
    parsed = parse((user(), read_call("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md")))

    assert parsed.events == ()
    assert [item.code for item in parsed.issues] == ["TOOL_USE_OPEN"]


def test_partial_read_keeps_unknown_revision_but_marks_incomplete() -> None:
    """A ranged read cannot claim a document revision, so it records unknown."""
    parsed = parse(
        (
            user(),
            read_call("tool-read", f"{KNOWLEDGE_ROOT}/guides/large.md"),
            read_result(
                "tool-read",
                f"{KNOWLEDGE_ROOT}/guides/large.md",
                "line 20\n",
                start_line=20,
                num_lines=1,
                total_lines=200,
            ),
        ),
    )

    event = parsed.events[0]
    assert event.document_revision == "unknown"
    assert event.object_revision == "unknown"
    evidence = next(item for item in parsed.evidence if item.tool_use_id == "tool-read")
    assert evidence.complete is False


def test_edit_and_bash_never_emit_knowledge_events() -> None:
    """Only a Read of a configured root is a knowledge trigger."""
    edit = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:01:00Z",
        "message": {
            "id": "message-edit",
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-edit",
                    "name": "Edit",
                    "input": {"file_path": f"{KNOWLEDGE_ROOT}/guides/runbook.md"},
                },
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    edit_result = {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:02:00Z",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": "tool-edit", "content": "ok"}],
        },
        "toolUseResult": {
            "type": "update",
            "filePath": f"{KNOWLEDGE_ROOT}/guides/runbook.md",
            "originalFile": "old\n",
        },
    }
    bash = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:03:00Z",
        "message": {
            "id": "message-bash",
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-bash",
                    "name": "Bash",
                    "input": {"command": f"cat {KNOWLEDGE_ROOT}/guides/runbook.md"},
                },
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    bash_result = {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:04:00Z",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": "tool-bash", "content": "body"}],
        },
        "toolUseResult": {
            "type": "text",
            "file": {
                "filePath": f"{KNOWLEDGE_ROOT}/guides/runbook.md",
                "content": "body",
                "startLine": 1,
                "numLines": 1,
                "totalLines": 1,
            },
        },
    }

    parsed = parse((user(), edit, edit_result, bash, bash_result))

    assert parsed.events == ()


def test_knowledge_events_are_stable_sorted_and_reindexed() -> None:
    """Events are ordered by call line, so a late result cannot reorder history."""
    skill = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:03:00Z",
        "message": {
            "id": "message-skill",
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-skill",
                    "name": "Skill",
                    "input": {"skill": "review"},
                },
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    parsed = parse(
        (
            user(),
            read_call("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md"),
            skill,
            read_result("tool-read", f"{KNOWLEDGE_ROOT}/guides/runbook.md", "body"),
        ),
    )

    assert [event.kind for event in parsed.events] == ["knowledge", "skill"]
    assert [event.event_index for event in parsed.events] == [0, 1]
    assert parsed.events[0].line_no == 2
    assert parsed.events[1].line_no == 3


def test_knowledge_event_coordinates_follow_the_read_call() -> None:
    """Line, message offset, and triggered time come from the assistant call."""
    parsed = parse(
        (
            user(),
            user("second task", timestamp="2026-11-16T01:00:30Z"),
            read_call(
                "tool-read",
                f"{KNOWLEDGE_ROOT}/guides/runbook.md",
                timestamp="2026-11-16T01:05:00Z",
            ),
            read_result(
                "tool-read",
                f"{KNOWLEDGE_ROOT}/guides/runbook.md",
                "body",
                timestamp="2026-11-16T01:09:00Z",
            ),
        ),
    )

    event = parsed.events[0]
    assert event.line_no == 3
    assert event.message_offset == 0
    assert event.triggered_at is not None
    assert event.triggered_at.hour == 9
    assert event.triggered_at.minute == 5


def test_read_path_spelling_is_canonicalized_in_the_event() -> None:
    """The event stores the canonical path and one document identity."""
    records = (
        user(),
        read_call("tool-double", f"{KNOWLEDGE_ROOT}//guides/a.md"),
        read_result("tool-double", f"{KNOWLEDGE_ROOT}//guides/a.md", "body"),
        read_call("tool-windows", "\\workspace\\knowledge\\guides\\b.md"),
        read_result(
            "tool-windows",
            "\\workspace\\knowledge\\guides\\b.md",
            "body",
        ),
        read_call("tool-trailing", f"{KNOWLEDGE_ROOT}/guides/c.md/"),
        read_result("tool-trailing", f"{KNOWLEDGE_ROOT}/guides/c.md/", "body"),
    )
    parsed = parse(records)

    assert [event.source_path for event in parsed.events] == [
        f"{KNOWLEDGE_ROOT}/guides/a.md",
        f"{KNOWLEDGE_ROOT}/guides/b.md",
        f"{KNOWLEDGE_ROOT}/guides/c.md",
    ]
    assert parsed.events[0].document_id == knowledge_document_id(
        f"{KNOWLEDGE_ROOT}/guides/a.md",
        KNOWLEDGE_ROOT,
    )


def test_very_long_document_path_is_truncated_to_the_column() -> None:
    """A path longer than the 1024 column is stored as a bounded prefix."""
    long_path = f"{KNOWLEDGE_ROOT}/" + "x" * 1500 + ".md"
    parsed = parse(
        (
            user(),
            read_call("tool-long", long_path),
            read_result("tool-long", long_path, "body"),
        ),
    )

    event = parsed.events[0]
    assert event.source_path is not None
    assert len(event.source_path) == 1024
    assert event.source_path == long_path[:1024]
    assert event.document_id == knowledge_document_id(long_path, KNOWLEDGE_ROOT)


def test_subagent_reads_also_use_the_payload_knowledge_roots() -> None:
    """Root matching is runtime-agnostic and applies to child transcripts too."""
    parsed = parse(
        (
            user(),
            read_call("tool-read", f"{KNOWLEDGE_ROOT}/team/oncall.md"),
            read_result("tool-read", f"{KNOWLEDGE_ROOT}/team/oncall.md", "body"),
        ),
        agent_kind="subagent",
    )

    assert len(parsed.events) == 1
    assert parsed.events[0].kind == "knowledge"
