"""The opt-in name switch only relaxes agent revision filtering."""

from __future__ import annotations

from app.service.evolution.potential import PotentialMatcher
from tests.m10_02_potential_support import (
    NOW,
    Harness,
    seed_case,
    seed_event,
    seed_session,
)


async def test_agent_name_match_ignores_observed_revisions(harness: Harness) -> None:
    """An agent whose digest differs still associates when the switch is on."""
    main = await seed_session(
        harness.database,
        session_id="session-name-match-agent",
        started_at=NOW,
        title="name match agent",
    )
    await seed_event(
        harness.database,
        agent_id=main,
        event_index=0,
        kind="agent",
        name="Explore",
        object_version="v1.0.0",
        object_revision="digest:name-match-agent",
    )
    await seed_case(
        harness.database,
        case_id="case-name-match-agent",
        session_id="session-name-match-agent",
        created_at=NOW,
    )
    condition = harness.condition(
        target_type="agent",
        target_name="Explore",
        target_version="v2.0.0",
    )
    observed = frozenset({"digest:other-body"})

    enabled = PotentialMatcher(harness.repository, agent_match_by_name=True)
    associated = await enabled.associated_sessions(condition, observed_revisions=observed)

    disabled = PotentialMatcher(harness.repository)
    filtered = await disabled.associated_sessions(condition, observed_revisions=observed)

    assert associated.associated == 1
    assert filtered.associated == 0


async def test_agent_name_match_is_a_noop_without_revision_filtering(
    harness: Harness,
) -> None:
    """Wizard/launch calls that pass no revision filter behave exactly as before."""
    main = await seed_session(
        harness.database,
        session_id="session-name-match-noop",
        started_at=NOW,
        title="name match noop",
    )
    await seed_event(
        harness.database,
        agent_id=main,
        event_index=0,
        kind="agent",
        name="Explore",
        object_version="v1.0.0",
        object_revision="digest:name-match-noop",
    )
    await seed_case(
        harness.database,
        case_id="case-name-match-noop",
        session_id="session-name-match-noop",
        created_at=NOW,
    )
    condition = harness.condition(target_type="agent", target_name="Explore")
    matcher = PotentialMatcher(harness.repository, agent_match_by_name=True)

    with_switch = await matcher.associated_sessions(condition)
    without_switch = await PotentialMatcher(harness.repository).associated_sessions(condition)

    assert with_switch.associated == without_switch.associated == 1
    assert [item.session_id for item in with_switch.sessions] == [
        item.session_id for item in without_switch.sessions
    ]


async def test_agent_name_match_keeps_skill_revision_filtering(harness: Harness) -> None:
    """Skill targets keep the body-hash filter even when the switch is on for agents."""
    main = await seed_session(
        harness.database,
        session_id="session-name-match-skill",
        started_at=NOW,
        title="name match skill",
    )
    await seed_event(
        harness.database,
        agent_id=main,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_version="v2.0.0",
        object_revision="digest:name-match-skill",
    )
    condition = harness.condition(
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
    )
    matcher = PotentialMatcher(harness.repository, agent_match_by_name=True)

    associated = await matcher.associated_sessions(
        condition,
        observed_revisions=frozenset({"digest:another-skill-body"}),
    )

    assert associated.associated == 0
