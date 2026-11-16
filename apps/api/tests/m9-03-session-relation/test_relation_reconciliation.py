"""M9-03 parent relation reconciliation and evidence exposure."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.crud.sessions import SessionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import agent_events, bad_cases, trajectory_payloads
from app.service.acquisition.agent_tree import assemble_agent_trees
from app.service.acquisition.local_sessions import scan_local_sessions
from app.service.acquisition.normalize import ParsedTranscript, normalize_transcript
from app.service.acquisition.replay import replay_pending_payloads
from app.service.sessions.service import SessionService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures" / "m9-real-shape"
ROOT_ID = "50000000-0000-4000-8000-000000000001"
FIXTURE_ROOT_ID = "40000000-0000-4000-8000-000000000001"
CHILD_ID = "agent-relation-child"
PARENT_TOOL_ID = "call-agent-parent"


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(text: str, *, timestamp: str = "2026-11-16T01:00:00Z") -> dict[str, object]:
    """Build one root user record."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {"content": text},
    }


def tool_result(
    tool_use_id: str,
    *,
    timestamp: str = "2026-11-16T01:02:00Z",
) -> dict[str, object]:
    """Build one user record carrying a tool result."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "synthetic result",
                },
            ],
        },
    }


def assistant(
    message_id: str,
    *,
    tools: tuple[tuple[str, str], ...] = (),
    stop_reason: str = "end_turn",
    timestamp: str = "2026-11-16T01:01:00Z",
) -> dict[str, object]:
    """Build one assistant record with optional Agent tool calls."""
    content: list[dict[str, object]] = [{"type": "text", "text": "synthetic answer"}]
    for tool_id, name in tools:
        content.append(
            {
                "type": "tool_use",
                "id": tool_id,
                "name": name,
                "input": {"description": "synthetic child"},
            },
        )
    return {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": "model-main",
            "stop_reason": stop_reason,
            "content": content,
            "usage": {"input_tokens": 4, "output_tokens": 2},
        },
    }


def parse(
    records: tuple[object, ...],
    *,
    agent_id: str,
    kind: str,
    meta: dict[str, object] | None = None,
) -> ParsedTranscript:
    """Normalize one deterministic transcript."""
    return normalize_transcript(
        jsonl(*records),
        root_session_id=ROOT_ID,
        agent_id=agent_id,
        agent_kind="main" if kind == "main" else "subagent",
        agent_meta=meta,
    )


def child(meta: dict[str, object]) -> ParsedTranscript:
    """Build one child transcript with explicit relation metadata."""
    return parse(
        (assistant("child-message"),),
        agent_id=CHILD_ID,
        kind="subagent",
        meta=meta,
    )


def relation_event(tree: Any, child_id: str) -> Any:
    """Return the parent trigger event that anchors one child."""
    target = next(item for item in tree.nodes if item.id == child_id)
    parent = next(item for item in tree.nodes if item.id == target.parent_agent_id)
    matching = [
        event
        for event in parent.events
        if event.kind == "agent" and event.tool_use_id == target.tool_use_id
    ]
    assert len(matching) == 1
    return matching[0]


def test_matching_tool_use_and_result_is_authoritative() -> None:
    """All three strong signals produce an authoritative parent edge."""
    main = parse(
        (
            user("synthetic prompt"),
            assistant(
                "main-tool",
                tools=((PARENT_TOOL_ID, "Agent"),),
                stop_reason="tool_use",
            ),
            tool_result(PARENT_TOOL_ID),
            assistant("main-final"),
        ),
        agent_id=ROOT_ID,
        kind="main",
    )
    child_transcript = child(
        {
            "agentType": "Explore",
            "description": "synthetic child",
            "toolUseId": PARENT_TOOL_ID,
        },
    )

    tree = assemble_agent_trees((main, child_transcript)).trees[0]

    node = next(item for item in tree.nodes if item.id == CHILD_ID)
    assert node.parent_agent_id == ROOT_ID
    assert relation_event(tree, CHILD_ID).relation_confidence == "authoritative"


def test_missing_tool_result_downgrades_to_derived_and_keeps_the_node() -> None:
    """A matching call without its result stays linked with lower confidence."""
    main = parse(
        (
            user("synthetic prompt"),
            assistant(
                "main-tool",
                tools=((PARENT_TOOL_ID, "Agent"),),
                stop_reason="tool_use",
            ),
        ),
        agent_id=ROOT_ID,
        kind="main",
    )
    child_transcript = child(
        {
            "agentType": "Explore",
            "description": "synthetic child",
            "toolUseId": PARENT_TOOL_ID,
        },
    )

    result = assemble_agent_trees((main, child_transcript))
    tree = result.trees[0]

    node = next(item for item in tree.nodes if item.id == CHILD_ID)
    assert node.parent_agent_id == ROOT_ID
    assert relation_event(tree, CHILD_ID).relation_confidence == "derived"
    assert CHILD_ID in {item.id for item in tree.nodes}


def test_parent_agent_metadata_alone_is_synthetic() -> None:
    """Weak metadata keeps the child under its named parent without an issue."""
    main = parse(
        (user("synthetic prompt"), assistant("main-final")),
        agent_id=ROOT_ID,
        kind="main",
    )
    child_transcript = child(
        {
            "agentType": "Explore",
            "description": "synthetic child",
            "parentAgentId": ROOT_ID,
        },
    )

    result = assemble_agent_trees((main, child_transcript))
    tree = result.trees[0]

    node = next(item for item in tree.nodes if item.id == CHILD_ID)
    assert node.parent_agent_id == ROOT_ID
    assert node.tool_use_id is not None
    assert relation_event(tree, CHILD_ID).relation_confidence == "synthetic"
    assert [issue.code for issue in result.issues if issue.agent_id == CHILD_ID] == []


def test_unknown_parent_identity_stays_unresolved_and_visible() -> None:
    """A child with no usable parent evidence remains in the diagnostic tree."""
    main = parse(
        (user("synthetic prompt"), assistant("main-final")),
        agent_id=ROOT_ID,
        kind="main",
    )
    child_transcript = child(
        {
            "agentType": "Explore",
            "description": "synthetic child",
            "toolUseId": "call-not-in-parent",
        },
    )

    result = assemble_agent_trees((main, child_transcript))
    tree = result.trees[0]

    node = next(item for item in tree.nodes if item.id == CHILD_ID)
    assert node.parent_agent_id == ROOT_ID
    assert node.tool_use_id is not None
    assert relation_event(tree, CHILD_ID).relation_confidence == "unresolved"
    assert "UNKNOWN_PARENT_TOOL_USE_ID" in {issue.code for issue in result.issues}
    assert tree.parent_by_id()[CHILD_ID] == ROOT_ID


def test_unmatched_tool_use_with_weak_parent_is_synthetic() -> None:
    """A known parentAgentId still lowers an unknown tool id to synthetic."""
    main = parse(
        (user("synthetic prompt"), assistant("main-final")),
        agent_id=ROOT_ID,
        kind="main",
    )
    child_transcript = child(
        {
            "agentType": "Explore",
            "description": "synthetic child",
            "toolUseId": "call-not-in-parent",
            "parentAgentId": ROOT_ID,
        },
    )

    result = assemble_agent_trees((main, child_transcript))
    tree = result.trees[0]

    node = next(item for item in tree.nodes if item.id == CHILD_ID)
    assert node.parent_agent_id == ROOT_ID
    assert relation_event(tree, CHILD_ID).relation_confidence == "synthetic"
    assert "UNKNOWN_PARENT_TOOL_USE_ID" in {issue.code for issue in result.issues}


def test_ambiguous_tool_use_with_weak_parent_is_synthetic() -> None:
    """A known parentAgentId survives an ambiguous tool identity."""
    main = parse(
        (
            user("synthetic prompt"),
            assistant(
                "main-tool",
                tools=(("duplicate-tool", "Agent"), ("duplicate-tool", "Agent")),
                stop_reason="tool_use",
            ),
        ),
        agent_id=ROOT_ID,
        kind="main",
    )
    child_transcript = child(
        {
            "agentType": "Explore",
            "description": "synthetic child",
            "toolUseId": "duplicate-tool",
            "parentAgentId": ROOT_ID,
        },
    )

    result = assemble_agent_trees((main, child_transcript))
    tree = result.trees[0]

    node = next(item for item in tree.nodes if item.id == CHILD_ID)
    assert node.parent_agent_id == ROOT_ID
    assert relation_event(tree, CHILD_ID).relation_confidence == "synthetic"
    assert "AMBIGUOUS_PARENT_TOOL_USE_ID" in {issue.code for issue in result.issues}


async def test_replay_persists_relation_confidence_and_api_exposes_it(tmp_path: Path) -> None:
    """Replay writes parent relation evidence and the tree DTO returns it."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'relation.db'}",
        ),
    )
    payloads = _authoritative_payloads()
    try:
        await _run_replay(database, payloads)
        rows = await _select_relations(database)
        assert (ROOT_ID, 0, PARENT_TOOL_ID, "authoritative") in rows
        await _insert_bad_case(database)

        service = SessionService(SessionRepository(database))
        tree = await service.tree(ROOT_ID, WorkspaceReadScope.all_workspaces())
        event = next(
            event
            for agent in tree.agents
            for event in agent.events
            if event.tool_use_id == PARENT_TOOL_ID
        )
        assert event.relation_confidence == "authoritative"
    finally:
        await database.dispose()


