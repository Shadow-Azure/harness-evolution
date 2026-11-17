"""Finalize must advance the run cursor into the terminal step.

The design state machine (07 §5.1) defines the terminal transition as
"终评完成, unit=5+M+1": once ``write_final`` persists the final row the
cursor moves to 5+M+1, which is exactly the readability threshold of the
``final`` step. The real-process smoke (reports/2026-11-18-m12-03-smoke) hit
the gap: a completed run stayed at unit 5+M, so ``GET /runs/{id}/steps/final``
answered 404 STEP_NOT_READY even though ``final_completed`` was recorded and
``evolution_finals`` held the verdict.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_rounds, probe_clusters
from app.service.evolution.state import ensure_step_readable

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=SH)
RUN_ID = "e2e-final-cursor-run"
ROUND_ID = "e2e-final-cursor-round"


@pytest_asyncio.fixture
async def finalized_state(tmp_path: Any) -> AsyncIterator[tuple[Any, ...]]:
    """Provide one run parked at 5+M with all iterations finished."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m12-03-final-cursor-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    await repository.create_run(
        {
            "id": RUN_ID,
            "title": "终评游标",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "synthetic-review",
            "target_version": "synthetic-1",
            "repo_url": "https://git.example.invalid/repo.git",
            "sub_dir": "skills/synthetic-review",
            "base_ref": "synthetic-1",
            "base_commit": None,
            "branch_name": None,
            "repo_path": None,
            "workspace_path": None,
            "status": "running",
            "progress_unit": 6,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id=f"{ROUND_ID}-cluster",
                run_id=RUN_ID,
                seq=1,
                probe_cluster_description="终评游标",
                probe_cluster_type="error",
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id=ROUND_ID,
                run_id=RUN_ID,
                probe_cluster_id=f"{ROUND_ID}-cluster",
                seq=1,
                status="accepted",
            ),
        )
    try:
        yield database, repository
    finally:
        await database.dispose()


async def test_write_final_advances_cursor_to_final_threshold(
    finalized_state: tuple[Any, ...],
) -> None:
    """Persisting the final row moves 5+M → 5+M+1 so the final step reads."""
    _database, repository = finalized_state
    final = await repository.write_final(
        {
            "run_id": RUN_ID,
            "best_version": "synthetic-1",
            "verdict": True,
            "best_score": 88.5,
            "init_score": 82,
            "metrics": [],
        },
    )
    assert final.verdict is True
    run = await repository.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 7
    ensure_step_readable(run.progress_unit, 1, run.status, "final")


async def test_write_final_is_idempotent_after_cursor_advance(
    finalized_state: tuple[Any, ...],
) -> None:
    """A re-entered finalize (retry path) updates the row without a conflict."""
    _database, repository = finalized_state
    await repository.write_final(
        {
            "run_id": RUN_ID,
            "best_version": "synthetic-1",
            "verdict": True,
            "best_score": 88.5,
            "init_score": 82,
            "metrics": [],
        },
    )
    retried = await repository.write_final(
        {
            "run_id": RUN_ID,
            "best_version": "synthetic-1",
            "verdict": False,
            "best_score": 79,
            "init_score": 82,
            "metrics": [],
        },
    )
    assert retried.verdict is False
    run = await repository.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 7
