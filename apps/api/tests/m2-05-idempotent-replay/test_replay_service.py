"""Idempotent root-level replay contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import delete, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    session_families,
    source_records,
    sync_runs,
    trajectory_payloads,
    user_turns,
)
from app.service.acquisition.normalize import CURRENT_PARSER_VERSION
from app.service.acquisition.replay import replay_pending_payloads

ROOT_A = "11111111-1111-4111-8111-111111111111"
SUB_A = "a1111111111111111"
ROOT_B = "22222222-2222-4222-8222-222222222222"
SUB_B = "b1111111111111111"


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database for one replay test."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'replay.db'}",
    )


def jsonl(*records: object | str) -> str:
    """Encode deterministic JSONL content."""
    return (
        "\n".join(
            record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
            for record in records
        )
        + "\n"
    )


def main_payload() -> str:
    """Return a complete root transcript with one user turn and Agent trigger."""
    return jsonl(
        {
            "type": "user",
            "sessionId": ROOT_A,
            "timestamp": "2026-10-20T01:00:00Z",
            "cwd": "/workspace/repository",
            "gitBranch": "main",
            "message": {"content": "private user prompt"},
        },
        {
            "type": "assistant",
            "sessionId": ROOT_A,
            "timestamp": "2026-10-20T01:01:00Z",
            "message": {
                "id": "main-message",
                "model": "main-model",
                "content": [
                    {"type": "text", "text": "private assistant text"},
                    {
                        "type": "tool_use",
                        "id": "tool-agent-a",
                        "name": "Agent",
                        "input": {
                            "description": "private delegated task",
                            "subagent_type": "Explore",
                        },
                    },
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    )


def subagent_payload(*, tokens: int = 7, bad_line: bool = False) -> str:
    """Return one child transcript with a stable parent call."""
    lines: list[object | str] = [
        {
            "type": "assistant",
            "sessionId": ROOT_A,
            "timestamp": "2026-10-20T01:02:00Z",
            "message": {
                "id": "child-message",
                "model": "child-model",
                "content": [{"type": "text", "text": "private child text"}],
                "usage": {"input_tokens": tokens, "output_tokens": 0},
            },
        },
    ]
    if bad_line:
        lines.append("{not-json")
    return jsonl(*lines)


async def insert_payload(
    database: Database,
    *,
    root_id: str,
    agent_id: str,
    agent_kind: str,
    content: str,
    meta: dict[str, object] | None = None,
    create_source: bool = False,
    parser_version: int | None = None,
) -> None:
    """Insert one raw payload and optionally its initial processing index."""
    digest = hashlib.sha256(content.encode()).hexdigest()
    async with database.transaction() as session:
        await session.execute(
            trajectory_payloads.insert().values(
                root_session_id=root_id,
                agent_id=agent_id,
                agent_kind=agent_kind,
                payload=content,
                agent_meta=meta,
                content_hash=digest,
                line_count=content.count("\n"),
                source_type="script",
                updated_at=datetime(2026, 10, 20, 1, tzinfo=UTC),
            ),
        )
        if create_source:
            await session.execute(
                source_records.insert().values(
                    root_session_id=root_id,
                    agent_id=agent_id,
                    kind=agent_kind,
                    source_type="script",
                    line_count=content.count("\n"),
                    received_at=datetime(2026, 10, 20, 1, tzinfo=UTC),
                    processed_at=None,
                    processed_hash=None,
                    parser_version=parser_version,
                    last_sync_run_id=None,
                ),
            )


async def seed_valid_root(database: Database) -> None:
    """Write one complete main/subagent root."""
    await insert_payload(
        database,
        root_id=ROOT_A,
        agent_id=ROOT_A,
        agent_kind="main",
        content=main_payload(),
    )
    await insert_payload(
        database,
        root_id=ROOT_A,
        agent_id=SUB_A,
        agent_kind="subagent",
        content=subagent_payload(),
        meta={
            "agentType": "Explore",
            "description": "private provider description",
            "spawnDepth": 1,
            "toolUseId": "tool-agent-a",
        },
    )


async def counts(database: Database) -> dict[str, int]:
    """Return canonical and cursor row counts."""
    async with database.session() as session:
        return {
            "families": len((await session.execute(select(session_families.c.id))).all()),
            "agents": len((await session.execute(select(agents.c.id))).all()),
            "events": len((await session.execute(select(agent_events.c.id))).all()),
            "turns": len((await session.execute(select(user_turns.c.id))).all()),
            "sources": len((await session.execute(select(source_records.c.id))).all()),
        }


async def test_first_replay_writes_canonical_root_and_cursors(tmp_path: Path) -> None:
    """A pending root is parsed, assembled, written, and marked processed."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)

        result = await replay_pending_payloads(database)

        assert result.root_sessions == 1
        assert result.payloads == 2
        assert result.imported == 2
        assert result.skipped == 0
        assert result.errors == 0
        assert await counts(database) == {
            "families": 1,
            "agents": 2,
            "events": 1,
            "turns": 1,
            "sources": 2,
        }
        async with database.session() as session:
            family = (
                (
                    await session.execute(
                        select(session_families).where(session_families.c.id == ROOT_A)
                    )
                )
                .mappings()
                .one()
            )
            sources = (
                (await session.execute(select(source_records).order_by(source_records.c.agent_id)))
                .mappings()
                .all()
            )
            run = (
                (
                    await session.execute(
                        select(sync_runs).where(sync_runs.c.id == result.sync_run_id)
                    )
                )
                .mappings()
                .one()
            )
        assert family["title"] == "private user prompt"
        assert family["agents_count"] == 1
        assert all(source["processed_hash"] is not None for source in sources)
        assert all(source["parser_version"] == CURRENT_PARSER_VERSION for source in sources)
        assert all(source["last_sync_run_id"] == result.sync_run_id for source in sources)
        assert run["status"] == "completed"
        assert run["records_total"] == 2
        assert run["records_done"] == 2
        assert run["imported"] == 2
        assert run["skipped"] == 0
    finally:
        await database.dispose()


