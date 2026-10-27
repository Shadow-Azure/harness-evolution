"""Stage service readiness and payload assembly over the real repositories."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, text, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import (
    evolution_finals,
    evolution_runs,
    probe_cluster_probes,
    probe_clusters,
)
from app.errors import AppError
from app.service.evolution.stages import (
    EvolutionStageService,
    EvolutionStepClusters,
    EvolutionStepFinal,
    EvolutionStepInput,
    EvolutionStepIteration,
    EvolutionStepSeverity,
)
from tests.six_step_seed import (
    NOW,
    RUN_ID,
    clear_evolution_state,
    load_fixture,
    load_snapshot,
    seed_external_corpus,
    seed_fixture,
    seed_run,
)

SECRET = "m5-06-service-signing-secret"


@pytest_asyncio.fixture
async def stage_service(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionStageService]]:
    """Provide the stage service bound to a migrated SQLite database."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr(SECRET),
        ),
    )
    await database.start()
    await upgrade_database(database)
    try:
        yield (
            database,
            EvolutionStageService(
                EvolutionRepository(database),
                ProbeQueryRepository(database),
            ),
        )
    finally:
        await database.dispose()


async def _seed_clustered(
    database: Database,
    *,
    progress_unit: int = 4,
    status: str = "running",
    mode: str = "full",
) -> None:
    """Seed the canonical corpus plus one ranked error cluster."""
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=progress_unit, status=status, mode=mode)
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters),
            [
                {
                    "probe_cluster_id": "C1",
                    "run_id": RUN_ID,
                    "seq": 1,
                    "probe_cluster_description": "检索索引读取失败",
                    "probe_cluster_type": "error",
                    "confidence": 0.82,
                    "impact": 9,
                    "severity": 7.4,
                    "rank": 1,
                    "created_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(probe_cluster_probes),
            [{"probe_cluster_id": "C1", "probe_id": "pr-050b-03"}],
        )


def _expect_app_error(
    exc: pytest.ExceptionInfo[BaseException],
    *,
    status_code: int,
    code: str,
    key: str | None = None,
) -> None:
    """Assert one raised error carries the documented status, code, and key."""
    assert isinstance(exc.value, AppError)
    assert exc.value.status_code == status_code
    assert exc.value.code == code
    if key is not None:
        assert exc.value.details == {"key": key}


async def test_unknown_run_raises_run_not_found(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """Every step key 404s with RUN_NOT_FOUND when the run does not exist."""
    _, service = stage_service

    with pytest.raises(AppError) as raised:
        await service.step("evo-missing", "input")
    _expect_app_error(raised, status_code=404, code="RUN_NOT_FOUND")


async def test_preparing_run_serves_input_preparation_state(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """A preparing run returns the active input shell instead of a 404."""
    database, service = stage_service
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=0, status="preparing")

    step = await service.step(RUN_ID, "input")

    assert isinstance(step, EvolutionStepInput)
    assert step.key == "input"
    assert step.index == 0
    assert step.title == "筛选输入"
    assert step.status == "active"
    assert step.clickable is True
    assert step.detail is None
    assert step.payload.condition.model_dump(mode="json", by_alias=True) == {
        "targetType": "skill",
        "targetName": "deep-research",
        "targetVersion": "v2.0.0",
        "from": "2026-08-20",
        "to": "2026-09-10",
        "models": ["glm-5.3"],
    }
    assert step.payload.hits.sessions == 0
    assert step.payload.hits.used_probes == 0
    assert step.payload.hits.by_attribute_type.non_issue == 0
    assert step.payload.rows == []


@pytest.mark.parametrize("key", ["clusters", "attribution", "severity", "iteration", "final"])
async def test_preparing_run_pending_steps_are_not_ready(
    stage_service: tuple[Database, EvolutionStageService],
    key: str,
) -> None:
    """Unreached steps of a preparing run stay 404 STEP_NOT_READY."""
    database, service = stage_service
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=0, status="preparing")

    with pytest.raises(AppError) as raised:
        await service.step(RUN_ID, key)  # type: ignore[arg-type]
    _expect_app_error(raised, status_code=404, code="STEP_NOT_READY", key=key)


async def test_cluster_only_run_serves_null_scores_and_locks_later_steps(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """Cluster-only runs expose input/clusters with null scores; later steps 404."""
    database, service = stage_service
    await _seed_clustered(database, progress_unit=2, status="completed", mode="cluster_only")
    async with database.transaction() as session:
        await session.execute(
            update(probe_clusters)
            .where(probe_clusters.c.run_id == RUN_ID)
            .values(confidence=None, severity=None, rank=None),
        )

    clusters = await service.step(RUN_ID, "clusters")

    assert isinstance(clusters, EvolutionStepClusters)
    assert clusters.status == "done"
    assert clusters.payload.clusters[0].confidence is None
    assert clusters.payload.clusters[0].severity is None
    assert clusters.payload.clusters[0].probes[0].probe_id == "pr-050b-03"

    for key in ("attribution", "severity", "iteration", "final"):
        with pytest.raises(AppError) as raised:
            await service.step(RUN_ID, key)
        _expect_app_error(raised, status_code=404, code="STEP_NOT_READY", key=key)


async def test_cluster_only_running_run_locks_later_steps_before_it_terminates(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """A running cluster-only run already 404s the four later steps (05 §4.12)."""
    database, service = stage_service
    await _seed_clustered(database, progress_unit=2, status="running", mode="cluster_only")

    clusters = await service.step(RUN_ID, "clusters")

    assert isinstance(clusters, EvolutionStepClusters)
    assert clusters.status == "done"

    for key in ("attribution", "severity", "iteration", "final"):
        with pytest.raises(AppError) as raised:
            await service.step(RUN_ID, key)
        _expect_app_error(raised, status_code=404, code="STEP_NOT_READY", key=key)


async def test_blocked_run_keeps_cursor_steps_readable(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """A blocked run reads done steps and the active iteration without advancing."""
    database, service = stage_service
    data = load_fixture("iteration")
    run_id = data["run"]["id"]
    await seed_fixture(database, data)
    async with database.transaction() as session:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == run_id)
            .values(status="blocked", blocked_stage="eval"),
        )

    step = await service.step(run_id, "iteration")

    assert isinstance(step, EvolutionStepIteration)
    assert step.status == "active"
    assert step.detail == "第 1/1 轮"
    assert step.payload.rounds[0].status == "accepted"
    assert step.payload.rounds[0].final_commit is not None

    with pytest.raises(AppError) as raised:
        await service.step(run_id, "final")
    _expect_app_error(raised, status_code=404, code="STEP_NOT_READY", key="final")


@pytest.mark.parametrize("status", ["failed", "interrupted"])
async def test_terminal_failed_runs_have_no_active_step(
    stage_service: tuple[Database, EvolutionStageService],
    status: str,
) -> None:
    """Failed and interrupted runs keep done steps readable, later steps 404."""
    database, service = stage_service
    await _seed_clustered(database, progress_unit=3, status=status)

    done = await service.step(RUN_ID, "attribution")

    assert done.status == "done"
    assert done.clickable is True

    with pytest.raises(AppError) as raised:
        await service.step(RUN_ID, "severity")
    _expect_app_error(raised, status_code=404, code="STEP_NOT_READY", key="severity")


async def test_severity_rows_order_by_stored_severity_descending(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """Ranking order comes from persisted severity, unranked clusters stay last."""
    database, service = stage_service
    await _seed_clustered(database, progress_unit=4)
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters),
            [
                {
                    "probe_cluster_id": "C2",
                    "run_id": RUN_ID,
                    "seq": 2,
                    "probe_cluster_description": "检索结果未去重",
                    "probe_cluster_type": "prompt",
                    "confidence": None,
                    "impact": 7,
                    "severity": None,
                    "rank": None,
                    "created_at": NOW,
                },
            ],
        )

    step = await service.step(RUN_ID, "severity")

    assert isinstance(step, EvolutionStepSeverity)
    assert [row.cluster_id for row in step.payload.rows] == ["C1", "C2"]
    assert step.payload.rows[0].severity == 7.4
    assert step.payload.rows[1].severity is None
    assert step.payload.rows[0].report_count == 1


async def test_final_changes_only_include_accepted_rounds(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """Rejected rounds never appear in the terminal change list."""
    database, service = stage_service
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=6, status="completed")
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters),
            [
                {
                    "probe_cluster_id": "C1",
                    "run_id": RUN_ID,
                    "seq": 1,
                    "probe_cluster_description": "检索索引读取失败",
                    "probe_cluster_type": "error",
                    "confidence": 0.82,
                    "impact": 9,
                    "severity": 7.4,
                    "rank": 1,
                    "created_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(evolution_finals).values(
                run_id=RUN_ID,
                best_version="v2.0.0-base",
                verdict=False,
                best_score=84.3,
                init_score=84.3,
                metrics=[],
            ),
        )

    step = await service.step(RUN_ID, "final")

    assert isinstance(step, EvolutionStepFinal)
    assert step.payload.verdict is False
    assert step.payload.changes == []


