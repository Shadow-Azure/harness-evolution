"""Body-hash association and post-process anchoring in the shared matcher."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import pytest
from sqlalchemy import insert, select

from app.db.crud.potential import ObjectType, window_day_boundaries
from app.db.models.domain import agent_events
from app.db.models.evolution import evolution_run_candidates, evolution_runs
from app.service.evolution.potential import MatchCondition, resolve_policy
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    Harness,
    seed_agent,
    seed_case,
    seed_session,
)
from tests.v2_acceptance_support import prepare_job, prepare_service

BODY_HASH = "a" * 64
"""One deterministic normalized body hash shared by every identity assertion."""

DIAGNOSTIC_REVISION = "digest:" + "b" * 64
"""A legacy/diagnostic revision that must not be required for matching."""

OBJECT_ENTRY = datetime(2026, 11, 17, 9, 30, tzinfo=SHANGHAI)
AFTER_ENTRY = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)


def body_hash_condition(target_type: ObjectType) -> MatchCondition:
    """Build the documented body-hash condition for one object type."""
    start, end = window_day_boundaries(
        datetime(2026, 11, 1, tzinfo=SHANGHAI).date(),
        datetime(2026, 11, 30, tzinfo=SHANGHAI).date(),
    )
    return MatchCondition(
        workspace_id="ws-m10-02-a",
        target_type=target_type,
        target_name=TARGET_NAME,
        target_version=TARGET_VERSION,
        target_revision=f"digest:{BODY_HASH}",
        window_start=start,
        window_end=end,
    )


async def _seed_event_with_identity(
    harness: Harness,
    *,
    agent_id: str,
    event_index: int,
    kind: str,
    name: str,
    definition_hash: str | None = None,
    document_revision: str | None = None,
    object_revision: str | None = None,
    object_version: str | None = None,
) -> None:
    """Insert one trigger row carrying explicit body-hash evidence."""
    async with harness.database.transaction() as session:
        await session.execute(
            insert(agent_events).values(
                agent_id=agent_id,
                event_index=event_index,
                line_no=event_index + 1,
                message_offset=event_index,
                kind=kind,
                name=name,
                object_version=object_version,
                object_revision=object_revision,
                definition_hash=definition_hash,
                document_revision=document_revision,
                triggered_at=OBJECT_ENTRY,
            ),
        )


@pytest.mark.parametrize("target_type", ["skill", "agent", "knowledge"])
async def test_association_accepts_the_body_hash_for_every_object_type(
    harness: Harness,
    target_type: str,
) -> None:
    """definition_hash/document_revision identify skill, agent, and knowledge."""
    session_id = f"session-body-hash-{target_type}"
    main_id = await seed_session(harness.database, session_id=session_id)
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=0,
        kind=target_type,
        name=TARGET_NAME,
        definition_hash=BODY_HASH,
        document_revision=f"digest:{BODY_HASH}" if target_type == "knowledge" else None,
        object_revision=DIAGNOSTIC_REVISION,
        object_version=None,
    )
    await seed_case(
        harness.database,
        case_id=f"case-body-hash-{target_type}",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        object_type=target_type,
        created_at=AFTER_ENTRY,
    )

    association = await harness.matcher.associated_sessions(
        body_hash_condition(cast(ObjectType, target_type)),
    )

    assert association.associated == 1
    assert association.sessions[0].session_id == session_id
    assert association.sessions[0].object_entry.event_index == 0


async def test_agent_diagnostic_revision_does_not_have_to_match(harness: Harness) -> None:
    """Agent target matching uses definition_hash, not the diagnostic revision."""
    session_id = "session-agent-diagnostic"
    main_id = await seed_session(harness.database, session_id=session_id)
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=0,
        kind="agent",
        name=TARGET_NAME,
        definition_hash=BODY_HASH,
        object_revision=DIAGNOSTIC_REVISION,
        object_version=TARGET_VERSION,
    )
    await seed_case(
        harness.database,
        case_id="case-agent-diagnostic",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        object_type="agent",
        created_at=AFTER_ENTRY,
    )

    association = await harness.matcher.associated_sessions(body_hash_condition("agent"))

    assert association.associated == 1


async def test_post_process_anchor_sorts_after_the_object_entry(harness: Harness) -> None:
    """A missing reported skill trigger becomes a comparable post-process case."""
    session_id = "session-post-process"
    main_id = await seed_session(harness.database, session_id=session_id)
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        definition_hash=BODY_HASH,
    )
    await seed_case(
        harness.database,
        case_id="case-post-process",
        session_id=session_id,
        case_type="discovery",
        object_name="other-skill",
        created_at=AFTER_ENTRY,
    )

    condition = body_hash_condition("skill")
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(
        condition,
        association,
        resolve_policy(None),
    )

    case = match.cases[0]
    assert case.anchor_source == "post_process"
    assert case.order_state == "comparable"
    assert case.hit_reason == "after_object"
    assert case.case_trigger is not None
    assert case.case_trigger.event_index == 2_147_483_647
    assert case.case_trigger.triggered_at == AFTER_ENTRY
    assert case.trigger_at == AFTER_ENTRY


async def test_self_agent_anchor_stays_on_the_reporter_node(harness: Harness) -> None:
    """self + agent keeps eventIndex=-1 on the reporter's own node."""
    session_id = "session-self-node"
    main_id = await seed_session(harness.database, session_id=session_id)
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        definition_hash=BODY_HASH,
    )
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=1,
        kind="agent",
        name="Review",
    )
    await seed_agent(
        harness.database,
        session_id=session_id,
        agent_id="agent-self-node",
        parent_agent_id=main_id,
        tool_use_id="tool-self-node",
    )
    await seed_case(
        harness.database,
        case_id="case-self-node",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        object_type="agent",
        agent_id="agent-self-node",
        created_at=AFTER_ENTRY,
    )

    condition = body_hash_condition("skill")
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(
        condition,
        association,
        resolve_policy(None),
    )

    case = match.cases[0]
    assert case.anchor_source == "node"
    assert case.case_trigger is not None
    assert case.case_trigger.event_index == -1
    assert case.case_trigger.agent_id == "agent-self-node"