async def test_real_shape_fixture_reports_derived_relation(tmp_path: Path) -> None:
    """The sanitized real-shape fixture keeps a missing result as derived."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'derived.db'}",
        ),
    )
    try:
        corpus = scan_local_sessions(FIXTURE_ROOT)
        payloads = [
            {
                "runtime_key": payload.runtime_key,
                "root_session_id": payload.root_session_id,
                "agent_id": payload.agent_id,
                "agent_kind": payload.agent_kind,
                "payload": payload.content,
                "agent_meta": payload.agent_meta,
                "content_hash": payload.content_hash,
                "line_count": payload.line_count,
                "source_type": "script",
                "updated_at": datetime(2026, 11, 16, 2, tzinfo=UTC),
            }
            for payload in corpus.payloads
        ]
        await _run_replay(database, payloads)
        rows = await _select_relations(database)
        assert (FIXTURE_ROOT_ID, 1, "tool-agent-1", "derived") in rows
    finally:
        await database.dispose()


def _authoritative_payloads() -> list[dict[str, object]]:
    """Build one authoritative root payload pair for the replay pipeline."""
    main = jsonl(
        user("synthetic prompt"),
        assistant(
            "main-tool",
            tools=((PARENT_TOOL_ID, "Agent"),),
            stop_reason="tool_use",
        ),
        tool_result(PARENT_TOOL_ID),
        assistant("main-final"),
    )
    child_transcript = jsonl(assistant("child-message"))
    meta = {
        "agentType": "Explore",
        "description": "synthetic child",
        "toolUseId": PARENT_TOOL_ID,
        "spawnDepth": 1,
    }
    return [
        {
            "runtime_key": "claude-code",
            "root_session_id": ROOT_ID,
            "agent_id": ROOT_ID,
            "agent_kind": "main",
            "payload": main,
            "agent_meta": None,
            "content_hash": hashlib.sha256(main.encode()).hexdigest(),
            "line_count": len(main.splitlines()),
            "source_type": "script",
            "updated_at": datetime(2026, 11, 16, 2, tzinfo=UTC),
        },
        {
            "runtime_key": "claude-code",
            "root_session_id": ROOT_ID,
            "agent_id": CHILD_ID,
            "agent_kind": "subagent",
            "payload": child_transcript,
            "agent_meta": meta,
            "content_hash": hashlib.sha256(child_transcript.encode()).hexdigest(),
            "line_count": len(child_transcript.splitlines()),
            "source_type": "script",
            "updated_at": datetime(2026, 11, 16, 2, tzinfo=UTC),
        },
    ]


async def _run_replay(database: Any, payloads: Sequence[Mapping[str, object]]) -> None:
    """Insert payloads and run the acquisition replay once."""
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        for payload in payloads:
            await session.execute(trajectory_payloads.insert().values(**payload))
    await replay_pending_payloads(database)


async def _insert_bad_case(database: Any) -> None:
    """Project one bad case so the scoped Session read path exposes the root."""
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id="case-relation-1",
                bad_case_session_id=ROOT_ID,
                bad_case_type="self",
                object_name="Explore",
                object_type="agent",
                title="synthetic child",
                bad_case_description="synthetic relation test",
                created_at=datetime(2026, 11, 16, 2, tzinfo=UTC),
                updated_at=datetime(2026, 11, 16, 2, tzinfo=UTC),
            ),
        )


async def _select_relations(
    database: Any,
) -> list[tuple[str, int, str | None, str]]:
    """Read stored relation confidence with its owning event identity."""
    async with database.session() as session:
        rows = (
            await session.execute(
                select(
                    agent_events.c.agent_id,
                    agent_events.c.event_index,
                    agent_events.c.tool_use_id,
                    agent_events.c.relation_confidence,
                ).where(agent_events.c.relation_confidence.is_not(None)),
            )
        ).all()
    return [
        (
            str(agent_id),
            int(event_index),
            str(tool_use_id) if tool_use_id is not None else None,
            str(relation),
        )
        for agent_id, event_index, tool_use_id, relation in rows
    ]
