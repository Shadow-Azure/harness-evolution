"""Resume a shutdown-interrupted attribution batch without repeating finished cases."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_control import EvolutionControlRepository
from app.db.crud.jobs import JobRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.models.evolution import evolution_run_candidates, evolution_runs
from app.service.events import EventBus
from app.service.evolution.attribution import (
    AttributionInput,
    AttributionResult,
    AttributionRunner,
)
from app.service.evolution.attribution_jobs import AttributionJobService
from app.service.evolution.control import EvolutionControlService
from app.service.evolution.events import EvolutionRunEventService
from app.service.jobs import JobRunner
from tests.attribution.support import (
    NOW,
    probe_write,
    seed_candidate,
    seed_case,
    seed_run,
    seed_session,
)
from tests.v2_acceptance_support import migrated_database

RUN_ID = "run-batch-22"
CASES = tuple(f"bc-shutdown-{index:02d}" for index in range(22))
FINISHED = CASES[:9]


class CountingEngine:
    """Deterministic rule engine that records each attributed case."""

    key = "rule-v1"

    def __init__(self) -> None:
        """Start with no attributed cases."""
        self.calls: list[str] = []

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Return one attributed conclusion and count the case."""
        self.calls.append(item.bad_case_id)
        return AttributionResult(
            conclusion="attributed",
            category="error",
            confidence=0.8,
            reason="synthetic attribution",
            reasoning="synthetic reasoning",
            token_count=7,
        )


@pytest.mark.asyncio
async def test_batch_resumes_from_nine_of_twenty_two_without_repeating_cases(
    tmp_path: Path,
) -> None:
    """Recovery queues the same batch and the runner only fills the missing tail."""
    database = await migrated_database(tmp_path, "bugfix-49-attribution.db")
    bus = EventBus(queue_capacity=16)
    runner: JobRunner | None = None
    try:
        await seed_session(database)
        for case_id in CASES:
            await seed_case(database, case_id)
        await seed_run(database, RUN_ID)
        for case_id in CASES:
            await seed_candidate(database, RUN_ID, case_id)
        async with database.transaction() as session:
            await session.execute(
                update(evolution_runs)
                .where(evolution_runs.c.id == RUN_ID)
                .values(progress_unit=3, status="preparing", control_state="running"),
            )

        runs = EvolutionRepository(database)
        candidates = EvolutionRunCandidateRepository(database)
        attributions = AttributionRepository(database)
        for index, case_id in enumerate(FINISHED):
            await attributions.write_probe_and_link(
                probe_write(
                    case_id,
                    probe_id=f"probe-shutdown-{index}",
                    created_run_id=RUN_ID,
                ),
                RUN_ID,
                NOW,
            )
        events = EvolutionRunEventService(SqlRunEventStore(database), runs, bus)
        jobs = JobRepository(database)
        runner = JobRunner(jobs, bus, run_events=events)
        runner.set_evolution_control(
            EvolutionControlService(EvolutionControlRepository(database), events, runner.schedule),
            runs,
        )
        engine = CountingEngine()
        service = AttributionJobService(
            runner,
            runs,
            candidates,
            attributions,
            AttributionRunner(attributions, engine_factory=lambda _key: engine),
        )
        runner.register_handler("attribution_batch", service.handle, concurrency_limit=2)

        job = await jobs.insert(
            kind="attribution_batch",
            payload={"runId": RUN_ID, "source": "prepare"},
            ref_id=RUN_ID,
            created_by=None,
        )
        assert await jobs.claim(job.id, owner="old-process") is not None
        await jobs.update_progress(job.id, 9 / 22, result={"processed": 9, "total": 22})
        assert await jobs.interrupt(
            job.id,
            "job cancelled during shutdown",
            owner="old-process",
        )
        await runs.mark_interrupted(
            RUN_ID,
            stage="prepare",
            message="job interrupted during shutdown",
        )

        await runner.recover()
        recovered = await jobs.get(job.id)
        assert recovered is not None and recovered.status == "queued"
        assert recovered.progress == 9 / 22
        await runs.mark_recovered(RUN_ID)
        await runner.start_queued()
        terminal = await runner.wait(job.id)

        assert terminal.status == "completed"
        assert terminal.result is not None
        assert terminal.result["processed"] == len(CASES) - len(FINISHED)
        assert engine.calls == list(CASES[len(FINISHED) :])
        async with database.session() as session:
            linked: list[str] = list(
                (
                    await session.execute(
                        select(evolution_run_candidates.c.bad_case_id).where(
                            evolution_run_candidates.c.run_id == RUN_ID,
                            evolution_run_candidates.c.probe_id.is_not(None),
                        ),
                    )
                )
                .scalars()
                .all(),
            )
        assert set(linked) == set(CASES)
    finally:
        if runner is not None:
            await runner.close()
        await bus.close()
        await database.dispose()
