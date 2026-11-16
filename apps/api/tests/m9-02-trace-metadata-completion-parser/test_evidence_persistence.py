"""M9-02 evidence persistence through the replay pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    session_families,
    sync_runs,
    trajectory_payloads,
)
from app.service.acquisition.local_sessions import scan_local_sessions
from app.service.acquisition.replay import replay_pending_payloads

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures" / "m9-real-shape"
ROOT_ID = "40000000-0000-4000-8000-000000000001"
AGENT_ID = "m902review0001"


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database for one replay test."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'evidence.db'}",
    )


async def test_replay_persists_completion_and_definition_evidence(tmp_path: Path) -> None:
    """Replay writes the parsed completion, definition, and Skill body evidence."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        corpus = scan_local_sessions(FIXTURE_ROOT)
        async with database.transaction() as session:
            for payload in corpus.payloads:
                await session.execute(
                    trajectory_payloads.insert().values(
                        runtime_key=payload.runtime_key,
                        root_session_id=payload.root_session_id,
                        agent_id=payload.agent_id,
                        agent_kind=payload.agent_kind,
                        payload=payload.content,
                        agent_meta=payload.agent_meta,
                        content_hash=payload.content_hash,
                        line_count=payload.line_count,
                        source_type="script",
                        updated_at=datetime(2026, 11, 14, 2, tzinfo=UTC),
                    ),
                )

        result = await replay_pending_payloads(database)

        assert result.root_sessions == 1
        assert result.imported == 2
        assert result.errors >= 3
        async with database.session() as session:
            family = (
                (
                    await session.execute(
                        select(session_families).where(session_families.c.id == ROOT_ID),
                    )
                )
                .mappings()
                .one()
            )
            nodes = (
                (await session.execute(select(agents).order_by(agents.c.sort_key))).mappings().all()
            )
            events = (await session.execute(select(agent_events))).mappings().all()
            run = (
                (
                    await session.execute(
                        select(sync_runs).where(sync_runs.c.id == result.sync_run_id),
                    )
                )
                .mappings()
                .one()
            )

        assert family["status"] == "ok"
        assert family["execution_outcome"] == "interrupted"
        assert family["end_reason"] == "tool_use_open"
        by_id = {node["id"]: node for node in nodes}
        assert by_id[ROOT_ID]["execution_outcome"] == "interrupted"
        assert by_id[ROOT_ID]["end_reason"] == "tool_use_open"
        assert by_id[ROOT_ID]["agent_definition_hash"] is None
        assert by_id[AGENT_ID]["execution_outcome"] == "interrupted"
        assert by_id[AGENT_ID]["end_reason"] == "missing_report"
        assert by_id[AGENT_ID]["definition_source"] == "prompt_snapshot"
        assert by_id[AGENT_ID]["agent_definition_hash"] is not None
        skill_event = next(event for event in events if event["kind"] == "skill")
        assert skill_event["definition_hash"] is not None
        codes = {item["code"] for item in run["errors"] if isinstance(item, dict)}
        assert {"TOOL_USE_OPEN", "MISSING_FINAL_REPORT", "TASK_SNAPSHOT_PENDING"} <= codes
    finally:
        await database.dispose()
