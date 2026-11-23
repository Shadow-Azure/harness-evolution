"""One potential count shared by preview, overview, and the prepared run.

All three surfaces receive the same condition here: target ``deep-research``
version ``v2.0.0`` and the inclusive window ``2026-11-01``..``2026-11-30``. The
target stores that version as its ``defaultRef`` and every trigger event stores
the same ``object_version``/``object_revision``, so the overview's per-version
matcher call and the wizard's explicit version resolve to one identical
condition rather than two approximations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest
import pytest_asyncio

from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.models.domain import probe_reports
from app.service.evolution.attribution import (
    AttributionEngine,
    AttributionInput,
    AttributionResult,
)
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    seed_case,
    seed_event,
    seed_session,
    seed_target,
    seed_workspace,
    table_count,
)
from tests.v2_acceptance_support import (
    AcceptanceApi,
    Identity,
    prepare_job,
    prepare_service,
    seed_identity,
    seed_run,
)
from tests.v2_acceptance_support import acceptance_api as acceptance_api

WORKSPACE_A = "ws-m11-05-consistency-a"
WORKSPACE_B = "ws-m11-05-consistency-b"
TARGET_A = "target-m11-05-consistency"
TARGET_B = "target-m11-05-consistency-b"
TARGET_NAME = "deep-research"
TARGET_VERSION = "v2.0.0"
RUN_ATTRIBUTED = "run-m11-05-consistency-a"
RUN_REUSED = "run-m11-05-consistency-b"
WINDOW = {"from": "2026-11-01", "to": "2026-11-30"}

SESSION_SELF = "m11-05-consistency-session-self"
SESSION_DISCOVERY = "m11-05-consistency-session-discovery"
SESSION_OTHER_SPACE = "m11-05-consistency-session-other"
CASE_AFTER = "case-m11-05-after"
CASE_NON_TARGET = "case-m11-05-non-target"
CASE_SELF = "case-m11-05-self"
CASE_EXCLUDED = "case-m11-05-excluded"
CASE_OTHER_SPACE = "case-m11-05-other-space"
POTENTIAL = 3


def _at(hour: int, minute: int) -> datetime:
    """Return one deterministic Asia/Shanghai instant on 2026-11-17."""
    return datetime(2026, 11, 17, hour, minute, tzinfo=SHANGHAI)


@dataclass(frozen=True, slots=True)
class Consistency:
    """The seeded two-workspace scenario plus the reader identities."""

    api: AcceptanceApi
    identities: dict[str, Identity]


class NonTargetEngine:
    """Attribute every case except one designated non-target case."""

    key = "rule-v1"

    def __init__(self, non_target_case: str) -> None:
        """Remember the single case that must not enter a cluster."""
        self._non_target_case = non_target_case
        self.calls: list[str] = []

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Return one stable conclusion without external evidence."""
        self.calls.append(item.bad_case_id)
        if item.bad_case_id == self._non_target_case:
            return AttributionResult(
                conclusion="non_target",
                category=None,
                confidence=0.7,
                reason="not this object",
                reasoning="evidence belongs to a different object",
            )
        return AttributionResult(
            conclusion="attributed",
            category="error",
            confidence=0.8,
            reason="object defect",
            reasoning="error evidence exists",
        )


