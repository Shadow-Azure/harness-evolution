"""Matcher behavior against a migrated corpus: policy, anchors, versions, isolation."""

from __future__ import annotations

from datetime import datetime

from app.db.models.domain import bad_case_analysis, probe_reports
from app.db.models.evolution import evolution_run_candidates
from app.service.evolution.potential import (
    HitReason,
    PotentialMatch,
    PotentialPolicy,
    ResolvedPolicy,
    resolve_policy,
)
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    LATER,
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    WORKSPACE_A,
    WORKSPACE_B,
    Harness,
    seed_agent,
    seed_case,
    seed_event,
    seed_probe,
    seed_session,
    seed_target,
    table_count,
)

EARLY = datetime(2026, 11, 17, 8, 30, tzinfo=SHANGHAI)
OBJECT_ENTRY = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)
CASE_AFTER = datetime(2026, 11, 17, 10, 30, tzinfo=SHANGHAI)


def default_policy() -> ResolvedPolicy:
    """Return the validated default policy used by the matcher tests."""
    return resolve_policy(None)


def reasons_of(match: PotentialMatch) -> dict[str, int]:
    """Return the matcher's closed reason counts as a plain mapping."""
    return {key: value for key, value in match.by_reason.items()}


def hits_of(match: PotentialMatch) -> dict[str, HitReason]:
    """Map every evaluated case id to its closed hit reason."""
    return {item.bad_case_id: item.hit_reason for item in match.cases}


async def seed_object_session(
    harness: Harness,
    *,
    session_id: str,
    started_at: datetime = NOW,
    object_type: str = "skill",
    object_name: str = TARGET_NAME,
    version: str | None = TARGET_VERSION,
    triggered_at: datetime = OBJECT_ENTRY,
) -> str:
    """Seed one associated session with a single object entry event."""
    main_id = await seed_session(
        harness.database,
        session_id=session_id,
        started_at=started_at,
        title=session_id,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=0,
        kind=object_type,
        name=object_name,
        object_version=version,
        triggered_at=triggered_at,
    )
    return main_id


