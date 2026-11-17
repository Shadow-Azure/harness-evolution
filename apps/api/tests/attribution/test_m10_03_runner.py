"""Runner cache reuse, cache-off rewrites, resume, and evidence plumbing."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.db.base import Database
from app.db.crud.attributions import (
    AttributionRepository,
    EvolutionRunCandidateRepository,
)
from app.db.crud.evolution import EvolutionRepository
from app.db.models.domain import probe_reports
from app.db.models.evolution import EvolutionRunCandidateRecord, EvolutionRunRecord
from app.service.evolution.attribution import (
    AttributionInput,
    AttributionResult,
    AttributionRunner,
)
from app.service.evolution.attribution_contracts import default_execution_manifest
from app.service.evolution.engine.contracts import RunBlocked
from app.utils.time import SHANGHAI
from tests.attribution.support import (
    CASE_ID,
    KNOWLEDGE_DOCUMENT_ID,
    OTHER_CASE_ID,
    OTHER_RUN_ID,
    RUN_ID,
    SESSION_ID,
    TARGET_REVISION,
    Harness,
    potential_case,
)


class CountingEngine:
    """Deterministic test engine that also counts calls."""

    key = "rule-v1"

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[str] = []
        self._fail_on_call = fail_on_call

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Return a distinctive result or fail on the configured call."""
        self.calls.append(item.bad_case_id)
        if self._fail_on_call is not None and len(self.calls) == self._fail_on_call:
            raise RuntimeError("synthetic engine failure")
        if item.bad_case_id == OTHER_CASE_ID and "error" not in item.metadata:
            return AttributionResult(
                conclusion="non_target",
                category=None,
                confidence=0.7,
                reason="非该对象问题：证据不足",  # noqa: RUF001
                reasoning="证据不足，不进簇",  # noqa: RUF001
            )
        return AttributionResult(
            conclusion="attributed",
            category="error",
            confidence=0.8,
            reason=f"第 {len(self.calls)} 次归因",
            reasoning="reasoning",
        )


async def load_run(database: Database, run_id: str = RUN_ID) -> EvolutionRunRecord:
    """Load one seeded run through the production repository."""
    run = await EvolutionRepository(database).get_run(run_id)
    assert run is not None
    return run


async def probe_count(database: Database) -> int:
    """Count probe rows to detect duplicate cache writes."""
    async with database.session() as session:
        return int(
            (await session.execute(select(func.count()).select_from(probe_reports))).scalar_one(),
        )


async def candidate(
    database: Database,
    run_id: str,
    case_id: str = CASE_ID,
) -> EvolutionRunCandidateRecord:
    """Return the one candidate snapshot of a run and case."""
    records = await EvolutionRunCandidateRepository(database).list(run_id)
    return next(record for record in records if record.bad_case_id == case_id)


def runner_cache_key(case_id: str = CASE_ID) -> str:
    """Return the V2 manifest cache identity for one seeded candidate."""
    item = potential_case(case_id)
    return default_execution_manifest(
        workspace_id="ws-default",
        bad_case_id=case_id,
        target_type="skill",
        target_name="deep-research",
        target_version=TARGET_REVISION,
        policy_version="v1",
        engine="rule-v1",
        session_id=item.session_id,
        hit_reason=item.hit_reason,
        order_state=item.order_state,
        object_trigger_at=item.object_trigger.triggered_at,
        case_trigger_at=(item.case_trigger.triggered_at if item.case_trigger is not None else None),
    ).content_hash


async def test_runner_writes_revision_scoped_probe_and_candidate(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """The first run writes one probe per included case and links the candidates."""
    run = await load_run(attribution_harness.database)
    engine = CountingEngine()
    runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: engine,
    )
    summary = await runner.run(
        run,
        (potential_case(), potential_case(OTHER_CASE_ID)),
        cache_enabled=True,
    )

    assert summary.processed == 2
    assert summary.created == 2
    assert summary.reused == 0
    assert summary.non_target == 1
    assert summary.skipped == 0
    first = await attribution_repository.get_probe_by_cache_key(
        runner_cache_key(),
    )
    assert first is not None
    assert first.created_run_id == RUN_ID
    assert first.conclusion == "attributed"
    assert first.report_schema_version == "probe-report/v2"
    assert first.report_payload is not None
    assert first.execution_manifest_hash == first.cache_key
    linked = await attribution_repository.linked_probe_ids(RUN_ID)
    assert set(linked) == {CASE_ID, OTHER_CASE_ID}
    assert linked[CASE_ID] == first.probe_id
    assert await probe_count(attribution_harness.database) == 2


