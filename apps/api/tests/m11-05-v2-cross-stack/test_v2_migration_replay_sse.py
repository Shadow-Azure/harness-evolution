"""Migration, combined real-shape replay, and one-shot SSE acceptance.

The replay fixture deliberately carries every V2 evidence kind in one root
session: an explicit Skill call with a tag revision, one Agent call with its
tool result (``authoritative`` parent evidence), one Agent call without the
result (``derived`` parent evidence), and one knowledge-base ``Read``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Response
from sqlalchemy import inspect, select, text, update
from sqlalchemy.engine import Connection

from app.api import events as events_api
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    bad_cases,
    session_families,
    source_records,
    trajectory_payloads,
)
from app.db.models.workspace import workspaces
from app.service.acquisition.replay import replay_pending_payloads
from app.utils.definition import definition_hash
from app.utils.knowledge_paths import knowledge_document_id
from tests.m10_02_potential_support import seed_case, seed_workspace
from tests.v2_acceptance_support import (
    AcceptanceApi,
    migrated_database,
    seed_identity,
    seed_run,
)
from tests.v2_acceptance_support import acceptance_api as acceptance_api

API_ROOT = Path(__file__).resolve().parents[2]
ROOT_ID = "61000000-0000-4000-8000-000000000001"
WORKSPACE_ID = "ws-m11-05-replay"
SSE_WORKSPACE = "ws-m11-05-sse"
SSE_RUN = "run-m11-05-sse"
TARGET_NAME = "deep-research"
TARGET_VERSION = "v2.0.0"
CHILD_AUTHORITATIVE = "agent-m11-05-authoritative"
CHILD_DERIVED = "agent-m11-05-derived"
PARENT_TOOL = "tool-m11-05-parent"
DERIVED_TOOL = "tool-m11-05-derived"
KNOWLEDGE_ROOT = "/workspace/knowledge"
KNOWLEDGE_PATH = f"{KNOWLEDGE_ROOT}/guides/runbook.md"
KNOWLEDGE_CONTENT = "Runbook\nbody\n"
REPLAY_CASE = "case-m11-05-replay"
PAYLOAD_TIME = datetime(2026, 11, 16, 2, tzinfo=UTC)
SECONDS = "2026-11-16T01:00:00Z"


@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    """Reflected table, column, and named-unique data for one database."""

    tables: frozenset[str]
    columns: dict[str, frozenset[str]]
    uniques: dict[str, dict[str, frozenset[str]]]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool-use block carried by an assistant record."""

    tool_id: str
    name: str
    tool_input: dict[str, object]


def _snapshot(connection: Connection) -> SchemaSnapshot:
    """Reflect the V2 schema without mutating the database."""
    inspector = inspect(connection)
    tables = frozenset(inspector.get_table_names())
    columns = {
        table: frozenset(str(column["name"]) for column in inspector.get_columns(table))
        for table in tables
    }
    uniques = {
        table: {
            str(unique["name"]): frozenset(str(column) for column in unique["column_names"])
            for unique in inspector.get_unique_constraints(table)
            if unique.get("name") is not None
        }
        for table in tables
    }
    return SchemaSnapshot(tables=tables, columns=columns, uniques=uniques)


