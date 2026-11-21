"""Seven-stage prepare pipeline: idempotency, clustering, and blocked recovery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pytest

from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.models.jobs import JobRunRecord
from app.service.evolution.attribution import (
    AttributionEngine,
    AttributionInput,
    AttributionResult,
    AttributionRunner,
    RuleBasedEngine,
)
from app.service.evolution.engine.contracts import RunBlocked
from app.service.evolution.prepare import EvolutionPrepareService
from app.third_party_api.git.workspace import PreparedWorkspace
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    WORKSPACE_A,
    Harness,
    seed_case,
    seed_event,
    seed_session,
)

RUN_ID = "run-m10-04"

pytestmark = pytest.mark.asyncio


class FakeWorkspacePreparer:
    """Return one deterministic prepared workspace without touching git."""

    async def prepare(self, run: object) -> PreparedWorkspace:
        """Return stable paths for the prepared run."""
        return PreparedWorkspace(
            repo_path=Path("/tmp/repo"),
            path=Path("/tmp/workspace"),
            ref=TARGET_VERSION,
            base_commit="a" * 40,
            branch=f"evo/{RUN_ID}",
        )


class FailingEngine:
    """Fail the first attribution attempt with a retryable engine error."""

    key = "rule-v1"

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Raise before any probe is written."""
        del item
        raise TimeoutError("engine timed out")


def _job(run_id: str = RUN_ID) -> JobRunRecord:
    """Build one evolution_prepare job row for the service under test."""
    now = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
    return JobRunRecord(
        id="job-m10-04",
        kind="evolution_prepare",
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="test",
        external_job_id=None,
        attempt=1,
        payload={"runId": run_id},
        result=None,
        error=None,
        created_by=None,
        created_at=now,
        started_at=now,
        finished_at=None,
        updated_at=now,
    )


async def _create_run(
    database: object,
    *,
    run_id: str = RUN_ID,
    mode: str = "full",
    engine: str = "rule-v1",
) -> None:
    """Insert one V2 run snapshot prepared from the shared workspace fixture."""
    repository = EvolutionRepository(database)  # type: ignore[arg-type]
    await repository.create_run(
        {
            "id": run_id,
            "title": f"{TARGET_NAME} {TARGET_VERSION} 自进化",
            "workspace_id": WORKSPACE_A,
            "mode": mode,
            "engine_key": "full" if mode == "full" else "cluster_only",
            "eval_config": {},
            "potential_policy": {"preset": "default"},
            "cache_enabled": True,
            "attribution_engine": engine,
            "target_config_id": None,
            "target_type": "skill",
            "target_name": TARGET_NAME,
            "target_version": TARGET_VERSION,
            "repo_url": "https://example.invalid/deep-research.git",
            "sub_dir": "skills/deep-research",
            "window_from": date(2026, 11, 1),
            "window_to": date(2026, 11, 30),
            "models": ["glm-5.3"],
            "status": "preparing",
        },
    )


async def _seed_self_case(harness: Harness) -> None:
    """Seed one main Agent whose trace contains the target and a self report."""
    main = await seed_session(
        harness.database,
        session_id="session-m10-04",
        started_at=NOW,
        title="七步 prepare",
    )
    await seed_event(
        harness.database,
        agent_id=main,
        event_index=1,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=NOW,
    )
    await seed_case(
        harness.database,
        case_id="case-m10-04",
        session_id="session-m10-04",
        case_type="self",
        agent_id=main,
        created_at=NOW,
    )


def _service(
    harness: Harness,
    *,
    engine_factory: Callable[[str], AttributionEngine] | None = None,
) -> EvolutionPrepareService:
    """Compose the prepare service over the migrated test database."""
    runs = EvolutionRepository(harness.database)
    candidates = EvolutionRunCandidateRepository(harness.database)
    attributions = AttributionRepository(harness.database)
    runner = AttributionRunner(
        attributions,
        engine_factory=engine_factory or (lambda _key: RuleBasedEngine()),
    )
    return EvolutionPrepareService(
        runs,
        candidates,
        attributions,
        harness.matcher,
        runner,
        FakeWorkspacePreparer(),
    )


async def test_prepare_advances_through_every_stage_and_clusters_attributed(
    harness: Harness,
) -> None:
    """A full run reaches unit 5 with candidates, probes, clusters, and rounds."""
    await _seed_self_case(harness)
    await _create_run(harness.database)

    result = await _service(harness).handle(_job())

    runs = EvolutionRepository(harness.database)
    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 5
    assert run.status == "running"
    assert result["rounds"] == 1
    assert result["clusters"] == 1

    candidates = await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)
    assert len(candidates) == 1
    assert candidates[0].included is True
    assert candidates[0].probe_id is not None
    attributed = await AttributionRepository(harness.database).list_clusterable_probes(RUN_ID)
    assert attributed == ((candidates[0].probe_id, "prompt", "case-m10-04"),)
    clusters = await runs.list_clusters(RUN_ID)
    assert len(clusters) == 1
    assert clusters[0].confidence == pytest.approx(0.74)
    assert clusters[0].rank == 1

    second = await _service(harness).handle(_job())
    assert second["reused"] is True
    assert len(await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)) == 1


