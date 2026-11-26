"""Agent name-match toggle in the shared potential matcher."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import pytest
from sqlalchemy import insert

from app.db.models.domain import agent_events
from app.service.evolution.potential import PotentialMatcher
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    NOW,
    TARGET_NAME,
    Harness,
    seed_case,
    seed_session,
)

BODY_HASH = "a" * 64
"""The target's configured body hash; the trace never carries it."""
TRACE_HASH = "b" * 64
"""The trace's different body hash, used to prove the revision filter is bypassed."""
OBSERVED_REVISIONS = frozenset({f"digest:{BODY_HASH}", BODY_HASH})
OBJECT_ENTRY = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)


def name_match_matcher(harness: Harness) -> PotentialMatcher:
    """Return a matcher with the opt-in agent name-match policy enabled."""
    return PotentialMatcher(harness.repository, agent_match_by_name=True)


async def seed_object_session(
    harness: Harness,
    *,
    session_id: str,
    object_type: Literal["skill", "agent", "knowledge"],
    case_id: str,
) -> str:
    """Seed one object entry with a trace hash that differs from the target body."""
    main_id = await seed_session(harness.database, session_id=session_id, started_at=NOW)
    async with harness.database.transaction() as session:
        await session.execute(
            insert(agent_events).values(
                agent_id=main_id,
                event_index=0,
                line_no=1,
                message_offset=0,
                kind=object_type,
                name=TARGET_NAME,
                object_version=None,
                object_revision=f"digest:{TRACE_HASH}",
                definition_hash=TRACE_HASH,
                triggered_at=OBJECT_ENTRY,
            ),
        )
    await seed_case(
        harness.database,
        case_id=case_id,
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        object_type=object_type,
        created_at=OBJECT_ENTRY,
    )
    return main_id


async def test_agent_name_match_ignores_observed_revisions(harness: Harness) -> None:
    """Flag on lets an agent Session associate despite a different body hash."""
    session_id = "session-name-agent"
    await seed_object_session(
        harness,
        session_id=session_id,
        object_type="agent",
        case_id="case-name-agent",
    )
    condition = harness.condition(target_type="agent")
    matcher = name_match_matcher(harness)

    default = await harness.matcher.associated_sessions(
        condition,
        observed_revisions=OBSERVED_REVISIONS,
    )
    by_name = await matcher.associated_sessions(
        condition,
        observed_revisions=OBSERVED_REVISIONS,
    )
    unfiltered = await matcher.associated_sessions(condition)

    assert default.associated == 0
    assert by_name.associated == 1
    assert by_name.sessions[0].session_id == session_id
    assert [item.session_id for item in unfiltered.sessions] == [session_id]


@pytest.mark.parametrize("object_type", ["skill", "knowledge"])
async def test_non_agent_objects_keep_the_observed_revision_filter(
    harness: Harness,
    object_type: Literal["skill", "knowledge"],
) -> None:
    """The flag is an agent-only exception; skill and knowledge still filter."""
    session_id = f"session-name-{object_type}"
    await seed_object_session(
        harness,
        session_id=session_id,
        object_type=object_type,
        case_id=f"case-name-{object_type}",
    )
    condition = harness.condition(target_type=object_type)

    by_name = await name_match_matcher(harness).associated_sessions(
        condition,
        observed_revisions=OBSERVED_REVISIONS,
    )

    assert by_name.associated == 0
