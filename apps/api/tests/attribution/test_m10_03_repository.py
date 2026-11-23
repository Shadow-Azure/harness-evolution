"""Cache lookup, atomic link writes, evidence batches, and cluster projections."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.db.crud.attributions import (
    AttributionRepository,
    EvolutionRunCandidateRepository,
)
from app.db.models.domain import agent_events, bad_case_analysis, probe_reports
from app.db.models.evolution import evolution_run_candidates
from app.utils.time import as_shanghai
from tests.attribution.support import (
    CASE_ID,
    KNOWLEDGE_DOCUMENT_ID,
    KNOWLEDGE_REVISION,
    LATER,
    NOW,
    ORPHAN_CASE_ID,
    OTHER_CASE_ID,
    OTHER_RUN_ID,
    RUN_ID,
    SESSION_ID,
    TARGET_NAME,
    TARGET_VERSION,
    Harness,
    candidate_write,
    probe_write,
)


async def test_write_probe_and_link_updates_all_three_rows_atomically(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """One transaction writes the probe, the case link, and the candidate pointer."""
    probe = probe_write()
    probe_id = await attribution_repository.write_probe_and_link(
        probe,
        RUN_ID,
        NOW,
    )

    assert probe_id == probe.probe_id
    cached = await attribution_repository.get_probe_by_cache_key(probe.cache_key)
    assert cached is not None
    assert cached.conclusion == "attributed"
    assert cached.attribute_type == "error"
    assert cached.object_version == "tag:v2.0.0"
    assert await attribution_repository.attribution_count(CASE_ID) == 1
    linked = await attribution_repository.linked_probe_ids(RUN_ID)
    assert linked[CASE_ID] == probe.probe_id
    rows = await EvolutionRunCandidateRepository(
        attribution_harness.database,
    ).list(RUN_ID)
    candidate = next(row for row in rows if row.bad_case_id == CASE_ID)
    assert candidate.probe_id == probe.probe_id
    assert candidate.is_cached is False


async def test_missing_candidate_row_rolls_back_probe_and_link(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """A candidate pointer write cannot leave an orphan probe behind."""
    probe = probe_write(ORPHAN_CASE_ID, probe_id="probe-orphan")

    with pytest.raises(LookupError, match="candidate"):
        await attribution_repository.write_probe_and_link(probe, RUN_ID, NOW)

    async with attribution_harness.database.session() as session:
        probes = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(probe_reports)
                    .where(probe_reports.c.probe_id == probe.probe_id),
                )
            ).scalar_one(),
        )
        links = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(bad_case_analysis)
                    .where(bad_case_analysis.c.bad_case_id == ORPHAN_CASE_ID),
                )
            ).scalar_one(),
        )
    assert probes == 0
    assert links == 0


async def test_reuse_counts_once_per_run_and_marks_the_candidate_cached(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """A cache hit advances the counter once per run and links the second run."""
    probe = probe_write()
    await attribution_repository.write_probe_and_link(probe, RUN_ID, NOW)

    assert await attribution_repository.reuse_probe_and_link(
        probe.probe_id,
        OTHER_RUN_ID,
        CASE_ID,
        LATER,
    )
    assert not await attribution_repository.reuse_probe_and_link(
        probe.probe_id,
        OTHER_RUN_ID,
        CASE_ID,
        LATER,
    )

    cached = await attribution_repository.get_probe_by_cache_key(probe.cache_key)
    assert cached is not None
    assert cached.reused_count == 1
    assert cached.last_reused_run_id == OTHER_RUN_ID
    assert cached.updated_at == as_shanghai(LATER)
    rows = await EvolutionRunCandidateRepository(
        attribution_harness.database,
    ).list(OTHER_RUN_ID)
    candidate = next(row for row in rows if row.bad_case_id == CASE_ID)
    assert candidate.probe_id == probe.probe_id
    assert candidate.is_cached is True


async def test_reuse_rejects_a_missing_candidate_row(
    attribution_repository: AttributionRepository,
) -> None:
    """Reusing a probe still requires the run candidate snapshot to exist."""
    probe = probe_write()
    await attribution_repository.write_probe_and_link(probe, RUN_ID, NOW)

    with pytest.raises(LookupError, match="candidate"):
        await attribution_repository.reuse_probe_and_link(
            probe.probe_id,
            RUN_ID,
            ORPHAN_CASE_ID,
            NOW,
        )


async def test_linked_probe_ids_are_scoped_to_one_run(
    attribution_repository: AttributionRepository,
) -> None:
    """Resume only sees the current run's persisted pointers."""
    first = probe_write()
    await attribution_repository.write_probe_and_link(first, RUN_ID, NOW)

    assert await attribution_repository.linked_probe_ids(RUN_ID) == {
        CASE_ID: first.probe_id,
    }
    assert await attribution_repository.linked_probe_ids(OTHER_RUN_ID) == {}