class CountingEngine:
    """Count engine calls so a cache-only run can assert zero fresh work."""

    key = "rule-v1"

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[str] = []

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Return one attributed conclusion and record the call."""
        self.calls.append(item.bad_case_id)
        return AttributionResult(
            conclusion="attributed",
            category="error",
            confidence=0.8,
            reason="object defect",
            reasoning="error evidence exists",
        )


def _preview_body() -> dict[str, object]:
    """Return the wizard potential condition shared by every assertion."""
    return {
        "targetType": "skill",
        "targetName": TARGET_NAME,
        "targetVersion": TARGET_VERSION,
        **WINDOW,
    }


def _preview_path(workspace_id: str = WORKSPACE_A) -> str:
    """Return the wizard potential preview path."""
    return f"/api/workspaces/{workspace_id}/evolution/preview/potential"


def _overview_path(workspace_id: str = WORKSPACE_A) -> str:
    """Return the evolution-target overview path with the shared window."""
    return (
        f"/api/workspaces/{workspace_id}/overview/targets?from={WINDOW['from']}&to={WINDOW['to']}"
    )


async def _prepare(
    api: AcceptanceApi,
    run_id: str,
    engine: AttributionEngine,
) -> None:
    """Run the real M10-04 prepare pipeline with one deterministic engine."""
    service = prepare_service(
        api.database,
        engine_factory=lambda _key: engine,
    )
    await service.handle(prepare_job(run_id))


async def _seed_consistency(api: AcceptanceApi) -> Consistency:
    """Seed the target, both Sessions, every trigger kind, and five cases."""
    database = api.database
    await seed_workspace(database, WORKSPACE_A)
    await seed_workspace(database, WORKSPACE_B)
    identities = {
        role: await seed_identity(
            api.app,
            database,
            username=f"m11-05-consistency-{role}",
            workspace_id=WORKSPACE_A,
            workspace_role=role,
        )
        for role in ("viewer", "member", "space_admin")
    }
    await seed_target(
        database,
        workspace_id=WORKSPACE_A,
        target_id=TARGET_A,
        object_name=TARGET_NAME,
        default_ref=TARGET_VERSION,
    )
    await seed_target(
        database,
        workspace_id=WORKSPACE_B,
        target_id=TARGET_B,
        object_name=TARGET_NAME,
        default_ref=TARGET_VERSION,
    )

    self_main = await seed_session(
        database,
        session_id=SESSION_SELF,
        started_at=_at(9, 0),
        title="self session",
    )
    await seed_event(
        database,
        agent_id=self_main,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=_at(10, 0),
    )
    await seed_event(
        database,
        agent_id=self_main,
        event_index=1,
        kind="skill",
        name="other-skill",
        triggered_at=_at(10, 20),
    )
    await seed_event(
        database,
        agent_id=self_main,
        event_index=2,
        kind="agent",
        name="Explore",
        object_version="v1.0.0",
        triggered_at=_at(10, 5),
    )
    await seed_event(
        database,
        agent_id=self_main,
        event_index=3,
        kind="knowledge",
        name="kb-doc",
        object_revision="digest:" + "a" * 64,
        triggered_at=_at(10, 6),
    )
    await seed_case(
        database,
        case_id=CASE_AFTER,
        session_id=SESSION_SELF,
        workspace_id=WORKSPACE_A,
        case_type="discovery",
        object_name="other-skill",
        created_at=_at(10, 40),
    )
    await seed_case(
        database,
        case_id=CASE_SELF,
        session_id=SESSION_SELF,
        workspace_id=WORKSPACE_A,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=_at(9, 0),
    )

    discovery_main = await seed_session(
        database,
        session_id=SESSION_DISCOVERY,
        started_at=_at(9, 0),
        title="discovery session",
    )
    await seed_event(
        database,
        agent_id=discovery_main,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=_at(11, 0),
    )
    await seed_event(
        database,
        agent_id=discovery_main,
        event_index=1,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=_at(11, 10),
    )
    await seed_event(
        database,
        agent_id=discovery_main,
        event_index=2,
        kind="skill",
        name="other-skill",
        triggered_at=_at(10, 30),
    )
    await seed_case(
        database,
        case_id=CASE_NON_TARGET,
        session_id=SESSION_DISCOVERY,
        workspace_id=WORKSPACE_A,
        case_type="discovery",
        object_name=TARGET_NAME,
        created_at=_at(11, 30),
    )
    await seed_case(
        database,
        case_id=CASE_EXCLUDED,
        session_id=SESSION_DISCOVERY,
        workspace_id=WORKSPACE_A,
        case_type="discovery",
        object_name="other-skill",
        created_at=_at(10, 30),
    )

    other_main = await seed_session(
        database,
        session_id=SESSION_OTHER_SPACE,
        started_at=_at(9, 0),
        title="other space session",
    )
    await seed_event(
        database,
        agent_id=other_main,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=_at(10, 0),
    )
    await seed_case(
        database,
        case_id=CASE_OTHER_SPACE,
        session_id=SESSION_OTHER_SPACE,
        workspace_id=WORKSPACE_B,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=_at(10, 30),
    )

    for run_id in (RUN_ATTRIBUTED, RUN_REUSED):
        await seed_run(
            database,
            run_id=run_id,
            workspace_id=WORKSPACE_A,
            target_name=TARGET_NAME,
            target_version=TARGET_VERSION,
        )
    return Consistency(api=api, identities=identities)


@pytest_asyncio.fixture
async def consistency(acceptance_api: AcceptanceApi) -> Consistency:
    """Seed the shared potential-consistency scenario."""
    return await _seed_consistency(acceptance_api)


async def test_preview_overview_and_run_share_one_potential_count(
    consistency: Consistency,
) -> None:
    """Wizard total, overview item potential, and included candidates are equal."""
    api = consistency.api
    headers = consistency.identities["viewer"].headers

    preview = await api.client.post(
        _preview_path(),
        headers=headers,
        json=_preview_body(),
    )
    overview = await api.client.get(_overview_path(), headers=headers)
    await _prepare(api, RUN_ATTRIBUTED, NonTargetEngine(CASE_NON_TARGET))

    candidates = await EvolutionRunCandidateRepository(api.database).list(RUN_ATTRIBUTED)
    included = [candidate for candidate in candidates if candidate.included]
    run = await EvolutionRepository(api.database).get_run(RUN_ATTRIBUTED)

    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["summary"]["potential"] == POTENTIAL
    assert preview_body["total"] == POTENTIAL
    assert preview_body["summary"]["badCases"] == 4
    assert preview_body["summary"]["byReason"] == {
        "selfReport": 1,
        "afterObject": 2,
        "both": 0,
        "policyExcluded": 1,
        "orderUnknown": 0,
    }

    assert overview.status_code == 200
    overview_body = overview.json()
    assert overview_body["summary"]["potential"] == POTENTIAL
    assert overview_body["items"][0]["targetId"] == TARGET_A
    assert overview_body["items"][0]["potential"] == POTENTIAL

    assert run is not None
    assert run.stats["potential"] == POTENTIAL
    assert len(included) == POTENTIAL
    assert preview_body["total"] == overview_body["items"][0]["potential"] == len(included)


async def test_cache_reuse_equals_potential_and_non_target_stays_out_of_clusters(
    consistency: Consistency,
) -> None:
    """A second attribution run reuses every cache key while non-target stays visible."""
    api = consistency.api
    first_engine = NonTargetEngine(CASE_NON_TARGET)
    await _prepare(api, RUN_ATTRIBUTED, first_engine)

    preview = await api.client.post(
        f"/api/workspaces/{WORKSPACE_A}/evolution/preview/attribution",
        headers=consistency.identities["viewer"].headers,
        json=_preview_body(),
    )
    assert preview.status_code == 200
    assert preview.json()["summary"] == {
        "potential": POTENTIAL,
        "reused": POTENTIAL,
        "missing": 0,
        "bySkill": {},
        "fresh": 0,
        "nonTargetKnown": 1,
    }

    second_engine = CountingEngine()
    await _prepare(api, RUN_REUSED, second_engine)
    reused = await EvolutionRepository(api.database).get_run(RUN_REUSED)
    reused_candidates = await EvolutionRunCandidateRepository(api.database).list(RUN_REUSED)
    attributed = AttributionRepository(api.database)

    assert reused is not None
    assert reused.stats["potential"] == POTENTIAL
    assert reused.stats["reused"] == POTENTIAL
    assert reused.stats["attributed"] == POTENTIAL - 1
    assert len([item for item in reused_candidates if item.included]) == POTENTIAL
    assert second_engine.calls == []
    assert await table_count(api.database, probe_reports) == POTENTIAL

    non_target_records = await attributed.list_attributions(CASE_NON_TARGET)
    assert len(non_target_records) == 1
    assert non_target_records[0].conclusion == "non_target"
    assert non_target_records[0].attribute_type is None
    clusterable = await attributed.list_clusterable_probes(RUN_ATTRIBUTED)
    assert len(clusterable) == POTENTIAL - 1
    assert CASE_NON_TARGET not in {case_id for _, _, case_id in clusterable}
    stored = next(
        item
        for item in await EvolutionRunCandidateRepository(api.database).list(
            RUN_ATTRIBUTED,
        )
        if item.bad_case_id == CASE_NON_TARGET
    )
    assert stored.included is True
    assert stored.probe_id == non_target_records[0].probe_id


@pytest.mark.parametrize("role", ["viewer", "member", "space_admin"])
async def test_role_scoping_keeps_the_same_workspace_count(
    consistency: Consistency,
    role: str,
) -> None:
    """Every in-space role sees the same workspace-scoped potential total."""
    api = consistency.api
    headers = consistency.identities[role].headers

    preview = await api.client.post(
        _preview_path(),
        headers=headers,
        json=_preview_body(),
    )
    overview = await api.client.get(_overview_path(), headers=headers)

    assert preview.status_code == 200
    assert overview.status_code == 200
    assert preview.json()["total"] == POTENTIAL
    assert overview.json()["items"][0]["potential"] == POTENTIAL
    assert preview.json()["summary"]["potential"] == overview.json()["summary"]["potential"]
