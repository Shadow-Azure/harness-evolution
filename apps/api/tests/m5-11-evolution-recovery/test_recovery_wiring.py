"""Composition-root and startup wiring for evolution recovery."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr, ValidationError
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.models.evolution import evolution_runs
from app.db.models.jobs import JobRunRecord, job_runs
from app.main import create_app

RUN_ID = "run-startup"
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def _run_values() -> dict[str, object]:
    """Build one due blocked push run for startup pickup."""
    return {
        "id": RUN_ID,
        "title": "startup blocked",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "branch_name": "evo/20261028-run-startup",
        "workspace_path": None,
        "status": "blocked",
        "blocked_stage": "push",
        "retry_attempts": 0,
        "next_retry_at": NOW - timedelta(days=1),
        "progress_unit": 4,
        "created_by": None,
        "created_at": NOW,
    }


def test_composition_registers_retry_and_sweeper(tmp_path: Path) -> None:
    """The app exposes the retry handler, service, and idle sweeper."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-11-wiring-signing-secret"),
            blocked_sweep_seconds=1,
        ),
    )

    assert "evolution_retry" in app.state.jobs._handlers
    assert app.state.evolution_retry is not None
    assert app.state.blocked_sweeper is not None
    assert app.state.blocked_sweeper.running is False
    assert app.state.settings.blocked_sweep_seconds == 1


def test_blocked_sweep_seconds_rejects_zero() -> None:
    """The configured cadence must stay at least one second."""
    with pytest.raises(ValidationError):
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=Path("unused"),
            jwt_secret=SecretStr("m5-11-wiring-signing-secret"),
            blocked_sweep_seconds=0,
        )


@pytest_asyncio.fixture
async def startup_app(
    tmp_path: Path,
) -> AsyncIterator[tuple[Any, Any]]:
    """Start one real lifespan with a one-second sweeper cadence."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-11-wiring-signing-secret"),
            blocked_sweep_seconds=1,
        ),
    )
    async with app.router.lifespan_context(app):
        yield app, app.state.database


async def test_startup_sweeper_picks_up_due_blocked_run(
    startup_app: tuple[Any, Any],
) -> None:
    """A due blocked run present after startup is picked up by the live sweeper."""
    app, database = startup_app
    seen: list[str] = []

    async def recording_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Record the picked-up run without touching git."""
        seen.append(job.ref_id or "")
        return {"ok": True}

    assert app.state.blocked_sweeper.running is True
    await app.state.blocked_sweeper.stop()
    app.state.jobs._handlers["evolution_retry"] = recording_handler
    async with database.transaction() as session:
        await session.execute(insert(evolution_runs).values(**_run_values()))

    scheduled = await app.state.blocked_sweeper.run_once()

    assert scheduled == 1
    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    select(job_runs).where(
                        job_runs.c.kind == "evolution_retry",
                        job_runs.c.ref_id == RUN_ID,
                    ),
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1