async def test_clusterable_probes_exclude_non_target_and_excluded_candidates(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """Only included attributed candidates reach the cluster projection."""
    attributed = probe_write()
    non_target = probe_write(
        OTHER_CASE_ID,
        probe_id="probe-non-target",
        conclusion="non_target",
        attribute_type=None,
    )
    await attribution_repository.write_probe_and_link(attributed, RUN_ID, NOW)
    await attribution_repository.write_probe_and_link(non_target, RUN_ID, NOW)
    excluded = probe_write(
        ORPHAN_CASE_ID,
        probe_id="probe-excluded",
    )
    await EvolutionRunCandidateRepository(attribution_harness.database).upsert(
        candidate_write(ORPHAN_CASE_ID, included=False, hit_reason="policy_excluded"),
    )
    await attribution_repository.write_probe_and_link(excluded, RUN_ID, NOW)

    assert await attribution_repository.list_clusterable_probe_ids(RUN_ID) == (attributed.probe_id,)


async def test_bad_case_evidence_is_loaded_in_one_batch(
    attribution_repository: AttributionRepository,
) -> None:
    """Attribution input metadata and descriptions come from bad_cases."""
    evidence = await attribution_repository.load_bad_case_evidence(
        (CASE_ID, OTHER_CASE_ID),
    )

    assert set(evidence) == {CASE_ID, OTHER_CASE_ID}
    assert evidence[CASE_ID].title == "检索索引读取失败"
    assert evidence[CASE_ID].description == "deep-research 读取索引时未校验快照字段"
    assert evidence[CASE_ID].metadata == {"error": "ENOENT", "file": "index.ts"}
    assert evidence[CASE_ID].object_name == TARGET_NAME
    assert evidence[CASE_ID].object_version == TARGET_VERSION
    assert evidence[OTHER_CASE_ID].bad_case_type == "discovery"


async def test_knowledge_evidence_is_loaded_from_the_case_session(
    attribution_repository: AttributionRepository,
) -> None:
    """Knowledge document triggers are batched by session for reasoning."""
    knowledge = await attribution_repository.load_knowledge_evidence((SESSION_ID,))

    assert len(knowledge[SESSION_ID]) == 1
    event = knowledge[SESSION_ID][0]
    assert event.document_id == KNOWLEDGE_DOCUMENT_ID
    assert event.document_revision == KNOWLEDGE_REVISION
    assert event.source_path == "/kb/retrieval.md"
    assert event.retrieval_kind == "file_read"


async def test_digest_revision_round_trips_in_the_widened_column(
    attribution_repository: AttributionRepository,
) -> None:
    """A 71-character digest revision is a first-class probe identity."""
    revision = "digest:" + "b" * 64
    probe = probe_write(object_version=revision)
    await attribution_repository.write_probe_and_link(probe, RUN_ID, NOW)

    cached = await attribution_repository.get_probe_by_cache_key(probe.cache_key)
    assert cached is not None
    assert cached.object_version == revision


async def test_concurrent_writers_converge_on_one_probe_and_both_candidates(
    attribution_harness: Harness,
    attribution_repository: AttributionRepository,
) -> None:
    """Two runs racing on one cache key keep one probe and two candidate pointers."""
    probe_ids = await asyncio.gather(
        attribution_repository.write_probe_and_link(
            probe_write(probe_id="probe-race-a"),
            RUN_ID,
            NOW,
        ),
        attribution_repository.write_probe_and_link(
            probe_write(probe_id="probe-race-b"),
            OTHER_RUN_ID,
            NOW,
        ),
    )

    assert len(set(probe_ids)) == 1
    async with attribution_harness.database.session() as session:
        count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(probe_reports)
                    .where(probe_reports.c.session_id == SESSION_ID),
                )
            ).scalar_one(),
        )
        candidates = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(evolution_run_candidates)
                    .where(
                        evolution_run_candidates.c.run_id.in_((RUN_ID, OTHER_RUN_ID)),
                        evolution_run_candidates.c.probe_id.is_not(None),
                    ),
                )
            ).scalar_one(),
        )
    assert count == 1
    assert candidates == 2


async def test_non_target_probe_is_visible_through_the_case_read_model(
    attribution_repository: AttributionRepository,
    attribution_harness: Harness,
) -> None:
    """A non-target probe stays readable even though it has no category."""
    probe = probe_write(
        OTHER_CASE_ID,
        probe_id="probe-non-target-read",
        conclusion="non_target",
        attribute_type=None,
    )
    await attribution_repository.write_probe_and_link(probe, RUN_ID, NOW)

    records = await attribution_repository.list_attributions(OTHER_CASE_ID)
    assert [record.probe_id for record in records] == [probe.probe_id]
    assert records[0].conclusion == "non_target"
    assert records[0].attribute_type is None
    assert await attribution_repository.attribution_count(OTHER_CASE_ID) == 1


async def test_knowledge_event_query_does_not_cross_sessions(
    attribution_repository: AttributionRepository,
    attribution_harness: Harness,
) -> None:
    """Knowledge evidence is keyed by the case session, not the whole workspace."""
    evidence = await attribution_repository.load_knowledge_evidence(
        ("97000000-0000-4000-8000-000000000099",),
    )
    assert evidence == {}

    async with attribution_harness.database.session() as session:
        count = int(
            (await session.execute(select(func.count()).select_from(agent_events))).scalar_one(),
        )
    assert count == 1