async def test_second_replay_has_zero_side_effects(tmp_path: Path) -> None:
    """An unchanged second run skips everything and preserves processed time."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        original = await replay_pending_payloads(database)
        fixed = datetime(2020, 1, 2, 3, 4, tzinfo=UTC)
        async with database.transaction() as session:
            await session.execute(
                source_records.update().values(
                    processed_at=fixed,
                    last_sync_run_id=original.sync_run_id,
                ),
            )
        before = await counts(database)

        result = await replay_pending_payloads(database)

        assert result.imported == 0
        assert result.skipped == 2
        assert result.errors == 0
        assert await counts(database) == before
        async with database.session() as session:
            sources = (await session.execute(select(source_records))).mappings().all()
        assert {source["last_sync_run_id"] for source in sources} == {
            original.sync_run_id,
        }
        assert {source["processed_at"].replace(tzinfo=None) for source in sources} == {
            fixed.replace(tzinfo=None)
        }
    finally:
        await database.dispose()


async def test_changed_payload_refreshes_source_line_count(tmp_path: Path) -> None:
    """A contents change advances the source index with the current payload shape."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        await replay_pending_payloads(database)
        async with database.session() as session:
            before = (
                (
                    await session.execute(
                        select(source_records).where(source_records.c.agent_id == SUB_A),
                    )
                )
                .mappings()
                .one()
            )

        expanded = subagent_payload() + jsonl(
            {
                "type": "assistant",
                "sessionId": ROOT_A,
                "timestamp": "2026-10-20T01:03:00Z",
                "message": {
                    "id": "child-message-2",
                    "model": "child-model",
                    "content": [{"type": "text", "text": "private second chunk"}],
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                },
            },
        )
        async with database.transaction() as session:
            await session.execute(
                trajectory_payloads.update()
                .where(
                    trajectory_payloads.c.root_session_id == ROOT_A,
                    trajectory_payloads.c.agent_id == SUB_A,
                )
                .values(
                    payload=expanded,
                    content_hash=hashlib.sha256(expanded.encode()).hexdigest(),
                    line_count=expanded.count("\n"),
                ),
            )

        result = await replay_pending_payloads(database)

        assert result.imported == 1
        async with database.session() as session:
            after = (
                (
                    await session.execute(
                        select(source_records).where(source_records.c.agent_id == SUB_A),
                    )
                )
                .mappings()
                .one()
            )
        assert after["line_count"] == 2
        assert after["kind"] == "subagent"
        assert after["source_type"] == "script"
        assert after["id"] == before["id"]
        assert after["received_at"] == before["received_at"]
        assert after["processed_hash"] != before["processed_hash"]
    finally:
        await database.dispose()


