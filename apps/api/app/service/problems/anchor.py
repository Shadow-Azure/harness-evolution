"""Shared in-memory problem anchors for Session tree and problem APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.constants import POST_PROCESS_EVENT_INDEX
from app.db.crud.sessions import AgentRecord, EventRecord

AnchorKind = Literal["event", "node", "post_process", "unknown"]


@dataclass(frozen=True, slots=True)
class ResolvedAnchor:
    """Anchor plus a stable diagnostic for unresolved reporter/trigger links."""

    agent_id: str
    event_index: int
    kind: AnchorKind
    warning: str | None = None


def resolve_problem_anchor(
    *,
    bad_case_type: str | None,
    object_name: str,
    object_type: str | None,
    bad_case_agent_id: str | None,
    agents_by_id: dict[str, AgentRecord],
    events_by_agent: dict[str, list[EventRecord]],
    main: AgentRecord,
) -> ResolvedAnchor:
    """Resolve the 06 §7.4 anchor, separating post-process from unknown.

    A resolved reporter whose reported object has no trigger record now gets an
    explicit ``post_process`` anchor (INT_MAX) instead of ``-1``. ``-1`` and
    ``unknown`` are reserved for a reporter that cannot be resolved at all.
    """
    reported_agent_id = bad_case_agent_id
    reporter_found = reported_agent_id is None or reported_agent_id in agents_by_id
    reporter = agents_by_id.get(reported_agent_id or main.id, main)
    if not reporter_found:
        return ResolvedAnchor(
            agent_id=main.id,
            event_index=-1,
            kind="unknown",
            warning="BAD_CASE_AGENT_NOT_FOUND",
        )
    if object_type == "skill":
        events = events_by_agent.get(reporter.id, [])
        for event_index in range(len(events) - 1, -1, -1):
            event = events[event_index]
            if event.kind == "skill" and event.name == object_name:
                return ResolvedAnchor(
                    agent_id=reporter.id,
                    event_index=event_index,
                    kind="event",
                )
        return ResolvedAnchor(
            agent_id=reporter.id,
            event_index=POST_PROCESS_EVENT_INDEX,
            kind="post_process",
            warning="BAD_CASE_SKILL_ANCHOR_NOT_FOUND",
        )
    if bad_case_type != "discovery":
        return ResolvedAnchor(agent_id=reporter.id, event_index=-1, kind="node")
    if reporter.parent_agent_id is None:
        return ResolvedAnchor(
            agent_id=reporter.id,
            event_index=POST_PROCESS_EVENT_INDEX,
            kind="post_process",
            warning="BAD_CASE_AGENT_ANCHOR_NOT_FOUND",
        )
    parent = agents_by_id.get(reporter.parent_agent_id)
    if parent is not None and reporter.tool_use_id is not None:
        for event_index, event in enumerate(events_by_agent.get(parent.id, [])):
            if event.kind == "agent" and event.tool_use_id == reporter.tool_use_id:
                return ResolvedAnchor(
                    agent_id=parent.id,
                    event_index=event_index,
                    kind="event",
                )
    return ResolvedAnchor(
        agent_id=reporter.id,
        event_index=POST_PROCESS_EVENT_INDEX,
        kind="post_process",
        warning="BAD_CASE_AGENT_ANCHOR_NOT_FOUND",
    )
