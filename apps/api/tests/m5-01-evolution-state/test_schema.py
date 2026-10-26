"""Evolution schema and persisted record contracts."""

import os
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import inspect

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database

EVOLUTION_TABLES = (
    "evolution_runs",
    "probe_clusters",
    "probe_cluster_probes",
    "evolution_rounds",
    "evolution_finals",
)


@pytest_asyncio.fixture
async def evolution_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide an upgraded isolated SQLite database."""
    database = create_database(
        Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path),
    )
    await database.start()
    try:
        await upgrade_database(database)
        yield database
    finally:
        await database.dispose()


async def reflected_schema(
    database: Database,
) -> dict[str, dict[str, Any]]:
    """Return columns, indexes, uniques, foreign keys, and table names."""
    async with database.engine.connect() as connection:
        return await connection.run_sync(
            lambda sync: {
                table: {
                    "columns": {column["name"] for column in inspect(sync).get_columns(table)},
                    "indexes": {
                        index["name"]
                        for index in inspect(sync).get_indexes(table)
                        if index["name"] is not None
                    },
                    "uniques": {
                        constraint["name"]
                        for constraint in inspect(sync).get_unique_constraints(table)
                        if constraint["name"] is not None
                    },
                    "foreign_keys": {
                        (
                            tuple(foreign_key["constrained_columns"]),
                            foreign_key["referred_table"],
                            tuple(foreign_key["referred_columns"]),
                        )
                        for foreign_key in inspect(sync).get_foreign_keys(table)
                    },
                }
                for table in EVOLUTION_TABLES
            },
        )


async def test_evolution_schema_is_complete_and_indexed(
    evolution_database: Database,
) -> None:
    """All five evolution tables expose their durable state columns and constraints."""
    reflected = await reflected_schema(evolution_database)

    assert reflected["evolution_runs"]["columns"] >= {
        "id",
        "title",
        "mode",
        "engine_key",
        "eval_config",
        "target_config_id",
        "target_type",
        "target_name",
        "target_version",
        "repo_url",
        "sub_dir",
        "repo_path",
        "base_ref",
        "base_commit",
        "branch_name",
        "workspace_path",
        "remote_name",
        "push_status",
        "pushed_at",
        "push_error",
        "window_from",
        "window_to",
        "models",
        "status",
        "blocked_stage",
        "retry_attempts",
        "next_retry_at",
        "eval_status",
        "error_stage",
        "error_message",
        "error_at",
        "progress_unit",
        "stats",
        "created_by",
        "created_at",
        "finished_at",
    }
    assert reflected["evolution_runs"]["indexes"] >= {
        "ix_evolution_runs_created_at",
        "ix_evolution_runs_status",
        "ix_evolution_runs_push_status",
        "ix_evolution_runs_status_next_retry",
        "ix_evolution_runs_target_version",
        "ix_evolution_runs_target_config",
    }
    assert (
        ("target_config_id",),
        "evolution_targets",
        ("id",),
    ) in reflected["evolution_runs"]["foreign_keys"]
    assert (
        ("created_by",),
        "users",
        ("id",),
    ) in reflected["evolution_runs"]["foreign_keys"]

    assert reflected["probe_clusters"]["columns"] >= {
        "probe_cluster_id",
        "run_id",
        "seq",
        "probe_cluster_description",
        "probe_cluster_type",
        "confidence",
        "impact",
        "severity",
        "rank",
        "created_at",
    }
    assert "uq_probe_clusters_run_seq" in reflected["probe_clusters"]["uniques"]
    assert reflected["probe_clusters"]["indexes"] >= {
        "ix_probe_clusters_run",
        "ix_probe_clusters_run_rank",
    }

    assert reflected["probe_cluster_probes"]["columns"] == {
        "id",
        "probe_cluster_id",
        "probe_id",
    }
    assert "uq_probe_cluster_probes_pair" in reflected["probe_cluster_probes"]["uniques"]
    assert "ix_probe_cluster_probes_probe" in reflected["probe_cluster_probes"]["indexes"]

    assert reflected["evolution_rounds"]["columns"] >= {
        "id",
        "run_id",
        "probe_cluster_id",
        "seq",
        "status",
        "started_at",
        "finished_at",
        "duration_ms",
        "error_message",
        "patch",
        "candidate_ref",
        "candidate_commit",
        "candidate_message",
        "push_status",
        "push_attempts",
        "pushed_at",
        "push_error",
        "eval_external_id",
        "eval_status",
        "eval_attempts",
        "eval_next_poll_at",
        "eval_started_at",
        "eval_finished_at",
        "eval_current",
        "eval_candidate",
        "eval_result",
        "eval_error",
        "accepted",
        "commit_hash",
        "commit_message",
    }
    assert "uq_evolution_rounds_run_seq" in reflected["evolution_rounds"]["uniques"]
    assert reflected["evolution_rounds"]["indexes"] >= {
        "ix_evolution_rounds_cluster",
        "ix_evolution_rounds_run_status",
        "ix_evolution_rounds_eval_poll",
    }

    assert reflected["evolution_finals"]["columns"] == {
        "run_id",
        "best_version",
        "verdict",
        "best_score",
        "init_score",
        "metrics",
    }


def test_record_helpers_copy_json_and_normalize_timestamps() -> None:
    """Mutable JSON rows become immutable-ish copies with Shanghai timestamps."""
    from app.db.models.evolution import (
        EvolutionFinalRecord,
        EvolutionRunRecord,
        evolution_finals,
        evolution_runs,
        record_from_evolution_final,
        record_from_evolution_run,
    )

    created_at = datetime(2026, 10, 27, 1, 2, 3)
    values: Mapping[str, Any] = {
        "id": "run-1",
        "title": "prototype run",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {"gateway": "mock"},
        "target_config_id": "target-1",
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/agent-skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": None,
        "base_ref": None,
        "base_commit": None,
        "branch_name": None,
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "pending",
        "pushed_at": None,
        "push_error": None,
        "window_from": None,
        "window_to": None,
        "models": ["glm-5.3"],
        "status": "preparing",
        "blocked_stage": None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": None,
        "error_message": None,
        "error_at": None,
        "progress_unit": 0,
        "stats": {"sessions": 4},
        "created_by": None,
        "created_at": created_at,
        "finished_at": None,
    }
    run = record_from_evolution_run(values)

    assert isinstance(run, EvolutionRunRecord)
    assert run.eval_config == {"gateway": "mock"}
    assert run.stats == {"sessions": 4}
    offset = run.created_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 8 * 60 * 60
    assert evolution_runs.c.progress_unit.name == "progress_unit"

    final = record_from_evolution_final(
        {
            "run_id": "run-1",
            "best_version": "v2.0.1",
            "verdict": True,
            "best_score": 88.9,
            "init_score": 84.3,
            "metrics": [{"name": "score", "value": 88.9}],
        },
    )
    assert isinstance(final, EvolutionFinalRecord)
    assert final.metrics == [{"name": "score", "value": 88.9}]
    assert evolution_finals.c.run_id.primary_key is True


@pytest.mark.mysql
async def test_mysql_evolution_schema_reflects_the_same_contract() -> None:
    """The MySQL lane exposes the same five evolution tables and key constraints."""
    url = os.environ.get("HE_DB_URL", "")
    if not url.startswith("mysql+asyncmy://"):
        if os.environ.get("HE_REQUIRE_MYSQL") == "1":
            pytest.fail("HE_DB_URL must point to MySQL when HE_REQUIRE_MYSQL=1")
        pytest.skip("HE_DB_URL is not configured for MySQL")
    database = create_database(
        Settings(db_dialect=DatabaseDialect.MYSQL, db_url=url),
    )
    await database.start()
    try:
        await upgrade_database(database)
        reflected = await reflected_schema(database)
    finally:
        await database.dispose()

    assert "progress_unit" in reflected["evolution_runs"]["columns"]
    assert "uq_probe_clusters_run_seq" in reflected["probe_clusters"]["uniques"]
    assert "ix_evolution_rounds_eval_poll" in reflected["evolution_rounds"]["indexes"]
