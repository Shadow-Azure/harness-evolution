"""Backoff ladder and blocked sweeper behavior."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.errors import AppError, ErrorCode
from app.service.evolution.backoff import (
    MAX_RETRY_ATTEMPTS,
    next_retry_at,
    next_retry_delay,
)
from app.service.evolution.blocked_sweeper import EvolutionBlockedSweeper

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@dataclass
class SubmittedJob:
    """One captured durable job submission."""

    kind: str
    payload: Mapping[str, Any]
    ref_id: str | None
    created_by: str | None
    reused: bool = False


@dataclass
class JobCapture:
    """Minimal idempotent queue double with busy-failure control."""

    items: list[SubmittedJob] = field(default_factory=list)
    raise_busy: bool = False

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> SubmittedJob:
        """Capture one job or report the same active stage as reused."""
        if self.raise_busy:
            raise AppError(
                status_code=409,
                code=ErrorCode.RUN_BUSY,
                message="another stage job is already active for this run",
            )
        for item in self.items:
            if item.kind == kind and item.ref_id == ref_id:
                return SubmittedJob(
                    kind=kind,
                    payload=dict(payload),
                    ref_id=ref_id,
                    created_by=created_by,
                    reused=True,
                )
        job = SubmittedJob(
            kind=kind,
            payload=dict(payload),
            ref_id=ref_id,
            created_by=created_by,
        )
        self.items.append(job)
        return job


@pytest_asyncio.fixture
async def state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository, JobCapture]]:
    """Provide migrated SQLite state and a capturing queue."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-11-sweeper-signing-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    jobs = JobCapture()
    try:
        yield database, EvolutionRepository(database), jobs
    finally:
        await database.dispose()


async def _seed_blocked(
    repository: EvolutionRepository,
    run_id: str,
    *,
    next_retry_at_value: datetime | None,
    retry_attempts: int = 0,
    blocked_stage: str = "push",
    created_by: str | None = None,
) -> None:
    """Create one blocked run with the exact retry facts under test."""
    await repository.create_run(
        {
            "id": run_id,
            "title": f"blocked {run_id}",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/skills.git",
            "sub_dir": "skills/deep-research",
            "branch_name": f"evo/20261028-{run_id}",
            "status": "blocked",
            "blocked_stage": blocked_stage,
            "retry_attempts": retry_attempts,
            "next_retry_at": next_retry_at_value,
            "progress_unit": 4,
            "created_by": created_by,
            "created_at": NOW,
        },
    )


def test_backoff_ladder_matches_design() -> None:
    """The frozen ladder is one, five, fifteen minutes and then stop."""
    assert next_retry_delay(0) == timedelta(minutes=1)
    assert next_retry_delay(1) == timedelta(minutes=5)
    assert next_retry_delay(2) == timedelta(minutes=15)
    assert next_retry_delay(MAX_RETRY_ATTEMPTS) is None
    assert next_retry_at(NOW, 0) == NOW + timedelta(minutes=1)
    assert next_retry_at(NOW, 3) is None


@pytest.mark.parametrize("attempts", [-1, -5])
def test_backoff_rejects_negative_attempts(attempts: int) -> None:
    """A corrupt negative counter never produces a schedule."""
    with pytest.raises(ValueError, match="negative"):
        next_retry_delay(attempts)
    with pytest.raises(ValueError, match="negative"):
        next_retry_at(NOW, attempts)


@pytest.mark.parametrize("attempts", [True, 1.5, "1", None])
def test_backoff_rejects_non_integer_attempts(attempts: object) -> None:
    """Boolean, float, string, and missing counters are rejected."""
    with pytest.raises(TypeError, match="integer"):
        next_retry_delay(attempts)  # type: ignore[arg-type]


async def test_sweeper_enqueues_only_due_push_backoff(
    state: tuple[Database, EvolutionRepository, JobCapture],
) -> None:
    """Due push blocks enqueue once; future, manual, and other stages do not."""
    _database, repository, jobs = state
    await _seed_blocked(
        repository,
        "run-due",
        next_retry_at_value=NOW - timedelta(seconds=1),
    )
    await _seed_blocked(
        repository,
        "run-future",
        next_retry_at_value=NOW + timedelta(minutes=5),
    )
    await _seed_blocked(repository, "run-manual", next_retry_at_value=None)
    await _seed_blocked(
        repository,
        "run-eval",
        next_retry_at_value=NOW - timedelta(minutes=1),
        blocked_stage="eval",
    )
    await _seed_blocked(
        repository,
        "run-capped",
        next_retry_at_value=NOW - timedelta(minutes=1),
        retry_attempts=3,
    )
    sweeper = EvolutionBlockedSweeper(repository, jobs, now=lambda: NOW)

    scheduled = await sweeper.run_once()

    assert scheduled == 1
    assert [(item.kind, item.ref_id, item.created_by) for item in jobs.items] == [
        ("evolution_retry", "run-due", None),
    ]
    assert jobs.items[0].payload == {"runId": "run-due", "automatic": True}

    assert await sweeper.run_once() == 0
    assert len(jobs.items) == 1


async def test_sweeper_tolerates_busy_and_records_nothing(
    state: tuple[Database, EvolutionRepository, JobCapture],
) -> None:
    """An already-active stage is silent and never counted as scheduled."""
    _database, repository, jobs = state
    await _seed_blocked(repository, "run-busy", next_retry_at_value=NOW)
    jobs.raise_busy = True
    sweeper = EvolutionBlockedSweeper(repository, jobs, now=lambda: NOW)

    assert await sweeper.run_once() == 0
    assert jobs.items == []


async def test_sweeper_start_stop_is_idempotent_and_stops_scanning(
    state: tuple[Database, EvolutionRepository, JobCapture],
) -> None:
    """Repeated start/stop is safe and a stopped loop performs no further scans."""
    _database, repository, jobs = state
    sweeper = EvolutionBlockedSweeper(
        repository,
        jobs,
        now=lambda: NOW,
        scan_interval_seconds=60.0,
    )
    sweeper.start()
    sweeper.start()
    assert sweeper.running
    await asyncio.sleep(0)
    await sweeper.stop()
    await sweeper.stop()
    assert not sweeper.running

    await _seed_blocked(repository, "run-after-stop", next_retry_at_value=NOW)
    await asyncio.sleep(0.02)
    assert jobs.items == []


async def test_sweeper_survives_a_failing_scan() -> None:
    """A scan exception is logged without killing the background loop."""
    failures = 0

    class FailingRuns:
        async def list_blocked_due(self, *args: object, **kwargs: object) -> tuple[object, ...]:
            nonlocal failures
            failures += 1
            if failures == 1:
                raise RuntimeError("transient scan failure")
            return ()

    sweeper = EvolutionBlockedSweeper(
        FailingRuns(),  # type: ignore[arg-type]
        JobCapture(),
        scan_interval_seconds=1.0,
    )
    sweeper.start()
    await asyncio.sleep(0.05)
    assert sweeper.running
    assert failures >= 1
    await sweeper.stop()
