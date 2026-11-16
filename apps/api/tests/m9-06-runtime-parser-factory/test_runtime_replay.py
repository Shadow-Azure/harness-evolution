"""Replay selection, per-runtime versions, and unknown-runtime contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agents,
    session_families,
    source_records,
    sync_runs,
    trajectory_payloads,
)
from app.service.acquisition.parsers import (
    AgentMetaFacts,
    BaseTraceParser,
    ParseContext,
    TraceParserFactory,
)
from app.service.acquisition.parsers.base import _dict, _string
from app.service.acquisition.replay import replay_pending_payloads

FAKE_ROOT = "33333333-3333-4333-8333-333333333333"
FAKE_SUB = "f1111111111111111"
CLAUDE_ROOT = "44444444-4444-4444-8444-444444444444"


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database for one runtime replay test."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'runtime-replay.db'}",
    )


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL content."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def fake_main_payload() -> str:
    """Return a complete fake-runtime main transcript with one Skill trigger."""
    return jsonl(
        {
            "event": "user",
            "at": "2026-10-22T01:00:00Z",
            "prompt": "fake runtime prompt",
        },
        {
            "event": "assistant",
            "id": "fake-main-message",
            "model": "fake-model",
            "at": "2026-10-22T01:01:00Z",
            "usage": {"input_tokens": 4, "output_tokens": 2},
            "tool": {
                "id": "tool-fake-agent",
                "name": "fake-agent",
                "description": "private fake trigger",
            },
        },
    )


def fake_sub_payload() -> str:
    """Return one fake-runtime subagent transcript."""
    return jsonl(
        {
            "event": "assistant",
            "id": "fake-sub-message",
            "model": "fake-child-model",
            "at": "2026-10-22T01:02:00Z",
            "usage": {"input_tokens": 3, "output_tokens": 1},
        },
    )


def claude_main_payload() -> str:
    """Return a minimal complete Claude root for the untouched runtime."""
    return jsonl(
        {
            "type": "user",
            "sessionId": CLAUDE_ROOT,
            "timestamp": "2026-10-22T02:00:00Z",
            "message": {"content": "claude prompt"},
        },
        {
            "type": "assistant",
            "sessionId": CLAUDE_ROOT,
            "timestamp": "2026-10-22T02:01:00Z",
            "message": {
                "id": "claude-main-message",
                "model": "claude-model",
                "content": [],
                "usage": {"input_tokens": 2, "output_tokens": 1},
            },
        },
    )


class FakeTraceParser(BaseTraceParser):
    """Minimal second runtime proving parser selection without factory edits."""

    runtime_key = "fake-runtime"
    parser_version = 1

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        """Interpret a tiny event schema independent of Claude field names."""
        event = record.get("event")
        timestamp = ctx.observe_timestamp(record.get("at"))
        if event == "user":
            prompt = _string(record.get("prompt"))
            if prompt is not None:
                ctx.record_user_turn(prompt, timestamp, line_no)
            ctx.mark_user_input()
            return
        if event != "assistant":
            return
        ctx.mark_assistant_record(fatal_error_unrecovered=False)
        message_offset = ctx.record_assistant_message(
            message_id=_string(record.get("id")),
            model=_string(record.get("model")),
            usage=_dict(record.get("usage")),
        )
        tool = _dict(record.get("tool"))
        if tool:
            ctx.record_tool_use(
                line_no=line_no,
                message_offset=message_offset,
                tool_use_id=_string(tool.get("id")),
                name=_string(tool.get("name")),
                trigger_kind="agent",
                description=_string(tool.get("description")),
            )

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        """Read the generic subagent hints used by the fake fixture."""
        depth = meta.get("spawnDepth")
        return AgentMetaFacts(
            agent_type=_string(meta.get("agentType")),
            parent_tool_use_id=_string(meta.get("toolUseId")),
            spawn_depth=depth if isinstance(depth, int) and depth >= 0 else 0,
        )


@pytest.fixture
def fake_runtime() -> Iterator[type[FakeTraceParser]]:
    """Register one test runtime and restore the production registry afterwards."""
    saved = dict(TraceParserFactory._parsers)
    TraceParserFactory.register(FakeTraceParser)
    try:
        yield FakeTraceParser
    finally:
        TraceParserFactory._parsers.clear()
        TraceParserFactory._parsers.update(saved)


async def insert_payload(
    database: Database,
    *,
    runtime_key: str,
    root_id: str,
    agent_id: str,
    agent_kind: str,
    content: str,
    meta: dict[str, object] | None = None,
) -> None:
    """Insert one raw payload under its runtime identity."""
    digest = hashlib.sha256(content.encode()).hexdigest()
    async with database.transaction() as session:
        await session.execute(
            trajectory_payloads.insert().values(
                runtime_key=runtime_key,
                root_session_id=root_id,
                agent_id=agent_id,
                agent_kind=agent_kind,
                payload=content,
                agent_meta=meta,
                content_hash=digest,
                line_count=content.count("\n"),
                source_type="script",
                updated_at=datetime(2026, 10, 22, 1, tzinfo=UTC),
            ),
        )


async def seed_fake_root(database: Database) -> None:
    """Write one complete fake-runtime root with a linked child."""
    await insert_payload(
        database,
        runtime_key="fake-runtime",
        root_id=FAKE_ROOT,
        agent_id=FAKE_ROOT,
        agent_kind="main",
        content=fake_main_payload(),
    )
    await insert_payload(
        database,
        runtime_key="fake-runtime",
        root_id=FAKE_ROOT,
        agent_id=FAKE_SUB,
        agent_kind="subagent",
        content=fake_sub_payload(),
        meta={"agentType": "Fake", "spawnDepth": 1, "toolUseId": "tool-fake-agent"},
    )


async def test_registered_fake_runtime_replays_with_its_identity(
    tmp_path: Path,
    fake_runtime: type[FakeTraceParser],
) -> None:
    """The factory-selected parser owns payload, cursor, and session identity."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_fake_root(database)

        result = await replay_pending_payloads(database)

        assert result.root_sessions == 1
        assert result.imported == 2
        assert result.errors == 0
        async with database.session() as session:
            family = (
                (
                    await session.execute(
                        select(session_families).where(session_families.c.id == FAKE_ROOT),
                    )
                )
                .mappings()
                .one()
            )
            sources = (await session.execute(select(source_records))).mappings().all()
            agent_ids = set(
                cast(
                    list[str],
                    (
                        await session.execute(
                            select(agents.c.id).where(agents.c.root_session_id == FAKE_ROOT),
                        )
                    )
                    .scalars()
                    .all(),
                ),
            )
        assert family["runtime_key"] == "fake-runtime"
        assert family["title"] == "fake runtime prompt"
        assert {source["runtime_key"] for source in sources} == {"fake-runtime"}
        assert {source["parser_version"] for source in sources} == {1}
        assert agent_ids == {FAKE_ROOT, FAKE_SUB}
    finally:
        await database.dispose()