async def test_default_policy_unions_self_report_and_after_object(harness: Harness) -> None:
    """The default policy takes the union of self reports and later cases."""
    session_id = "session-default-union"
    main_id = await seed_object_session(harness, session_id=session_id)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="other-skill",
        triggered_at=CASE_AFTER,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=2,
        kind="skill",
        name="early-skill",
        triggered_at=EARLY,
    )
    await seed_case(
        harness.database,
        case_id="case-self-early",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=EARLY,
    )
    await seed_case(
        harness.database,
        case_id="case-after-other",
        session_id=session_id,
        object_name="other-skill",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-before-other",
        session_id=session_id,
        object_name="early-skill",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-after-self-other",
        session_id=session_id,
        case_type="self",
        object_name="other-skill",
        created_at=LATER,
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert association.associated == 1
    assert len(match.cases) == 4
    assert match.potential == 3
    assert hits_of(match) == {
        "case-self-early": "self_report",
        "case-after-other": "after_object",
        "case-before-other": "policy_excluded",
        "case-after-self-other": "after_object",
    }
    assert reasons_of(match) == {
        "self_report": 1,
        "after_object": 2,
        "both": 0,
        "policy_excluded": 1,
        "order_unknown": 0,
    }


async def test_self_report_matches_name_not_case_object_version(harness: Harness) -> None:
    """The self branch only checks object name and bad_case_type."""
    session_id = "session-self-version"
    await seed_object_session(harness, session_id=session_id)
    await seed_case(
        harness.database,
        case_id="case-self-other-version",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        object_version="v1.0.0",
        created_at=EARLY,
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert match.potential == 1
    assert match.included[0].hit_reason == "self_report"


async def test_skill_anchor_uses_the_last_named_trigger(harness: Harness) -> None:
    """A skill case anchors on the reporter's last event for that skill name."""
    session_id = "session-skill-anchor"
    main_id = await seed_object_session(harness, session_id=session_id)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="case-skill",
        triggered_at=EARLY,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=2,
        kind="skill",
        name="case-skill",
        triggered_at=CASE_AFTER,
    )
    await seed_case(
        harness.database,
        case_id="case-skill-last",
        session_id=session_id,
        object_name="case-skill",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-skill-missing",
        session_id=session_id,
        object_name="never-triggered",
        created_at=LATER,
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert hits_of(match)["case-skill-last"] == "after_object"
    # No matching skill event degrades to the reporter birth point (session start).
    assert hits_of(match)["case-skill-missing"] == "policy_excluded"


async def test_agent_discovery_anchors_on_the_parent_call(harness: Harness) -> None:
    """Agent cases anchor where the parent called the reporting subagent."""
    session_id = "session-agent-anchor"
    main_id = await seed_session(harness.database, session_id=session_id, started_at=NOW)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=0,
        kind="agent",
        name="Explore",
        object_version=TARGET_VERSION,
        triggered_at=OBJECT_ENTRY,
    )
    await seed_agent(
        harness.database,
        session_id=session_id,
        agent_id="agent-early",
        parent_agent_id=main_id,
        tool_use_id="tool-early",
    )
    await seed_agent(
        harness.database,
        session_id=session_id,
        agent_id="agent-late",
        parent_agent_id=main_id,
        tool_use_id="tool-late",
        tree_index=2,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="agent",
        name="early-child",
        tool_use_id="tool-early",
        triggered_at=EARLY,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=2,
        kind="agent",
        name="late-child",
        tool_use_id="tool-late",
        triggered_at=CASE_AFTER,
    )
    await seed_target(
        harness.database,
        target_id="target-agent-m10-02",
        object_type="agent",
        object_name="Explore",
    )
    await seed_case(
        harness.database,
        case_id="case-discovery-early",
        session_id=session_id,
        case_type="discovery",
        object_name="Explore",
        object_type="agent",
        agent_id="agent-early",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-discovery-late",
        session_id=session_id,
        case_type="discovery",
        object_name="Explore",
        object_type="agent",
        agent_id="agent-late",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-self-child",
        session_id=session_id,
        case_type="self",
        object_name="OtherAgent",
        object_type="agent",
        agent_id="agent-early",
        created_at=LATER,
    )

    condition = harness.condition(target_type="agent", target_name="Explore")
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert hits_of(match)["case-discovery-late"] == "after_object"
    assert hits_of(match)["case-discovery-early"] == "policy_excluded"
    assert hits_of(match)["case-self-child"] == "policy_excluded"


async def test_custom_same_object_only_filters_the_union(harness: Harness) -> None:
    """sameObjectOnly removes other-object cases after the union is computed."""
    session_id = "session-same-object"
    main_id = await seed_object_session(harness, session_id=session_id)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name=TARGET_NAME,
        triggered_at=CASE_AFTER,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=2,
        kind="skill",
        name="other-skill",
        triggered_at=CASE_AFTER,
    )
    await seed_case(
        harness.database,
        case_id="case-same-self",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=EARLY,
    )
    await seed_case(
        harness.database,
        case_id="case-same-after",
        session_id=session_id,
        object_name=TARGET_NAME,
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-other-after",
        session_id=session_id,
        object_name="other-skill",
        created_at=LATER,
    )
    policy = resolve_policy(
        PotentialPolicy(
            preset="custom",
            include_self_report=True,
            include_after_object=True,
            same_object_only=True,
        ),
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, policy)

    assert hits_of(match) == {
        "case-same-self": "both",
        "case-same-after": "after_object",
        "case-other-after": "policy_excluded",
    }
    assert match.potential == 2