async def test_second_run_reuses_the_cache_and_counts_once(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """A different run with the same case reuses the probe and marks is_cached."""
    first_run = await load_run(attribution_harness.database)
    runner = AttributionRunner(attribution_repository)
    await runner.run(first_run, (potential_case(),), cache_enabled=True)

    second_run = await load_run(attribution_harness.database, OTHER_RUN_ID)
    summary = await runner.run(second_run, (potential_case(),), cache_enabled=True)

    assert summary.reused == 1
    assert summary.created == 0
    cached = await attribution_repository.get_probe_by_cache_key(
        runner_cache_key(),
    )
    assert cached is not None
    assert cached.reused_count == 1
    assert cached.last_reused_run_id == OTHER_RUN_ID
    record = await candidate(attribution_harness.database, OTHER_RUN_ID)
    assert record.probe_id == cached.probe_id
    assert record.is_cached is True


async def test_rerunning_the_same_run_skips_already_linked_candidates(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """Resume never recomputes or recounts a candidate that already has a probe."""
    run = await load_run(attribution_harness.database)
    engine = CountingEngine()
    runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: engine,
    )
    await runner.run(run, (potential_case(),), cache_enabled=True)

    summary = await runner.run(run, (potential_case(),), cache_enabled=True)

    assert summary.skipped == 1
    assert summary.created == 0
    assert summary.reused == 0
    assert engine.calls == [CASE_ID]


async def test_cache_off_recomputes_and_overwrites_the_same_key(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """Disabling the cache refreshes the probe row instead of appending history."""
    first_run = await load_run(attribution_harness.database)
    engine = CountingEngine()
    runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: engine,
    )
    await runner.run(first_run, (potential_case(),), cache_enabled=True)

    where = probe_reports.c.session_id == SESSION_ID
    async with attribution_harness.database.session() as session:
        first_updated_at: datetime = (
            await session.execute(select(probe_reports.c.updated_at).where(where))
        ).scalar_one()

    second_run = await load_run(attribution_harness.database, OTHER_RUN_ID)
    runner_off = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: engine,
    )
    summary = await runner_off.run(second_run, (potential_case(),), cache_enabled=False)

    assert summary.reused == 0
    assert summary.created == 1
    async with attribution_harness.database.session() as session:
        rows = (await session.execute(select(probe_reports).where(where))).mappings().all()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["created_run_id"] == OTHER_RUN_ID
    assert row["reused_count"] == 0
    assert row["probe_description"] == "第 2 次归因"
    assert row["updated_at"] != first_updated_at
    record = await candidate(attribution_harness.database, OTHER_RUN_ID)
    assert record.is_cached is False