def _expected_head() -> str:
    """Return the Alembic head revision from the checked-in migration tree."""
    config = Config(str(API_ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _assert_v2_schema(snapshot: SchemaSnapshot, version: str) -> None:
    """Assert the V2 tables, columns, and link identity constraints exist."""
    assert version == _expected_head()
    assert {
        "workspaces",
        "workspace_members",
        "workspace_ingest_credentials",
        "evolution_run_candidates",
    } <= snapshot.tables
    assert {
        "object_revision",
        "triggered_at",
        "relation_confidence",
        "document_id",
        "document_revision",
        "source_path",
        "retrieval_kind",
        "retrieval_scope",
    } <= snapshot.columns["agent_events"]
    # Tree order lives on the Agent node; events carry the coordinates it pairs with.
    assert "tree_index" in snapshot.columns["agents"]
    assert snapshot.uniques["bad_case_analysis"]["uq_bad_case_analysis_case_probe"] == (
        frozenset({"bad_case_id", "probe_id"})
    )
    assert {"workspace_id", "conclusion", "cache_key", "reused_count"} <= snapshot.columns[
        "probe_reports"
    ]
    assert {"potential_policy", "cache_enabled", "attribution_engine"} <= snapshot.columns[
        "evolution_runs"
    ]
    assert {
        "workspace_id",
        "included",
        "included_reason",
        "order_state",
        "probe_id",
        "is_cached",
    } <= snapshot.columns["evolution_run_candidates"]


async def test_fresh_sqlite_upgrades_to_head_with_v2_schema(tmp_path: Path) -> None:
    """One empty SQLite file runs every migration and exposes the V2 schema."""
    database = await migrated_database(tmp_path, "m11-05-schema.db")
    try:
        async with database.engine.connect() as connection:
            version: str = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            snapshot = await connection.run_sync(_snapshot)
    finally:
        await database.dispose()

    assert isinstance(version, str)
    _assert_v2_schema(snapshot, version)


@pytest.mark.mysql
async def test_mysql_upgrades_to_the_same_head_and_v2_schema() -> None:
    """The same V2 schema assertions run against a configured MySQL service."""
    url = os.environ.get("HE_DB_URL", "")
    if not url.startswith("mysql+asyncmy://"):
        if os.environ.get("HE_REQUIRE_MYSQL") == "1":
            pytest.fail("HE_DB_URL must point to MySQL when HE_REQUIRE_MYSQL=1")
        pytest.skip("MySQL integration requires HE_DB_URL")
    database = create_database(Settings(db_dialect=DatabaseDialect.MYSQL, db_url=url))
    await database.start()
    try:
        await upgrade_database(database)
        async with database.engine.connect() as connection:
            version: str = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            snapshot = await connection.run_sync(_snapshot)
    finally:
        await database.dispose()

    assert isinstance(version, str)
    _assert_v2_schema(snapshot, version)


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(text_value: str, *, timestamp: str = SECONDS) -> dict[str, object]:
    """Build one root user record."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {"content": text_value},
    }


def assistant(
    message_id: str,
    *,
    calls: tuple[ToolCall, ...] = (),
    stop_reason: str = "end_turn",
    timestamp: str = SECONDS,
) -> dict[str, object]:
    """Build one assistant record with explicit tool-use blocks."""
    content: list[dict[str, object]] = [{"type": "text", "text": "synthetic answer"}]
    for call in calls:
        content.append(
            {
                "type": "tool_use",
                "id": call.tool_id,
                "name": call.name,
                "input": call.tool_input,
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


def tool_result(tool_id: str, *, timestamp: str = SECONDS) -> dict[str, object]:
    """Build one user record carrying a tool result."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": "synthetic result",
                },
            ],
        },
    }


def read_call(
    tool_id: str,
    path: str,
    *,
    timestamp: str = SECONDS,
) -> dict[str, object]:
    """Build one assistant record holding a single Read call."""
    return assistant(
        f"message-{tool_id}",
        calls=(ToolCall(tool_id, "Read", {"file_path": path}),),
        stop_reason="tool_use",
        timestamp=timestamp,
    )


def read_result(
    tool_id: str,
    path: str,
    content: str,
    *,
    timestamp: str = SECONDS,
) -> dict[str, object]:
    """Build one complete Read tool result carrying file content."""
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
                "startLine": 1,
                "numLines": content.count("\n"),
                "totalLines": content.count("\n"),
            },
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


def child_meta(*, agent_type: str, tool_use_id: str, description: str) -> dict[str, object]:
    """Build one closed child metadata shape carrying strong parent identity."""
    return {
        "agentType": agent_type,
        "description": description,
        "spawnDepth": 1,
        "toolUseId": tool_use_id,
        "isBuiltIn": False,
    }


def _main_content() -> str:
    """Build the combined root trace with Skill, Agent, and knowledge triggers."""
    return jsonl(
        user("synthetic cross-stack task"),
        assistant(
            "message-skill",
            calls=(
                ToolCall(
                    "tool-skill",
                    "Skill",
                    {"skill": TARGET_NAME, "skillVersion": TARGET_VERSION},
                ),
            ),
            stop_reason="tool_use",
            timestamp="2026-11-16T01:01:00Z",
        ),
        tool_result("tool-skill", timestamp="2026-11-16T01:02:00Z"),
        assistant(
            "message-parent",
            calls=(
                ToolCall(
                    PARENT_TOOL,
                    "Agent",
                    {"subagent_type": "Explore", "description": "authoritative child"},
                ),
            ),
            stop_reason="tool_use",
            timestamp="2026-11-16T01:03:00Z",
        ),
        tool_result(PARENT_TOOL, timestamp="2026-11-16T01:04:00Z"),
        assistant(
            "message-derived",
            calls=(
                ToolCall(
                    DERIVED_TOOL,
                    "Agent",
                    {"subagent_type": "Planner", "description": "derived child"},
                ),
            ),
            stop_reason="tool_use",
            timestamp="2026-11-16T01:05:00Z",
        ),
        read_call("tool-knowledge", KNOWLEDGE_PATH, timestamp="2026-11-16T01:06:00Z"),
        read_result(
            "tool-knowledge",
            KNOWLEDGE_PATH,
            KNOWLEDGE_CONTENT,
            timestamp="2026-11-16T01:07:00Z",
        ),
        assistant("message-final", timestamp="2026-11-16T01:08:00Z"),
    )