async def test_active_final_without_a_terminal_row_returns_null_verdict(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """A running run at unit 4+M serves the final step without fake zero values."""
    database, service = stage_service
    data = load_fixture("final-active")
    run_id = data["run"]["id"]
    await seed_fixture(database, data)

    step = await service.step(run_id, "final")

    assert isinstance(step, EvolutionStepFinal)
    assert step.status == "active"
    assert step.clickable is True
    assert step.detail is None
    assert step.payload.verdict is None
    assert step.payload.best_version is None
    assert step.payload.best_score is None
    assert step.payload.init_score is None
    assert step.payload.metrics == []
    assert [change.commit for change in step.payload.changes] == [
        "cd34ab12ef56cd34ab12ef56cd34ab12ef56cd34",
    ]
    assert step.model_dump(mode="json", by_alias=True) == load_snapshot("final-active")


async def test_step_reads_are_repeatable_without_writes(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """Reading the same step twice returns identical payloads and writes nothing."""
    database, service = stage_service
    data = load_fixture("iteration")
    run_id = data["run"]["id"]
    await seed_fixture(database, data)

    first = await service.step(run_id, "iteration")
    second = await service.step(run_id, "iteration")

    assert first.model_dump(mode="json", by_alias=True) == second.model_dump(
        mode="json",
        by_alias=True,
    )
    async with database.session() as session:
        rounds = len((await session.execute(text("SELECT id FROM evolution_rounds"))).all())
        runs = len((await session.execute(text("SELECT id FROM evolution_runs"))).all())
    assert (runs, rounds) == (1, 1)


async def test_snapshot_payloads_match_design_examples(
    stage_service: tuple[Database, EvolutionStageService],
) -> None:
    """Each fixture group reproduces its stored 05 §3.6.1 response snapshot."""
    database, service = stage_service
    for key in ("input", "clusters", "attribution", "severity", "iteration", "final"):
        data = load_fixture(key)
        await clear_evolution_state(database)
        await seed_fixture(database, data)
        step = await service.step(data["run"]["id"], key)
        assert step.model_dump(mode="json", by_alias=True) == load_snapshot(key)