async def test_parser_upgrade_replays_only_that_runtime(
    tmp_path: Path,
    fake_runtime: type[FakeTraceParser],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake-runtime version bump leaves the Claude cursor and tree untouched."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_fake_root(database)
        await insert_payload(
            database,
            runtime_key="claude-code",
            root_id=CLAUDE_ROOT,
            agent_id=CLAUDE_ROOT,
            agent_kind="main",
            content=claude_main_payload(),
        )
        first = await replay_pending_payloads(database)
        async with database.session() as session:
            claude_before = (
                (
                    await session.execute(
                        select(session_families).where(
                            session_families.c.id == CLAUDE_ROOT,
                        ),
                    )
                )
                .mappings()
                .one()
            )

        monkeypatch.setattr(fake_runtime, "parser_version", 2)
        upgraded = await replay_pending_payloads(database)

        assert first.imported == 3
        assert upgraded.imported == 2
        assert upgraded.skipped == 1
        async with database.session() as session:
            claude_after = (
                (
                    await session.execute(
                        select(session_families).where(
                            session_families.c.id == CLAUDE_ROOT,
                        ),
                    )
                )
                .mappings()
                .one()
            )
            versions = {
                (source["runtime_key"], source["parser_version"])
                for source in (await session.execute(select(source_records))).mappings().all()
            }
        assert claude_after["updated_at"] == claude_before["updated_at"]
        assert versions == {("claude-code", 2), ("fake-runtime", 2)}
    finally:
        await database.dispose()


async def test_unknown_runtime_fails_without_writing_tree_or_fallback(
    tmp_path: Path,
) -> None:
    """An unknown runtime is a stable diagnostic and never reaches Claude."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await insert_payload(
            database,
            runtime_key="unknown-runtime",
            root_id=FAKE_ROOT,
            agent_id=FAKE_ROOT,
            agent_kind="main",
            content=fake_main_payload(),
        )

        result = await replay_pending_payloads(database)

        assert result.imported == 0
        assert result.failed == 1
        assert result.errors == 1
        async with database.session() as session:
            families = (await session.execute(select(session_families.c.id))).all()
            sources = (await session.execute(select(source_records.c.id))).all()
            run = (
                (
                    await session.execute(
                        select(sync_runs).where(sync_runs.c.id == result.sync_run_id),
                    )
                )
                .mappings()
                .one()
            )
        assert families == []
        assert sources == []
        assert run["status"] == "completed"
        assert run["errors"][0]["code"] == "UNSUPPORTED_RUNTIME"
        assert run["errors"][0]["message"] == "Unsupported trace runtime: unknown-runtime"
        assert "fake runtime prompt" not in repr(run["errors"])
    finally:
        await database.dispose()
