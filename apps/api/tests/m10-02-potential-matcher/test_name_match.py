"""The per-member name switch only relaxes that member's revision filtering."""

from __future__ import annotations

from dataclasses import replace

from app.db.crud.potential import ObjectType
from app.service.evolution.potential import MatchTarget, PotentialMatcher
from tests.m10_02_potential_support import (
    NOW,
    Harness,
    seed_case,
    seed_event,
    seed_session,
)


def _member_target(
    *,
    object_type: ObjectType,
    object_name: str,
    match_by_name: bool,
) -> MatchTarget:
    """Build one member target with the same version identity as the fixture."""
    return MatchTarget(
        object_type=object_type,
        object_name=object_name,
        target_version="v2.0.0",
        target_revision="tag:v2.0.0",
        match_by_name=match_by_name,
    )


async def _seed_trace(
    harness: Harness,
    *,
    session_id: str,
    events: tuple[tuple[str, str, str], ...],
) -> None:
    """Insert one Session with ``(kind, name, revision)`` trigger events."""
    main = await seed_session(
        harness.database,
        session_id=session_id,
        started_at=NOW,
        title=session_id,
    )
    for index, (kind, name, revision) in enumerate(events):
        await seed_event(
            harness.database,
            agent_id=main,
            event_index=index,
            kind=kind,
            name=name,
            object_version="v1.0.0",
            object_revision=revision,
        )
    await seed_case(
        harness.database,
        case_id=f"case-{session_id}",
        session_id=session_id,
        object_name=events[0][1],
        object_type=events[0][0],
        created_at=NOW,
    )


async def test_agent_member_name_match_ignores_observed_revisions(
    harness: Harness,
) -> None:
    """An agent whose digest differs still associates when its switch is on."""
    await _seed_trace(
        harness,
        session_id="session-name-match-agent",
        events=(("agent", "Explore", "digest:name-match-agent"),),
    )
    base = harness.condition(target_type="agent", target_name="Explore")
    condition = replace(
        base,
        targets=(_member_target(object_type="agent", object_name="Explore", match_by_name=True),),
    )
    observed = frozenset({"digest:other-body"})

    associated = await PotentialMatcher(harness.repository).associated_sessions(
        condition,
        observed_revisions=observed,
    )
    unfiltered = await PotentialMatcher(harness.repository).associated_sessions(base)

    assert associated.associated == 1
    assert unfiltered.associated == 1


async def test_skill_member_name_match_ignores_observed_revisions(
    harness: Harness,
) -> None:
    """Skill members take the same per-member branch as agents."""
    await _seed_trace(
        harness,
        session_id="session-name-match-skill",
        events=(("skill", "deep-research", "digest:name-match-skill"),),
    )
    base = harness.condition(target_type="skill", target_name="deep-research")
    condition = replace(
        base,
        targets=(
            _member_target(
                object_type="skill",
                object_name="deep-research",
                match_by_name=True,
            ),
        ),
    )

    associated = await PotentialMatcher(harness.repository).associated_sessions(
        condition,
        observed_revisions=frozenset({"digest:other-skill-body"}),
    )

    assert associated.associated == 1


async def test_disabled_member_keeps_revision_filtering(harness: Harness) -> None:
    """An off member in the same condition still filters by body hash."""
    await _seed_trace(
        harness,
        session_id="session-name-match-off",
        events=(("agent", "Explore", "digest:name-match-off"),),
    )
    base = harness.condition(target_type="agent", target_name="Explore")
    condition = replace(
        base,
        targets=(_member_target(object_type="agent", object_name="Explore", match_by_name=False),),
    )

    filtered = await PotentialMatcher(harness.repository).associated_sessions(
        condition,
        observed_revisions=frozenset({"digest:other-body"}),
    )

    assert filtered.associated == 0


async def test_mixed_members_are_filtered_independently(harness: Harness) -> None:
    """One condition can turn name matching on for a skill and off for an agent."""
    await _seed_trace(
        harness,
        session_id="session-name-match-mixed",
        events=(
            ("skill", "deep-research", "digest:skill-body"),
            ("agent", "Explore", "digest:agent-body"),
        ),
    )
    base = harness.condition(target_type="skill", target_name="deep-research")
    condition = replace(
        base,
        targets=(
            _member_target(
                object_type="skill",
                object_name="deep-research",
                match_by_name=True,
            ),
            _member_target(object_type="agent", object_name="Explore", match_by_name=False),
        ),
    )

    association = await PotentialMatcher(harness.repository).associated_sessions(
        condition,
        observed_revisions=frozenset({"digest:skill-body"}),
    )

    # The skill row matches through the name switch even though the passed
    # revision belongs only to the skill's own body; the agent row's digest is
    # outside the filter, so only the skill event survives as an entry.
    assert association.associated == 1
    session = association.sessions[0]
    assert [entry.object_name for entry in session.object_entries] == ["deep-research"]


async def test_name_match_is_a_noop_without_revision_filtering(harness: Harness) -> None:
    """Wizard/launch calls that pass no revision filter behave exactly as before."""
    await _seed_trace(
        harness,
        session_id="session-name-match-noop",
        events=(("agent", "Explore", "digest:name-match-noop"),),
    )
    base = harness.condition(target_type="agent", target_name="Explore")
    condition = replace(
        base,
        targets=(_member_target(object_type="agent", object_name="Explore", match_by_name=True),),
    )

    with_switch = await PotentialMatcher(harness.repository).associated_sessions(condition)
    without_switch = await PotentialMatcher(harness.repository).associated_sessions(base)

    assert with_switch.associated == without_switch.associated == 1
    assert [item.session_id for item in with_switch.sessions] == [
        item.session_id for item in without_switch.sessions
    ]
