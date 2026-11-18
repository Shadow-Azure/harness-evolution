"""End-to-end prepare coverage for the m12-04 lexical clustering upgrade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy import update

from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.models.domain import bad_cases
from app.db.models.jobs import JobRunRecord
from app.service.evolution.attribution import AttributionRunner, RuleBasedEngine
from app.service.evolution.cluster import CLUSTER_ALGORITHM, SIMILARITY_THRESHOLD
from app.service.evolution.events import EvolutionRunEventStage, EvolutionRunEventType
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

RUN_ID = "run-m12-04"
SESSION_ID = "session-m12-04"

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True, slots=True)
class _RecordedEvent:
    """One prepare event captured for payload assertions."""

    event_type: str
    stage: str
    payload: Mapping[str, Any] | None


class RecordingEvents:
    """Capture prepare events without touching the event table."""

    def __init__(self) -> None:
        """Start with no recorded events."""
        self.records: list[_RecordedEvent] = []

    async def record(
        self,
        run_id: str,
        event_type: EvolutionRunEventType,
        *,
        level: str,
        stage: EvolutionRunEventStage,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> object:
        """Keep the event fields the clustering contract needs."""
        del run_id, level, message, step_index, cluster_id, round_id, job_id, error
        self.records.append(
            _RecordedEvent(event_type=str(event_type), stage=str(stage), payload=payload),
        )
        return object()


class UnusedWorkspacePreparer:
    """Fail if a cluster-only run tries to prepare a git workspace."""

    async def prepare(self, run: object) -> PreparedWorkspace:
        """Reject unexpected workspace work."""
        del run
        raise AssertionError("cluster-only prepare must not touch git")


def _job() -> JobRunRecord:
    """Build one evolution_prepare job row for the service under test."""
    now = datetime(2026, 11, 18, 9, 0, tzinfo=SHANGHAI)
    return JobRunRecord(
        id="job-m12-04",
        kind="evolution_prepare",
        ref_id=RUN_ID,
        status="running",
        progress=0.0,
        executor="test",
        external_job_id=None,
        attempt=1,
        payload={"runId": RUN_ID},
        result=None,
        error=None,
        created_by=None,
        created_at=now,
        started_at=now,
        finished_at=None,
        updated_at=now,
    )


async def _create_cluster_only_run(harness: Harness) -> None:
    """Insert one cluster-only run snapshot over the shared workspace fixture."""
    await EvolutionRepository(harness.database).create_run(
        {
            "id": RUN_ID,
            "title": f"{TARGET_NAME} {TARGET_VERSION} 聚类预览",
            "workspace_id": WORKSPACE_A,
            "mode": "cluster_only",
            "engine_key": "cluster_only",
            "eval_config": {},
            "potential_policy": {"preset": "default"},
            "cache_enabled": True,
            "attribution_engine": "rule-v1",
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


async def _seed_titled_cases(harness: Harness) -> dict[str, str]:
    """Seed three self-reported cases whose titles carry the clustering signal."""
    main = await seed_session(
        harness.database,
        session_id=SESSION_ID,
        started_at=NOW,
        title="m12-04 聚类",
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
    titles = {
        "case-m12-04-a": "检索索引读取失败",
        "case-m12-04-b": "检索索引读取超时",
        "case-m12-04-c": "工具调用超时",
    }
    for case_id in titles:
        await seed_case(
            harness.database,
            case_id=case_id,
            session_id=SESSION_ID,
            case_type="self",
            agent_id=main,
        )
    async with harness.database.transaction() as session:
        for case_id, title in titles.items():
            await session.execute(
                update(bad_cases)
                .where(bad_cases.c.bad_case_id == case_id)
                .values(title=title, bad_case_description=title),
            )
    return titles


def _service(harness: Harness, events: RecordingEvents) -> EvolutionPrepareService:
    """Compose the prepare service over the migrated test database."""
    attributions = AttributionRepository(harness.database)
    return EvolutionPrepareService(
        EvolutionRepository(harness.database),
        EvolutionRunCandidateRepository(harness.database),
        attributions,
        harness.matcher,
        AttributionRunner(attributions, engine_factory=lambda _key: RuleBasedEngine()),
        UnusedWorkspacePreparer(),
        events,
    )


async def test_cluster_only_prepare_writes_title_clusters_and_audit_payload(
    harness: Harness,
) -> None:
    """The upgraded algorithm keeps the same tables and records its run parameters."""
    await _seed_titled_cases(harness)
    await _create_cluster_only_run(harness)
    events = RecordingEvents()

    await _service(harness, events).handle(_job())

    runs = EvolutionRepository(harness.database)
    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 5
    assert run.status == "completed"
    assert (run.stats or {}).get("clusters") == 2

    clusters = await runs.list_clusters(RUN_ID)
    assert [cluster.probe_cluster_type for cluster in clusters] == ["prompt", "prompt"]
    assert [cluster.probe_cluster_description for cluster in clusters] == [
        "prompt 类问题 · 检索索引读取失败",  # noqa: RUF001
        "prompt 类问题 · 工具调用超时",  # noqa: RUF001
    ]
    assert [cluster.rank for cluster in clusters] == [1, 2]
    assert all(cluster.confidence == pytest.approx(0.74) for cluster in clusters)
    assert all(cluster.impact == pytest.approx(7.0) for cluster in clusters)
    assert all(cluster.severity is not None for cluster in clusters)

    candidates = await EvolutionRunCandidateRepository(harness.database).list(RUN_ID)
    probe_by_case = {candidate.bad_case_id: candidate.probe_id for candidate in candidates}
    probe_a = probe_by_case["case-m12-04-a"]
    probe_b = probe_by_case["case-m12-04-b"]
    probe_c = probe_by_case["case-m12-04-c"]
    links = await runs.list_cluster_probes(RUN_ID)
    members = {
        cluster.probe_cluster_id: tuple(
            link.probe_id for link in links if link.probe_cluster_id == cluster.probe_cluster_id
        )
        for cluster in clusters
    }
    assert list(members.values()) == [(probe_a, probe_b), (probe_c,)]

    created = next(event for event in events.records if event.event_type == "clusters_created")
    assert created.stage == "cluster"
    assert created.payload is not None
    assert created.payload["clusters"] == 2
    assert created.payload["algorithm"] == CLUSTER_ALGORITHM
    assert created.payload["similarityThreshold"] == SIMILARITY_THRESHOLD
    fingerprint = str(created.payload["clusterHash"])
    assert len(fingerprint) == 64
    assert set(fingerprint) <= set("0123456789abcdef")
