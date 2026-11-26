"""Project a real JSONL trigger line through the overview read model."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import backfill_legacy_associations
from app.db.crud.overview import OverviewRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import agent_events, bad_cases, trajectory_payloads
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.service.acquisition.local_sessions import scan_local_sessions
from app.service.acquisition.replay import replay_pending_payloads
from app.utils.time import now_shanghai

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures" / "m9-real-shape"
ROOT_ID = "40000000-0000-4000-8000-000000000001"
CASE_ID = "m12-10-real-jsonl"


def _settings(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database for one replay assertion."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'trigger-line.db'}",
    )


async def test_overview_projects_a_real_jsonl_trigger_line(tmp_path: Path) -> None:
    """The stored line comes from a normalized real-shape Skill event."""
    database = create_database(_settings(tmp_path))
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
        await replay_pending_payloads(database)
        async with database.session() as session:
            event = (
                (
                    await session.execute(
                        select(agent_events)
                        .where(agent_events.c.kind == "skill")
                        .order_by(agent_events.c.event_index.desc()),
                    )
                )
                .mappings()
                .first()
            )
        assert event is not None
        trigger_line = int(event["line_no"])
        today = now_shanghai().replace(hour=9, minute=0, second=0, microsecond=0)
        async with database.transaction() as session:
            await session.execute(
                bad_cases.insert().values(
                    bad_case_id=CASE_ID,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    bad_case_session_id=ROOT_ID,
                    bad_case_type="self",
                    object_name=str(event["name"]),
                    object_type="skill",
                    object_version=None,
                    bad_case_agent_id=str(event["agent_id"]),
                    trigger_line=trigger_line,
                    title="real JSONL trigger line",
                    bad_case_description="m12-10 real JSONL line fixture.",
                    meta_data=None,
                    source="m12-10-test",
                    created_at=today,
                    updated_at=today,
                ),
            )
        await backfill_legacy_associations(database)

        rows = await OverviewRepository(database).page_cases(
            workspace_id=DEFAULT_WORKSPACE_ID,
            start=today.date(),
            end=today.date(),
            objects=(),
            bad_case_type="all",
            page=1,
            page_size=8,
        )

        assert len(rows) == 1
        assert rows[0].bad_case_id == CASE_ID
        assert rows[0].trigger_line == trigger_line
    finally:
        await database.dispose()
