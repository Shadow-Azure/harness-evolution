"""Sanitized normalization issues attach to a durable sync run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.crud.sync_errors import append_normalization_issues
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import sync_runs
from app.service.acquisition.normalize import normalize_transcript

ROOT_ID = "11111111-1111-4111-8111-111111111111"


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'normalize.db'}",
    )


async def test_parse_issues_append_without_raw_input(tmp_path: Path) -> None:
    """Only stable issue fields reach sync_runs.errors."""
    settings = settings_for(tmp_path)
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        async with database.transaction() as session:
            await session.execute(
                sync_runs.insert().values(
                    id="sync-01",
                    source_type="script",
                    started_at=datetime(2026, 10, 20, tzinfo=UTC),
                    finished_at=None,
                    status="running",
                    records_total=1,
                    records_done=0,
                    imported=0,
                    skipped=0,
                    errors=[],
                ),
            )

        parsed = normalize_transcript(
            '{"privatePrompt":"DO_NOT_PERSIST"}\n{not-json}\n',
            root_session_id=ROOT_ID,
            agent_id=ROOT_ID,
            agent_kind="main",
            agent_meta=None,
        )
        await append_normalization_issues(database, "sync-01", parsed.issues)

        async with database.session() as session:
            errors = cast(
                list[dict[str, object]],
                (
                    await session.execute(
                        select(sync_runs.c.errors).where(sync_runs.c.id == "sync-01"),
                    )
                ).scalar_one(),
            )
        assert errors == [
            {
                "agentId": ROOT_ID,
                "code": "INVALID_JSONL_LINE",
                "lineNo": 2,
                "message": "JSONL line could not be parsed",
                "sessionId": ROOT_ID,
            },
        ]
        assert "DO_NOT_PERSIST" not in repr(errors)
    finally:
        await database.dispose()