def _payloads() -> list[dict[str, object]]:
    """Build the three real-shape payloads of the combined replay fixture."""
    main = _main_content()
    authoritative = jsonl(
        prompt_snapshot(CHILD_AUTHORITATIVE, "You are a synthetic reviewer."),
        user("review this", timestamp="2026-11-16T01:09:00Z"),
    )
    derived = jsonl(
        prompt_snapshot(CHILD_DERIVED, "You are a synthetic planner."),
        user("plan this", timestamp="2026-11-16T01:10:00Z"),
    )
    return [
        _payload(ROOT_ID, "main", main, None),
        _payload(
            CHILD_AUTHORITATIVE,
            "subagent",
            authoritative,
            child_meta(
                agent_type="Explore",
                tool_use_id=PARENT_TOOL,
                description="authoritative child",
            ),
        ),
        _payload(
            CHILD_DERIVED,
            "subagent",
            derived,
            child_meta(
                agent_type="Planner",
                tool_use_id=DERIVED_TOOL,
                description="derived child",
            ),
        ),
    ]


def _payload(
    agent_id: str,
    agent_kind: str,
    content: str,
    agent_meta: dict[str, object] | None,
) -> dict[str, object]:
    """Build one raw payload row as an external pull would insert it."""
    return {
        "runtime_key": "claude-code",
        "root_session_id": ROOT_ID,
        "agent_id": agent_id,
        "agent_kind": agent_kind,
        "payload": content,
        "agent_meta": agent_meta,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "line_count": len(content.splitlines()),
        "source_type": "script",
        "updated_at": PAYLOAD_TIME,
    }


async def _seed_replay(database: Database) -> None:
    """Seed one knowledge-rooted workspace, its reported case, and the payloads."""
    await seed_workspace(database, WORKSPACE_ID)
    async with database.transaction() as session:
        await session.execute(
            update(workspaces)
            .where(workspaces.c.id == WORKSPACE_ID)
            .values(knowledge_roots=[KNOWLEDGE_ROOT]),
        )
    await seed_case(
        database,
        case_id=REPLAY_CASE,
        session_id=ROOT_ID,
        workspace_id=WORKSPACE_ID,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=datetime(2026, 11, 16, 2, tzinfo=UTC),
    )
    async with database.transaction() as session:
        for payload in _payloads():
            await session.execute(trajectory_payloads.insert().values(**payload))