async def test_engine_failure_blocks_the_run_and_resume_only_fills_the_rest(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """A failed attribution leaves earlier rows durable and resumes unfinished cases."""
    run = await load_run(attribution_harness.database)
    failing = CountingEngine(fail_on_call=2)
    runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: failing,
    )

    with pytest.raises(RunBlocked) as blocked:
        await runner.run(
            run,
            (potential_case(), potential_case(OTHER_CASE_ID)),
            cache_enabled=True,
        )
    assert blocked.value.stage == "attribution"
    assert blocked.value.error_stage == "prepare"
    linked = await attribution_repository.linked_probe_ids(RUN_ID)
    assert set(linked) == {CASE_ID}
    async with attribution_harness.database.session() as session:
        first_updated_at: datetime = (
            await session.execute(
                select(probe_reports.c.updated_at).where(
                    probe_reports.c.probe_id == linked[CASE_ID],
                ),
            )
        ).scalar_one()

    resume = CountingEngine()
    resumed_runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: resume,
        now=lambda: datetime(2026, 11, 17, 11, 0, tzinfo=SHANGHAI),
    )
    summary = await resumed_runner.run(
        run,
        (potential_case(), potential_case(OTHER_CASE_ID)),
        cache_enabled=True,
    )

    assert summary.skipped == 1
    assert summary.created == 1
    assert resume.calls == [OTHER_CASE_ID]
    async with attribution_harness.database.session() as session:
        unchanged: datetime = (
            await session.execute(
                select(probe_reports.c.updated_at).where(
                    probe_reports.c.probe_id == linked[CASE_ID],
                ),
            )
        ).scalar_one()
    assert unchanged == first_updated_at
    resumed_links = await attribution_repository.linked_probe_ids(RUN_ID)
    assert len(resumed_links) == 2
    assert resumed_links[CASE_ID] == linked[CASE_ID]


async def test_non_target_is_persisted_but_not_clusterable(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """A non-target conclusion stays visible and stays out of the cluster input."""
    run = await load_run(attribution_harness.database)
    engine = CountingEngine()
    runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: engine,
    )
    summary = await runner.run(run, (potential_case(OTHER_CASE_ID),), cache_enabled=True)

    assert summary.non_target == 1
    records = await attribution_repository.list_attributions(OTHER_CASE_ID)
    assert len(records) == 1
    assert records[0].conclusion == "non_target"
    assert records[0].attribute_type is None
    assert await attribution_repository.list_clusterable_probe_ids(RUN_ID) == ()


async def test_rule_engine_receives_knowledge_evidence(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """The runner batches knowledge document triggers into the pure engine input."""
    run = await load_run(attribution_harness.database)
    runner = AttributionRunner(attribution_repository)
    await runner.run(run, (potential_case(),), cache_enabled=True)

    records = await attribution_repository.list_attributions(CASE_ID)
    assert len(records) == 1
    assert KNOWLEDGE_DOCUMENT_ID in records[0].probe_analysis
    assert "/kb/retrieval.md" in records[0].probe_analysis


async def test_excluded_candidates_are_not_attributed(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """Policy-excluded rows stay as candidates only; they get no probe."""
    run = await load_run(attribution_harness.database)
    summary = await AttributionRunner(attribution_repository).run(
        run,
        (potential_case(included=False, hit_reason="policy_excluded"),),
        cache_enabled=True,
    )

    assert summary.processed == 0
    assert summary.created == 0
    assert await probe_count(attribution_harness.database) == 0


async def test_two_runs_racing_on_one_case_keep_one_probe(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """Concurrent first runs still converge on the cache-key unique row."""
    first = await load_run(attribution_harness.database)
    second = await load_run(attribution_harness.database, OTHER_RUN_ID)
    runner = AttributionRunner(attribution_repository)

    await asyncio.gather(
        runner.run(first, (potential_case(),), cache_enabled=True),
        runner.run(second, (potential_case(),), cache_enabled=True),
    )

    assert await probe_count(attribution_harness.database) == 1
    assert set(await attribution_repository.linked_probe_ids(RUN_ID)) == {CASE_ID}
    assert set(await attribution_repository.linked_probe_ids(OTHER_RUN_ID)) == {CASE_ID}


class InvalidResultEngine:
    """Engine double that violates the result contract."""

    key = "rule-v1"

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Raise a validation error that must fail the job, not block the run."""
        del item
        return AttributionResult(
            conclusion="attributed",
            category=None,
            confidence=0.8,
            reason="invalid",
            reasoning="invalid",
        )


async def test_invalid_engine_result_fails_instead_of_blocking(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """A programming/validation error must not masquerade as a retryable block."""
    run = await load_run(attribution_harness.database)
    runner = AttributionRunner(
        attribution_repository,
        engine_factory=lambda key: InvalidResultEngine(),
    )

    with pytest.raises(ValueError, match="category"):
        await runner.run(run, (potential_case(),), cache_enabled=True)
    assert await probe_count(attribution_harness.database) == 0
