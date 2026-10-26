"""Evolution run-list aggregation against a migrated database."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import (
    evolution_finals,
    evolution_rounds,
    evolution_runs,
    probe_clusters,
)
from app.db.models.users import users

OLDER = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
NEWER = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def run_database(tmp_path: Path) -> AsyncIterator[tuple[Database, EvolutionRepository]]:
    """Provide a migrated SQLite database with one creator."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("m5-04-run-list-repository-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        await session.execute(
            insert(users).values(
                id="user-run-list",
                username="run-creator",
                password_hash="not-used",
                display_name="Run Creator",
                role="admin",
                is_active=True,
                must_change_password=False,
                created_at=OLDER,
                updated_at=OLDER,
                last_login_at=None,
                password_changed_at=None,
            ),
        )
    try:
        yield database, EvolutionRepository(database)
    finally:
        await database.dispose()


def _run_values(
    run_id: str,
    status: str,
    created_at: datetime,
    *,
    progress_unit: int = 0,
) -> dict[str, Any]:
    """Build a complete run snapshot for repository aggregation."""
    return {
        "id": run_id,
        "title": f"{run_id} title",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": None,
        "base_ref": "v2.0.0",
        "base_commit": None,
        "branch_name": f"evo/{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "succeeded",
        "pushed_at": created_at,
        "push_error": None,
        "window_from": date(2026, 8, 20),
        "window_to": date(2026, 9, 10),
        "models": ["glm-5.3"],
        "status": status,
        "blocked_stage": None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": None,
        "error_message": None,
        "error_at": None,
        "progress_unit": progress_unit,
        "stats": {
            "sessions": 4,
            "probes": 3,
            "usedProbes": 2,
            "byAttributeType": {"model": 1, "prompt": 1, "error": 0, "nonIssue": 1},
        },
        "created_by": "user-run-list",
        "created_at": created_at,
        "finished_at": None,
    }


async def test_list_summaries_batches_counts_final_and_creator(
    run_database: tuple[Database, EvolutionRepository],
) -> None:
    """One query result carries creator, actual cluster count, accepted rounds, and final."""
    database, repository = run_database
    async with database.transaction() as session:
        await session.execute(
            insert(evolution_runs),
            [
                _run_values("run-older", "running", OLDER, progress_unit=4),
                _run_values("run-newer-b", "completed", NEWER, progress_unit=7),
                _run_values("run-newer-a", "failed", NEWER, progress_unit=2),
            ],
        )
        await session.execute(
            insert(probe_clusters),
            [
                {
                    "probe_cluster_id": "cluster-1",
                    "run_id": "run-newer-b",
                    "seq": 1,
                    "probe_cluster_description": "one",
                    "probe_cluster_type": "error",
                    "confidence": 0.9,
                    "impact": 9,
                    "severity": 8.1,
                    "rank": 1,
                    "created_at": NEWER,
                },
                {
                    "probe_cluster_id": "cluster-2",
                    "run_id": "run-newer-b",
                    "seq": 2,
                    "probe_cluster_description": "two",
                    "probe_cluster_type": "prompt",
                    "confidence": 0.8,
                    "impact": 7,
                    "severity": 5.6,
                    "rank": 2,
                    "created_at": NEWER,
                },
            ],
        )
        await session.execute(
            insert(evolution_finals).values(
                run_id="run-newer-b",
                best_version="v2.0.1-best",
                verdict=True,
                best_score=88.9,
                init_score=84.3,
                metrics=[],
            ),
        )
        await session.execute(
            insert(evolution_rounds),
            [
                {
                    "id": "round-1",
                    "run_id": "run-newer-b",
                    "probe_cluster_id": "cluster-1",
                    "seq": 1,
                    "status": "accepted",
                    "accepted": True,
                },
                {
                    "id": "round-2",
                    "run_id": "run-newer-b",
                    "probe_cluster_id": "cluster-2",
                    "seq": 2,
                    "status": "rejected",
                    "accepted": False,
                },
            ],
        )

    summaries = await repository.list_summaries()

    assert [summary.run.id for summary in summaries] == [
        "run-newer-b",
        "run-newer-a",
        "run-older",
    ]
    completed = summaries[0]
    assert completed.created_by_name == "Run Creator"
    assert completed.cluster_count == 2
    assert completed.accepted_count == 1
    assert completed.final is not None
    assert completed.final.best_version == "v2.0.1-best"
