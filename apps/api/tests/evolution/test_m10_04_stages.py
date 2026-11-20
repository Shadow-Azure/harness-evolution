"""Seven-step projection: shared envelope, V2 facts, and legacy adaptation."""

from __future__ import annotations

import pytest

from app.db.base import Database
from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.errors import AppError
from app.service.evolution.attribution import AttributionRunner, RuleBasedEngine
from app.service.evolution.prepare import EvolutionPrepareService
from app.service.evolution.stages import EvolutionStageService, StepSessionRow
from app.service.evolution.state import STEP_KEYS
from tests.evolution.test_m10_04_prepare import (
    FakeWorkspacePreparer,
    _create_run,
    _job,
    _seed_self_case,
)
from tests.m10_02_potential_support import Harness
from tests.six_step_seed import (
    load_fixture,
    seed_external_corpus,
    seed_fixture,
)

pytestmark = pytest.mark.asyncio


def _stage_service(database: Database) -> EvolutionStageService:
    """Compose the seven-step projection over one migrated database."""
    return EvolutionStageService(
        EvolutionRepository(database),
        ProbeQueryRepository(database),
        EvolutionRunCandidateRepository(database),
        AttributionRepository(database),
    )


def _prepare_service(database: Database, harness: Harness) -> EvolutionPrepareService:
    """Compose the prepare service used to reach the durable V2 state."""
    candidates = EvolutionRunCandidateRepository(database)
    attributions = AttributionRepository(database)
    return EvolutionPrepareService(
        EvolutionRepository(database),
        candidates,
        attributions,
        harness.matcher,
        AttributionRunner(attributions, engine_factory=lambda _: RuleBasedEngine()),
        FakeWorkspacePreparer(),
    )


async def test_v2_run_returns_all_seven_steps_in_order(harness: Harness) -> None:
    """A prepared V2 run exposes every step with the documented envelope."""
    await _seed_self_case(harness)
    await _create_run(harness.database)
    await _prepare_service(harness.database, harness).handle(_job())
    service = _stage_service(harness.database)

    envelopes = []
    for key in STEP_KEYS[:-1]:
        step = await service.step("run-m10-04", key)  # type: ignore[arg-type]
        envelopes.append(step)
        assert step.key == key
        assert step.index == STEP_KEYS.index(key)
        assert step.status in {"done", "active"}

    assert [step.key for step in envelopes] == list(STEP_KEYS[:-1])
    with pytest.raises(AppError) as pending_final:
        await service.step("run-m10-04", "final")
    assert pending_final.value.code.value == "STEP_NOT_READY"
    sessions = await service.step("run-m10-04", "sessions")
    assert sessions.payload.summary.associated == 1  # type: ignore[union-attr]
    assert sessions.payload.rows[0].bad_case_count == 1  # type: ignore[union-attr]
    assert sessions.payload.rows[0].short == "七步 prepare"  # type: ignore[union-attr]
    potential = await service.step("run-m10-04", "potential")
    assert potential.payload.total == 1  # type: ignore[union-attr]
    assert potential.payload.rows[0].hit_reason == "self_report"  # type: ignore[union-attr]
    attribution = await service.step("run-m10-04", "attribution")
    assert attribution.payload.summary.potential == 1  # type: ignore[union-attr]
    assert attribution.payload.summary.non_target == 0  # type: ignore[union-attr]
    assert attribution.payload.rows[0].session_id == "session-m10-04"  # type: ignore[union-attr]
    clusters = await service.step("run-m10-04", "clusters")
    cluster = clusters.payload.clusters[0]  # type: ignore[union-attr]
    assert cluster.case_count == 1
    assert cluster.cases[0].bad_case_id == "case-m10-04"
    iteration = await service.step("run-m10-04", "iteration")
    assert iteration.payload.rounds[0].case_count == 1  # type: ignore[union-attr]


async def test_historical_session_rows_fall_back_to_bounded_title(
    harness: Harness,
) -> None:
    """Rows prepared before `short` existed still render a bounded label."""
    await _seed_self_case(harness)
    await _create_run(harness.database)
    await _prepare_service(harness.database, harness).handle(_job())
    runs = EvolutionRepository(harness.database)
    prepared = await runs.get_run("run-m10-04")
    assert prepared is not None
    long_title = ("SWE-bench astropy-12907 修复任务 " * 200)[:3337]
    historical = []
    for row in prepared.stats["sessionRows"]:
        legacy_row = {**row, "title": long_title}
        legacy_row.pop("short", None)
        historical.append(legacy_row)
    await runs.write_stats(
        "run-m10-04",
        {**dict(prepared.stats), "sessionRows": historical},
    )

    sessions = await _stage_service(harness.database).step("run-m10-04", "sessions")

    row = sessions.payload.rows[0]  # type: ignore[union-attr]
    assert isinstance(row, StepSessionRow)
    assert row.title == long_title
    assert row.short == long_title[:120]


async def test_legacy_run_maps_six_step_progress_onto_seven_steps(
    harness: Harness,
) -> None:
    """A V1 run that finished severity renders as a prepared seven-step run."""
    await seed_external_corpus(harness.database)
    data = load_fixture("clusters")
    await seed_fixture(harness.database, data)
    service = _stage_service(harness.database)

    clusters = await service.step(data["run"]["id"], "clusters")
    assert clusters.index == 4
    assert clusters.status == "done"
    cluster = clusters.payload.clusters[0]  # type: ignore[union-attr]
    assert cluster.category == "error"
    assert cluster.cases

    iteration = await service.step(data["run"]["id"], "iteration")
    assert iteration.status == "active"

    sessions = await service.step(data["run"]["id"], "sessions")
    assert sessions.status == "done"
    assert sessions.payload.summary.associated == 1  # type: ignore[union-attr]

    attribution = await service.step(data["run"]["id"], "attribution")
    assert attribution.payload.rows
    assert (  # type: ignore[union-attr]
        attribution.payload.rows[0].session_id == "050b81ba-0000-4000-8000-0000000000c3"
    )

    range_step = await service.step(data["run"]["id"], "range")
    assert range_step.status == "done"
    assert range_step.payload.condition.target_version == "v2.0.0"  # type: ignore[union-attr]


async def test_cluster_only_hides_iteration_and_final(harness: Harness) -> None:
    """Cluster-only runs stop after the cluster step."""
    await _seed_self_case(harness)
    await _create_run(harness.database, mode="cluster_only")
    await _prepare_service(harness.database, harness).handle(_job())
    service = _stage_service(harness.database)

    clusters = await service.step("run-m10-04", "clusters")
    assert clusters.status == "done"
    with pytest.raises(AppError) as hidden:
        await service.step("run-m10-04", "iteration")
    assert hidden.value.code.value == "STEP_NOT_READY"


async def test_pending_step_is_not_readable(harness: Harness) -> None:
    """A run that has not reached a step returns STEP_NOT_READY."""
    await _create_run(harness.database, run_id="run-preparing")
    service = _stage_service(harness.database)
    for key in ("sessions", "potential", "attribution", "clusters", "iteration", "final"):
        with pytest.raises(AppError) as pending:
            await service.step("run-preparing", key)
        assert pending.value.code.value == "STEP_NOT_READY"