async def test_prepare_yields_after_persisted_attribution_and_resumes(harness: Harness) -> None:
    """A pause during attribution keeps the link, cursor and frozen target on resume."""
    from sqlalchemy import update

    from app.db.models.evolution import evolution_runs

    await _seed_self_case(harness)
    await _create_run(harness.database)
    calls = 0

    class PausingEngine(RuleBasedEngine):
        async def attribute(self, item: AttributionInput) -> AttributionResult:
            nonlocal calls
            calls += 1
            async with harness.database.transaction() as session:
                await session.execute(
                    update(evolution_runs)
                    .where(evolution_runs.c.id == RUN_ID)
                    .values(
                        control_state="pause_requested",
                    )
                )
            return await super().attribute(item)

    with pytest.raises(Exception) as yielded:
        await _service(harness, engine_factory=lambda _: PausingEngine()).handle(_job())
    assert type(yielded.value).__name__ == "PauseAtCheckpoint"
    assert len(await AttributionRepository(harness.database).list_clusterable_probes(RUN_ID)) == 1
    assert not await EvolutionRepository(harness.database).list_clusters(RUN_ID)
    async with harness.database.transaction() as session:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == RUN_ID)
            .values(control_state="running")
        )
    await _service(harness, engine_factory=lambda _: PausingEngine()).handle(_job())
    assert calls == 1
    assert len(await EvolutionRepository(harness.database).list_rounds(RUN_ID)) == 1


async def test_cluster_only_stops_after_clustering(harness: Harness) -> None:
    """Cluster-only runs complete at unit 5 without iteration rounds."""
    await _seed_self_case(harness)
    await _create_run(harness.database, mode="cluster_only")

    await _service(harness).handle(_job())

    runs = EvolutionRepository(harness.database)
    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert run.status == "completed"
    assert run.progress_unit == 5
    assert run.finished_at is not None
    assert await runs.list_rounds(RUN_ID) == ()
    assert len(await runs.list_clusters(RUN_ID)) == 1


@pytest.mark.parametrize(
    ("revision", "unit", "message"),
    [(None, 0, "revision"), ("tag:v1", 2, "association")],
)
async def test_historical_pause_fails_before_replacing_missing_inputs(
    harness: Harness, revision: str | None, unit: int, message: str
) -> None:
    from sqlalchemy import update

    from app.db.models.evolution import evolution_runs
    from app.service.evolution.engine.contracts import ConfigError

    await _seed_self_case(harness)
    await _create_run(harness.database, mode="cluster_only")
    async with harness.database.transaction() as session:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == RUN_ID)
            .values(
                target_revision=revision,
                progress_unit=unit,
                resumed_at=NOW,
                stats={"sessionRows": [{"sessionId": "original-session"}]},
            )
        )
    with pytest.raises(ConfigError, match=message):
        await _service(harness).handle(_job())
    assert not await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)


async def test_prepare_keeps_association_until_potential_cursor_commits(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import Any

    from sqlalchemy import update

    from app.db.models.evolution import evolution_runs

    await _seed_self_case(harness)
    await _create_run(harness.database, mode="cluster_only")
    runs = EvolutionRepository(harness.database)
    await runs.freeze_revision(RUN_ID, f"tag:{TARGET_VERSION}")
    advance = EvolutionRepository.advance_unit

    async def crash_before_cursor(
        repository: EvolutionRepository, run_id: str, **kwargs: Any
    ) -> Any:
        if kwargs["expected"] == 2:
            raise RuntimeError("process stopped before potential cursor")
        return await advance(repository, run_id, **kwargs)

    with monkeypatch.context() as stopping:
        stopping.setattr(EvolutionRepository, "advance_unit", crash_before_cursor)
        with pytest.raises(RuntimeError, match="before potential cursor"):
            await _service(harness).handle(_job())
    async with harness.database.transaction() as session:
        await session.execute(
            update(evolution_runs).where(evolution_runs.c.id == RUN_ID).values(resumed_at=NOW)
        )
    resumed = await _service(harness).handle(_job())
    assert resumed["status"] == "completed"
    assert len(await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)) == 1


async def test_blocked_attribution_resumes_without_duplicate_candidates(
    harness: Harness,
) -> None:
    """A retried attribution stage only fills missing probe links."""
    await _seed_self_case(harness)
    await _create_run(harness.database)
    runs = EvolutionRepository(harness.database)

    with pytest.raises(RunBlocked) as blocked:
        await _service(
            harness,
            engine_factory=lambda _key: FailingEngine(),
        ).handle(_job())
    assert blocked.value.stage == "attribution"
    after_failure = await runs.get_run(RUN_ID)
    assert after_failure is not None
    assert after_failure.progress_unit == 3
    assert len(await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)) == 1

    await runs.mark_blocked(
        RUN_ID,
        stage="attribution",
        message="engine timed out",
        error_stage="prepare",
    )
    await runs.mark_resumed(RUN_ID)
    await _service(harness).handle(_job())

    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 5
    candidates = await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)
    assert len(candidates) == 1
    assert candidates[0].probe_id is not None