async def test_missing_reporter_leaves_order_unknown(harness: Harness) -> None:
    """An unresolvable reporter never claims the case happened after the object."""
    session_id = "session-order-unknown"
    await seed_object_session(harness, session_id=session_id)
    await seed_case(
        harness.database,
        case_id="case-unknown-self",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        agent_id="agent-that-does-not-exist",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-unknown-discovery",
        session_id=session_id,
        object_name="other-skill",
        agent_id="agent-that-does-not-exist",
        created_at=LATER,
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert hits_of(match)["case-unknown-self"] == "self_report"
    assert hits_of(match)["case-unknown-discovery"] == "order_unknown"
    assert {item.order_state for item in match.cases} == {"unknown"}


async def test_session_partition_pending_unresolved_skipped(harness: Harness) -> None:
    """reported splits into associated, versionUnresolved, skipped, and pending."""
    associated = "session-associated"
    unresolved = "session-unresolved"
    skipped = "session-skipped"
    pending = "session-pending"
    await seed_object_session(harness, session_id=associated)
    await seed_object_session(harness, session_id=unresolved, version=None)
    skipped_main = await seed_session(harness.database, session_id=skipped, started_at=NOW)
    await seed_event(
        harness.database,
        agent_id=skipped_main,
        event_index=0,
        kind="skill",
        name=TARGET_NAME,
        object_version="v1.0.0",
        triggered_at=OBJECT_ENTRY,
    )
    for session_id in (associated, unresolved, skipped, pending):
        await seed_case(
            harness.database,
            case_id=f"case-{session_id}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)

    assert association.reported == 4
    assert association.associated == 1
    assert association.version_unresolved == 1
    assert association.skipped == 1
    assert association.pending == 1
    assert [session.session_id for session in association.sessions] == [associated]
    assert association.sessions[0].bad_case_count == 1
    match = await harness.matcher.potential_cases(condition, association, default_policy())
    assert [item.bad_case_id for item in match.cases] == [f"case-{associated}"]


async def test_knowledge_target_uses_the_same_entry_point_and_order(harness: Harness) -> None:
    """knowledge maps to kind=knowledge and shares entry/anchor comparison."""
    await seed_target(
        harness.database,
        target_id="target-knowledge-m10-02",
        object_type="knowledge",
        object_name="Runbook",
        default_ref="rev-1",
    )
    session_id = "session-knowledge"
    main_id = await seed_session(harness.database, session_id=session_id, started_at=NOW)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=0,
        kind="knowledge",
        name="Runbook",
        object_version="rev-1",
        triggered_at=OBJECT_ENTRY,
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="other-skill",
        triggered_at=CASE_AFTER,
    )
    await seed_case(
        harness.database,
        case_id="case-knowledge-after",
        session_id=session_id,
        object_name="other-skill",
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-knowledge-self",
        session_id=session_id,
        case_type="self",
        object_name="Runbook",
        created_at=EARLY,
    )

    condition = harness.condition(
        target_type="knowledge",
        target_name="Runbook",
        target_version="rev-1",
    )
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert association.associated == 1
    assert hits_of(match)["case-knowledge-after"] == "after_object"
    assert hits_of(match)["case-knowledge-self"] == "self_report"


async def test_window_filters_by_shanghai_day(harness: Harness) -> None:
    """The case window uses Asia/Shanghai midnight boundaries."""
    session_id = "session-window"
    await seed_object_session(
        harness,
        session_id=session_id,
        started_at=datetime(2026, 11, 16, 9, 0, tzinfo=SHANGHAI),
        triggered_at=datetime(2026, 11, 16, 10, 0, tzinfo=SHANGHAI),
    )
    await seed_case(
        harness.database,
        case_id="case-before-midnight",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=datetime(2026, 11, 16, 23, 59, 59, tzinfo=SHANGHAI),
    )
    await seed_case(
        harness.database,
        case_id="case-after-midnight",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=datetime(2026, 11, 17, 0, 0, 1, tzinfo=SHANGHAI),
    )

    condition = harness.condition(
        window_from=datetime(2026, 11, 17).date(),
        window_to=datetime(2026, 11, 17).date(),
    )
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert [item.bad_case_id for item in match.cases] == ["case-after-midnight"]


async def test_workspace_scope_excludes_other_workspace_cases(harness: Harness) -> None:
    """A preview only counts bad cases owned by the route workspace."""
    session_id = "session-workspace"
    await seed_object_session(harness, session_id=session_id)
    await seed_case(
        harness.database,
        case_id="case-workspace-a",
        session_id=session_id,
        workspace_id=WORKSPACE_A,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=LATER,
    )
    await seed_case(
        harness.database,
        case_id="case-workspace-b",
        session_id=session_id,
        workspace_id=WORKSPACE_B,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=LATER,
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert [item.bad_case_id for item in match.cases] == ["case-workspace-a"]


async def test_object_entry_is_the_earliest_matching_version(harness: Harness) -> None:
    """A later duplicate target event never becomes the entry point."""
    session_id = "session-earliest-entry"
    main_id = await seed_object_session(harness, session_id=session_id)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=datetime(2026, 11, 17, 11, 0, tzinfo=SHANGHAI),
    )
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=2,
        kind="skill",
        name="other-skill",
        triggered_at=CASE_AFTER,
    )
    await seed_case(
        harness.database,
        case_id="case-between-entries",
        session_id=session_id,
        object_name="other-skill",
        created_at=LATER,
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())

    assert match.included[0].hit_reason == "after_object"
    assert match.included[0].object_trigger.triggered_at == OBJECT_ENTRY