async def _replay_rows(
    database: Database,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Return Agent rows keyed by id plus every persisted trigger event."""
    async with database.session() as session:
        agent_rows = (await session.execute(select(agents))).mappings().all()
        event_rows = (await session.execute(select(agent_events))).mappings().all()
    return (
        {str(row["id"]): dict(row) for row in agent_rows},
        [dict(row) for row in event_rows],
    )


def _string_list(values: Iterable[object]) -> list[str]:
    """Convert one iterable of driver scalars into a stable string list."""
    return [str(value) for value in values]


async def test_combined_replay_persists_three_trigger_kinds_and_relations(
    tmp_path: Path,
) -> None:
    """One replay writes Skill, Agent, and knowledge evidence plus relation grades."""
    database = await migrated_database(tmp_path, "m11-05-replay.db")
    try:
        await _seed_replay(database)
        result = await replay_pending_payloads(database)
        agent_rows, events = await _replay_rows(database)
        async with database.session() as session:
            sessions = _string_list(
                (await session.execute(select(session_families.c.id))).scalars().all()
            )
            sources = _string_list(
                (await session.execute(select(source_records.c.agent_id))).scalars().all()
            )
    finally:
        await database.dispose()

    assert result.imported == 3
    assert result.failed == 0
    assert sessions == [ROOT_ID]
    assert set(sources) == {ROOT_ID, CHILD_AUTHORITATIVE, CHILD_DERIVED}
    assert {agent_id: row["tree_index"] for agent_id, row in agent_rows.items()} == {
        ROOT_ID: 0,
        CHILD_AUTHORITATIVE: 1,
        CHILD_DERIVED: 2,
    }
    assert agent_rows[CHILD_AUTHORITATIVE]["parent_agent_id"] == ROOT_ID
    assert agent_rows[CHILD_DERIVED]["parent_agent_id"] == ROOT_ID

    skill = next(row for row in events if row["kind"] == "skill")
    assert skill["agent_id"] == ROOT_ID
    assert skill["name"] == TARGET_NAME
    assert skill["object_version"] == TARGET_VERSION
    assert skill["object_revision"] == f"tag:{TARGET_VERSION}"
    assert skill["triggered_at"] is not None

    by_tool = {str(row["tool_use_id"]): row for row in events if row["kind"] == "agent"}
    authoritative = by_tool[PARENT_TOOL]
    derived = by_tool[DERIVED_TOOL]
    assert authoritative["name"] == "Explore"
    assert authoritative["relation_confidence"] == "authoritative"
    assert authoritative["triggered_at"] is not None
    assert derived["name"] == "Planner"
    assert derived["relation_confidence"] == "derived"
    assert derived["triggered_at"] is not None

    knowledge = next(row for row in events if row["kind"] == "knowledge")
    assert knowledge["agent_id"] == ROOT_ID
    assert knowledge["document_id"] == knowledge_document_id(KNOWLEDGE_PATH, KNOWLEDGE_ROOT)
    normalized = definition_hash(KNOWLEDGE_CONTENT)
    assert normalized is not None
    assert knowledge["document_revision"] == f"digest:{normalized}"
    assert knowledge["source_path"] == KNOWLEDGE_PATH
    assert knowledge["retrieval_kind"] == "file_read"
    assert knowledge["retrieval_scope"] == KNOWLEDGE_ROOT
    assert "document_content" not in knowledge


async def test_combined_replay_is_idempotent_on_rerun(tmp_path: Path) -> None:
    """A second replay of the same payloads adds no Agent, event, or Session rows."""
    database = await migrated_database(tmp_path, "m11-05-idempotent.db")
    try:
        await _seed_replay(database)
        first = await replay_pending_payloads(database)
        before = await _row_counts(database)
        second = await replay_pending_payloads(database)
        after = await _row_counts(database)
    finally:
        await database.dispose()

    assert first.imported == 3
    assert second.imported == 0
    assert second.failed == 0
    assert before == after
    assert after["agents"] == 3


async def _row_counts(database: Database) -> dict[str, int]:
    """Count the rows whose duplication would expose a non-idempotent replay."""
    async with database.session() as session:
        return {
            "agents": len((await session.execute(select(agents.c.id))).scalars().all()),
            "events": len(
                (await session.execute(select(agent_events.c.id))).scalars().all(),
            ),
            "sessions": len(
                (await session.execute(select(session_families.c.id))).scalars().all(),
            ),
            "cases": len(
                (await session.execute(select(bad_cases.c.bad_case_id))).scalars().all(),
            ),
        }


async def test_sse_ticket_is_consumed_exactly_once(
    acceptance_api: AcceptanceApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ticket issued through the API streams once and then answers 401."""
    api = acceptance_api
    await seed_workspace(api.database, SSE_WORKSPACE)
    identity = await seed_identity(
        api.app,
        api.database,
        username="m11-05-sse-admin",
        workspace_id=SSE_WORKSPACE,
        workspace_role="space_admin",
    )
    await seed_run(
        api.database,
        run_id=SSE_RUN,
        workspace_id=SSE_WORKSPACE,
        status="running",
    )

    issued = await api.client.post(
        "/api/events/ticket",
        headers=identity.headers,
        json={
            "topics": [f"run:{SSE_RUN}"],
            "workspaceId": SSE_WORKSPACE,
            "lastEventId": 0,
        },
    )
    assert issued.status_code == 200
    ticket = str(issued.json()["ticket"])

    captured: dict[str, object] = {}

    def capture_response(content: object, **kwargs: object) -> Response:
        """Capture stream wiring without opening a long-lived connection."""
        captured["content"] = content
        captured.update(kwargs)
        return Response(media_type="text/event-stream")

    monkeypatch.setattr(events_api, "EventSourceResponse", capture_response)
    consumed = await api.client.get(f"/api/events?ticket={ticket}")
    replayed = await api.client.get(f"/api/events?ticket={ticket}")

    assert consumed.status_code == 200
    assert consumed.headers["content-type"].startswith("text/event-stream")
    assert captured["ping"] == 0
    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "TICKET_INVALID"