async def test_unknown_reporter_stays_unknown(harness: Harness) -> None:
    """Only an unresolvable reporter keeps the -1/unknown anchor."""
    session_id = "session-unknown-reporter"
    main_id = await seed_session(harness.database, session_id=session_id)
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        definition_hash=BODY_HASH,
    )
    await seed_case(
        harness.database,
        case_id="case-unknown-reporter",
        session_id=session_id,
        case_type="discovery",
        object_name="other-skill",
        agent_id="missing-reporter",
        created_at=AFTER_ENTRY,
    )

    condition = body_hash_condition("skill")
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(
        condition,
        association,
        resolve_policy(None),
    )

    case = match.cases[0]
    assert case.anchor_source == "unknown"
    assert case.order_state == "unknown"
    assert case.case_trigger is None
    assert case.trigger_at == AFTER_ENTRY


async def test_prepare_persists_the_candidate_anchor_kind(harness: Harness) -> None:
    """A prepared run audits post_process on the candidate row and trigger index."""
    session_id = "session-candidate-anchor"
    main_id = await seed_session(harness.database, session_id=session_id)
    await _seed_event_with_identity(
        harness,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        definition_hash=BODY_HASH,
    )
    await seed_case(
        harness.database,
        case_id="case-candidate-post",
        session_id=session_id,
        case_type="discovery",
        object_name="other-skill",
        created_at=AFTER_ENTRY,
    )
    run_id = "run-m13-candidate-anchor"
    async with harness.database.transaction() as session:
        await session.execute(
            insert(evolution_runs).values(
                id=run_id,
                workspace_id="ws-m10-02-a",
                title=f"{TARGET_NAME} {TARGET_VERSION} 自进化",
                mode="cluster_only",
                engine_key="cluster_only",
                eval_config={},
                potential_policy={"preset": "default"},
                cache_enabled=False,
                attribution_engine="rule-v1",
                target_config_id=None,
                target_type="skill",
                target_name=TARGET_NAME,
                target_version=TARGET_VERSION,
                target_revision=f"digest:{BODY_HASH}",
                repo_url="https://example.invalid/repo.git",
                sub_dir="skills/deep-research",
                validation_project_id="validation",
                test_project_id="test",
                window_from=datetime(2026, 11, 1, tzinfo=SHANGHAI).date(),
                window_to=datetime(2026, 11, 30, tzinfo=SHANGHAI).date(),
                models=[],
                status="preparing",
                created_at=NOW,
                stats={},
            ),
        )

    await prepare_service(harness.database).handle(prepare_job(run_id))

    async with harness.database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_run_candidates).where(
                        evolution_run_candidates.c.run_id == run_id,
                    ),
                )
            )
            .mappings()
            .one()
        )
    assert row["case_anchor_kind"] == "post_process"
    assert row["case_trigger_event_index"] == 2_147_483_647
    assert row["included"] is True
