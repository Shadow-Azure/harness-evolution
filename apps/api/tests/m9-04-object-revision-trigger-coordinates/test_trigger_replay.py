"""M9-04 trigger coordinates and revisions persist through replay."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import agent_events, agents, trajectory_payloads
from app.service.acquisition.normalize import normalize_transcript
from app.service.acquisition.replay import replay_pending_payloads

ROOT_ID = "60000000-0000-4000-8000-000000000001"
CHILD_ONE = "agent-coordinate-child-one"
CHILD_TWO = "agent-coordinate-child-two"
GRANDCHILD = "agent-coordinate-grandchild"


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(text: str, *, timestamp: str) -> dict[str, object]:
    """Build one user turn."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {"content": text},
    }


def assistant(
    message_id: str,
    *,
    tool_id: str,
    tool_name: str,
    tool_input: dict[str, object],
    timestamp: str,
) -> dict[str, object]:
    """Build one assistant record with a single trigger call."""
    return {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {"type": "text", "text": "synthetic answer"},
                {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input},
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    }


def prompt_snapshot(agent_id: str, body: str) -> dict[str, object]:
    """Build one child Agent definition snapshot."""
    return {
        "type": "prompt_snapshot",
        "sessionId": ROOT_ID,
        "agentId": agent_id,
        "systemPrompt": [body],
    }


def meta(*, agent_type: str, tool_use_id: str, description: str) -> dict[str, object]:
    """Build one closed child metadata shape."""
    return {
        "agentType": agent_type,
        "description": description,
        "spawnDepth": 1,
        "toolUseId": tool_use_id,
        "isBuiltIn": False,
    }


MAIN_CONTENT = jsonl(
    user("coordinate task", timestamp="2026-11-16T01:00:00Z"),
    assistant(
        "message-main-1",
        tool_id="tool-child-one",
        tool_name="Agent",
        tool_input={"subagent_type": "reviewer", "agentVersion": "v1"},
        timestamp="2026-11-16T01:01:00Z",
    ),
    assistant(
        "message-main-2",
        tool_id="tool-child-two",
        tool_name="Agent",
        tool_input={"subagent_type": "planner"},
        timestamp="2026-11-16T01:02:00Z",
    ),
)
CHILD_ONE_CONTENT = jsonl(
    prompt_snapshot(CHILD_ONE, "You are a synthetic reviewer."),
    user("review this", timestamp="2026-11-16T01:03:00Z"),
    assistant(
        "message-child-1",
        tool_id="tool-grandchild",
        tool_name="Agent",
        tool_input={"subagent_type": "worker"},
        timestamp="2026-11-16T01:04:00Z",
    ),
)
CHILD_TWO_CONTENT = jsonl(
    prompt_snapshot(CHILD_TWO, "You are a synthetic planner."),
    user("plan this", timestamp="2026-11-16T01:05:00Z"),
)
GRANDCHILD_CONTENT = jsonl(
    prompt_snapshot(GRANDCHILD, "You are a synthetic worker."),
    user("work this", timestamp="2026-11-16T01:06:00Z"),
)


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database for one replay test."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'coordinates.db'}",
    )


async def seed_payload(
    database: Database,
    *,
    agent_id: str,
    agent_kind: Literal["main", "subagent"],
    content: str,
    agent_meta: dict[str, object] | None,
) -> None:
    """Insert one raw payload as an external pull would."""
    async with database.transaction() as session:
        await session.execute(
            trajectory_payloads.insert().values(
                runtime_key="claude-code",
                root_session_id=ROOT_ID,
                agent_id=agent_id,
                agent_kind=agent_kind,
                payload=content,
                agent_meta=agent_meta,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                line_count=len(content.splitlines()),
                source_type="script",
                updated_at=datetime(2026, 11, 16, 2, tzinfo=UTC),
            ),
        )


async def test_replay_persists_trigger_coordinates_and_object_revisions(
    tmp_path: Path,
) -> None:
    """Replay writes DFS tree indexes, trigger timestamps, versions, and revisions."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(
            database,
            agent_id=ROOT_ID,
            agent_kind="main",
            content=MAIN_CONTENT,
            agent_meta=None,
        )
        await seed_payload(
            database,
            agent_id=CHILD_ONE,
            agent_kind="subagent",
            content=CHILD_ONE_CONTENT,
            agent_meta=meta(
                agent_type="reviewer",
                tool_use_id="tool-child-one",
                description="review",
            ),
        )
        await seed_payload(
            database,
            agent_id=CHILD_TWO,
            agent_kind="subagent",
            content=CHILD_TWO_CONTENT,
            agent_meta=meta(
                agent_type="planner",
                tool_use_id="tool-child-two",
                description="plan",
            ),
        )
        await seed_payload(
            database,
            agent_id=GRANDCHILD,
            agent_kind="subagent",
            content=GRANDCHILD_CONTENT,
            agent_meta=meta(
                agent_type="worker",
                tool_use_id="tool-grandchild",
                description="work",
            ),
        )

        result = await replay_pending_payloads(database)

        async with database.session() as session:
            node_rows = (await session.execute(select(agents))).mappings().all()
            event_rows = (await session.execute(select(agent_events))).mappings().all()

        assert result.root_sessions == 1
        assert result.imported == 4
        tree_index = {str(row["id"]): int(row["tree_index"]) for row in node_rows}
        assert tree_index == {
            ROOT_ID: 0,
            CHILD_ONE: 1,
            GRANDCHILD: 2,
            CHILD_TWO: 3,
        }
        events = {(str(row["agent_id"]), str(row["name"])): row for row in event_rows}
        child_one_event = events[(ROOT_ID, "reviewer")]
        child_two_event = events[(ROOT_ID, "planner")]
        grandchild_event = events[(CHILD_ONE, "worker")]
        assert child_one_event["object_version"] == "v1"
        assert child_one_event["object_revision"] == "tag:v1"
        assert child_one_event["triggered_at"] is not None
        assert child_two_event["object_version"] is None
        assert str(child_two_event["object_revision"]).startswith("digest:")
        assert grandchild_event["object_version"] is None
        assert str(grandchild_event["object_revision"]).startswith("digest:")
        assert all(row["triggered_at"] is not None for row in event_rows)
    finally:
        await database.dispose()


def test_agent_revision_matches_replayed_event_revision() -> None:
    """The event revision is the child definition identity, stable across tasks."""
    first = normalize_transcript(
        CHILD_TWO_CONTENT,
        root_session_id=ROOT_ID,
        agent_id=CHILD_TWO,
        agent_kind="subagent",
        agent_meta=meta(
            agent_type="planner",
            tool_use_id="tool-child-two",
            description="plan",
        ),
    )
    second = normalize_transcript(
        jsonl(
            prompt_snapshot(CHILD_TWO, "You are a synthetic planner."),
            user("a different task", timestamp="2026-11-16T01:07:00Z"),
        ),
        root_session_id=ROOT_ID,
        agent_id=CHILD_TWO,
        agent_kind="subagent",
        agent_meta=meta(
            agent_type="planner",
            tool_use_id="tool-child-two",
            description="another plan",
        ),
    )

    assert first.agent_revision is not None
    assert first.agent_revision == second.agent_revision