async def test_attribution_preview_counts_existing_keys_and_non_target(harness: Harness) -> None:
    """Cache preview reuses keys without writing and counts non-target history."""
    session_id = "session-attribution"
    main_id = await seed_object_session(harness, session_id=session_id)
    await seed_event(
        harness.database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="early-skill",
        triggered_at=EARLY,
    )
    for index in range(3):
        await seed_case(
            harness.database,
            case_id=f"case-potential-{index}",
            session_id=session_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=LATER,
        )
    await seed_case(
        harness.database,
        case_id="case-excluded",
        session_id=session_id,
        object_name="early-skill",
        created_at=LATER,
    )
    await seed_probe(
        harness.database,
        case_id="case-potential-0",
        session_id=session_id,
        conclusion="attributed",
    )
    await seed_probe(
        harness.database,
        case_id="case-potential-1",
        session_id=session_id,
        conclusion="attributed",
    )
    await seed_probe(
        harness.database,
        case_id="case-excluded",
        session_id=session_id,
        conclusion="non_target",
    )

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, default_policy())
    counts = await harness.matcher.attribution_preview(condition, match, cache_enabled=True)
    disabled = await harness.matcher.attribution_preview(condition, match, cache_enabled=False)

    assert match.potential == 3
    assert counts.potential == 3
    assert counts.reused == 2
    assert counts.fresh == 1
    assert counts.non_target_known == 1
    assert disabled.reused == 0
    assert disabled.fresh == 3
    assert disabled.non_target_known == 1


async def test_preview_paths_do_not_write_probe_or_candidate_rows(harness: Harness) -> None:
    """Association, potential, and attribution preview are strictly read-only."""
    session_id = "session-read-only"
    await seed_object_session(harness, session_id=session_id)
    await seed_case(
        harness.database,
        case_id="case-read-only",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=LATER,
    )
    before = {
        "probes": await table_count(harness.database, probe_reports),
        "links": await table_count(harness.database, bad_case_analysis),
        "candidates": await table_count(harness.database, evolution_run_candidates),
    }

    condition = harness.condition()
    association = await harness.matcher.associated_sessions(condition)
    match = await harness.matcher.potential_cases(condition, association, resolve_policy(None))
    await harness.matcher.attribution_preview(condition, match, cache_enabled=True)

    after = {
        "probes": await table_count(harness.database, probe_reports),
        "links": await table_count(harness.database, bad_case_analysis),
        "candidates": await table_count(harness.database, evolution_run_candidates),
    }
    assert before == after
    assert after["candidates"] == 0
    assert match.potential == 1
