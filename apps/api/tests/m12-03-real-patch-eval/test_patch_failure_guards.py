"""Guards around mark_round_failed and the suppressed-conflict raise path.

The run-side update must never overwrite an already-terminal run (a push
blocked run keeps its blocked facts), and a suppressed StageConflict must not
fabricate a second run_failed event — the original ConfigError still propagates.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_rounds, probe_clusters
from app.service.evolution.engine.contracts import ConfigError
from app.service.evolution.git_candidate import EvolutionCandidateService
from app.service.evolution.state import StageConflict

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=SH)


@pytest_asyncio.fixture
async def guard_state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository]]:
    """Migrated SQLite state with one patching round under a running run."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m12-03-guard-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    await repository.create_run(
        {
            "id": "run-guard",
            "title": "round failure guard",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": str(tmp_path / "example.git"),
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261118-run-guard",
            "repo_path": str(tmp_path / "repos" / "run-guard"),
            "workspace_path": str(tmp_path / "workspaces" / "run-guard"),
            "status": "running",
            "progress_unit": 5,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-guard",
                run_id="run-guard",
                seq=1,
                probe_cluster_description="guard issue",
                probe_cluster_type="error",
                confidence=0.9,
                impact=0.8,
                severity=0.8,
                rank=1,
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id="round-guard",
                run_id="run-guard",
                probe_cluster_id="cluster-guard",
                seq=1,
                status="patching",
            ),
        )
    try:
        yield database, repository
    finally:
        await database.dispose()


async def _enter_patching(
    database: Database,
    round_id: str = "round-guard",
) -> None:
    """Force the round back into patching after a run-level state change."""
    async with database.transaction() as session:
        await session.execute(
            update(evolution_rounds)
            .where(evolution_rounds.c.id == round_id)
            .values(status="patching"),
        )


async def test_mark_round_failed_keeps_a_blocked_run_untouched(
    guard_state: tuple[Database, EvolutionRepository],
) -> None:
    """A run already blocked at push is not overwritten by a late patch failure."""
    database, repository = guard_state
    await repository.mark_blocked("run-guard", stage="push", message="push failed")
    await _enter_patching(database)

    failed = await repository.mark_round_failed(
        "run-guard",
        "round-guard",
        stage="patch",
        message="existing target config is not valid JSON",
    )

    assert failed.status == "failed"
    run = await repository.get_run("run-guard")
    assert run is not None
    # The terminal run stays untouched: the push-blocked facts survive.
    assert run.status == "blocked"
    assert run.blocked_stage == "push"
    assert run.error_stage == "push"
    assert run.error_message == "push failed"
    assert run.finished_at is None


async def test_mark_round_failed_still_fails_a_running_run(
    guard_state: tuple[Database, EvolutionRepository],
) -> None:
    """The normal path keeps failing a non-terminal run with the patch stage."""
    _database, repository = guard_state

    await repository.mark_round_failed(
        "run-guard",
        "round-guard",
        stage="patch",
        message="existing target config is not valid JSON",
    )

    run = await repository.get_run("run-guard")
    assert run is not None
    assert run.status == "failed"
    assert run.error_stage == "patch"
    assert run.error_message == "existing target config is not valid JSON"
    assert run.finished_at is not None


async def test_mark_failed_does_not_rewrite_an_already_failed_run(
    guard_state: tuple[Database, EvolutionRepository],
) -> None:
    """A late generic job failure keeps the first writer's patch stage facts."""
    _database, repository = guard_state
    await repository.mark_round_failed(
        "run-guard",
        "round-guard",
        stage="patch",
        message="existing target config is not valid JSON",
    )

    await repository.mark_failed("run-guard", stage="step", message="任务执行失败")

    run = await repository.get_run("run-guard")
    assert run is not None
    assert run.status == "failed"
    assert run.error_stage == "patch"
    assert run.error_message == "existing target config is not valid JSON"


class _ConflictingRuns:
    """Repository stub whose round failure always loses a stage race."""

    def __init__(self, events: _EventRecorder) -> None:
        self._events = events

    async def mark_round_failed(
        self,
        run_id: str,
        round_id: str,
        *,
        stage: str,
        message: str,
    ) -> Any:
        del run_id, round_id, stage, message
        raise StageConflict(
            status_code=409,
            current=0,
            target=1,
            reason="round cannot fail from the patching state",
        )


class _EventRecorder:
    """Capture event records without touching the durable store."""

    def __init__(self) -> None:
        self.recorded: list[tuple[str, str]] = []

    async def record(self, run_id: str, event_type: str, **kwargs: Any) -> None:
        """Capture one event record call."""
        del kwargs
        self.recorded.append((run_id, event_type))


class _RunStub:
    """Minimal run identity for the failure helper."""

    def __init__(self, run_id: str) -> None:
        self.id = run_id


async def test_suppressed_stage_conflict_raises_root_cause_without_new_event() -> None:
    """A lost race keeps the round-side winner and only re-raises the ConfigError."""
    events = _EventRecorder()
    service = EvolutionCandidateService(
        _ConflictingRuns(events),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        events=events,  # type: ignore[arg-type]
    )

    with pytest.raises(ConfigError, match="config"):
        await service._fail_patch_generation(
            _RunStub("run-guard"),  # type: ignore[arg-type]
            "round-guard",
            ConfigError("existing target config is not valid JSON: config/app.json"),
            job_id=None,
        )

    assert events.recorded == []