async def test_new_child_and_parser_upgrade_rebuild_only_affected_root(
    tmp_path: Path,
) -> None:
    """A changed root is rebuilt while another root's cursor and tree stay stable."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        await insert_payload(
            database,
            root_id=ROOT_B,
            agent_id=ROOT_B,
            agent_kind="main",
            content=main_payload().replace(ROOT_A, ROOT_B).replace("tool-agent-a", "tool-b"),
        )
        await replay_pending_payloads(database)
        async with database.session() as session:
            root_b_before = (
                (
                    await session.execute(
                        select(session_families).where(session_families.c.id == ROOT_B),
                    )
                )
                .mappings()
                .one()
            )

        await insert_payload(
            database,
            root_id=ROOT_A,
            agent_id="a2222222222222222",
            agent_kind="subagent",
            content=subagent_payload(tokens=11).replace("child-message", "child-two"),
            meta={
                "agentType": "Explore",
                "spawnDepth": 1,
                "toolUseId": "tool-agent-a",
            },
        )
        result = await replay_pending_payloads(database)

        assert result.imported == 1
        async with database.session() as session:
            root_a_agents = cast(
                list[str],
                (
                    await session.execute(
                        select(agents.c.id).where(agents.c.root_session_id == ROOT_A),
                    )
                )
                .scalars()
                .all(),
            )
            root_b_after = (
                (
                    await session.execute(
                        select(session_families).where(session_families.c.id == ROOT_B),
                    )
                )
                .mappings()
                .one()
            )
        assert set(root_a_agents) == {ROOT_A, SUB_A, "a2222222222222222"}
        assert root_b_after["updated_at"] == root_b_before["updated_at"]
        assert root_b_after["tokens_total"] == root_b_before["tokens_total"]

        async with database.transaction() as session:
            await session.execute(
                source_records.update()
                .where(source_records.c.root_session_id == ROOT_A)
                .values(parser_version=CURRENT_PARSER_VERSION - 1),
            )
        upgraded = await replay_pending_payloads(database)
        assert upgraded.imported == 3
    finally:
        await database.dispose()


async def test_bad_line_is_processed_but_sanitized(tmp_path: Path) -> None:
    """A recoverable bad line still writes the tree and a stable issue."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await insert_payload(
            database,
            root_id=ROOT_A,
            agent_id=ROOT_A,
            agent_kind="main",
            content=main_payload(),
        )
        await insert_payload(
            database,
            root_id=ROOT_A,
            agent_id=SUB_A,
            agent_kind="subagent",
            content=subagent_payload(bad_line=True),
            meta={"agentType": "Explore", "toolUseId": "tool-agent-a"},
        )

        result = await replay_pending_payloads(database)

        assert result.errors == 1
        async with database.session() as session:
            run = (
                (
                    await session.execute(
                        select(sync_runs).where(sync_runs.c.id == result.sync_run_id)
                    )
                )
                .mappings()
                .one()
            )
            sources = (await session.execute(select(source_records))).mappings().all()
        assert run["status"] == "completed"
        assert run["errors"][0]["code"] == "INVALID_JSONL_LINE"
        assert "private" not in repr(run["errors"]).lower()
        assert all(source["processed_hash"] is not None for source in sources)
    finally:
        await database.dispose()


async def test_structural_failure_isolated_and_keeps_old_cursor(tmp_path: Path) -> None:
    """A broken root rolls back while a healthy root in the same batch completes."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        await insert_payload(
            database,
            root_id=ROOT_B,
            agent_id=SUB_B,
            agent_kind="subagent",
            content=subagent_payload(),
        )

        result = await replay_pending_payloads(database)

        assert result.root_sessions == 1
        assert result.imported == 2
        assert result.failed == 1
        assert result.errors == 1
        async with database.session() as session:
            broken_source = (
                (
                    await session.execute(
                        select(source_records).where(
                            source_records.c.root_session_id == ROOT_B,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
            run = (
                (
                    await session.execute(
                        select(sync_runs).where(sync_runs.c.id == result.sync_run_id)
                    )
                )
                .mappings()
                .one()
            )
        assert broken_source is None
        assert run["errors"][0]["code"] == "MISSING_MAIN_AGENT"
        assert run["errors"][0]["sessionId"] == ROOT_B
    finally:
        await database.dispose()


async def test_missing_source_is_created_and_payload_deletion_is_non_destructive(
    tmp_path: Path,
) -> None:
    """Replay creates absent cursors and never deletes a still-persisted tree."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        await replay_pending_payloads(database)
        before = await counts(database)
        async with database.session() as session:
            source_before = cast(
                list[datetime],
                (await session.execute(select(source_records.c.received_at))).scalars().all(),
            )

        async with database.transaction() as session:
            await session.execute(
                delete(trajectory_payloads).where(
                    trajectory_payloads.c.root_session_id == ROOT_A,
                    trajectory_payloads.c.agent_id == SUB_A,
                ),
            )
        result = await replay_pending_payloads(database)

        assert result.imported == 0
        assert await counts(database) == before
        async with database.session() as session:
            source_after = cast(
                list[datetime],
                (await session.execute(select(source_records.c.received_at))).scalars().all(),
            )
        assert source_after == source_before
    finally:
        await database.dispose()


async def test_missing_source_rows_are_backfilled_at_discovery_time(tmp_path: Path) -> None:
    """A payload without an index gains an honest first-discovery timestamp."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        result = await replay_pending_payloads(database)

        async with database.session() as session:
            source = (
                (
                    await session.execute(
                        select(source_records).where(source_records.c.agent_id == SUB_A),
                    )
                )
                .mappings()
                .one()
            )
            run = (
                (
                    await session.execute(
                        select(sync_runs).where(sync_runs.c.id == result.sync_run_id)
                    )
                )
                .mappings()
                .one()
            )
        assert source["received_at"] is not None
        assert source["processed_hash"] is not None
        assert cast(list[dict[str, object]], run["errors"]) == []
    finally:
        await database.dispose()


async def test_replay_reports_progress_for_successful_and_failed_roots(
    tmp_path: Path,
) -> None:
    """The optional job callback observes every processed root exactly once."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_valid_root(database)
        await insert_payload(
            database,
            root_id=ROOT_B,
            agent_id=SUB_B,
            agent_kind="subagent",
            content=subagent_payload(),
        )
        progress: list[tuple[int, int]] = []

        async def on_progress(done: int, total: int) -> None:
            progress.append((done, total))

        await replay_pending_payloads(database, on_progress=on_progress)

        assert progress == [(2, 3), (3, 3)]
    finally:
        await database.dispose()
