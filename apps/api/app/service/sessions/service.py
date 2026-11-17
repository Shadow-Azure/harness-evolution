"""Session read-model mapping, filtering, and deterministic tree anchoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, cast

from app.db.crud.read_scope import WorkspaceReadScope
from app.db.crud.sessions import (
    AgentRecord,
    BadCaseRecord,
    EventRecord,
    SessionRecord,
    SessionRepository,
    SessionSort,
    SessionStatusFilter,
)
from app.errors import AppError, ErrorCode
from app.service.bad_cases.title import derive_title
from app.service.problems.anchor import resolve_problem_anchor
from app.service.sessions.schemas import (
    DEFINITION_SOURCES,
    END_REASONS,
    EXECUTION_OUTCOMES,
    RELATION_CONFIDENCES,
    AgentKind,
    BadCaseAgent,
    BadCaseAnchor,
    DefinitionSource,
    EndReason,
    EventKind,
    ExecutionOutcome,
    RelationConfidence,
    SessionAgent,
    SessionBadCase,
    SessionEvent,
    SessionListItem,
    SessionListResponse,
    SessionStats,
    SessionStatus,
    SessionTree,
    TaskKind,
)
from app.utils.time import as_shanghai

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionFilters:
    """Validated list filters owned by the session service."""

    query: str = ""
    status: SessionStatusFilter = "all"
    sort: SessionSort = "latest"
    # Routes own the page size: V1 passes 100, V2 passes 10.
    limit: int = 100
    exact_query: bool = False


def _density(count: int, messages: int) -> float:
    """Compute the shared per-hundred-message density with one decimal."""
    if messages == 0:
        return 0.0
    return round(count / messages * 100, 1)


def _list_item(record: SessionRecord, bad_cases: int) -> SessionListItem:
    """Map one aggregate row to the sole list/overview contract."""
    return SessionListItem(
        id=record.id,
        short=record.short_title,
        title=record.title,
        repo=record.repo_name,
        runtime_key=record.runtime_key,
        model=record.model,
        started_at=as_shanghai(record.started_at),
        duration_seconds=record.duration_seconds,
        status=cast(SessionStatus, record.status),
        execution_outcome=cast(
            ExecutionOutcome,
            _closed(record.execution_outcome, EXECUTION_OUTCOMES, "execution outcome"),
        ),
        skills=list(record.skill_names),
        stats=SessionStats(
            user_turns=record.user_turns_count,
            messages=record.messages_count,
            tools=record.tools_count,
            errors=record.errors_count,
            agents=record.agents_count,
            bad_cases=bad_cases,
            tokens=record.tokens_total,
            fail_per_100_messages=_density(record.errors_count, record.messages_count),
            bad_cases_per_100_messages=_density(bad_cases, record.messages_count),
        ),
    )


def _label(agent: AgentRecord) -> str:
    """Select the stable display label without recomputing it in the browser."""
    if agent.kind == "main":
        return "主会话"
    for value in (agent.name, agent.skill_name, agent.agent_type, agent.kind):
        if value:
            return value
    return agent.kind


def _task_kind(value: str | None) -> TaskKind | None:
    """Narrow persisted task-kind values before exposing the closed contract."""
    if value is None or value in {"in_process_teammate", "forked_skill"}:
        return cast(TaskKind | None, value)
    raise AppError(
        status_code=500,
        code=ErrorCode.INTERNAL,
        message="session tree has an unsupported task kind",
    )


def _closed(value: str, allowed: frozenset[str], field: str) -> str:
    """Reject a persisted value outside the public closed state set."""
    if value not in allowed:
        raise AppError(
            status_code=500,
            code=ErrorCode.INTERNAL,
            message=f"session tree has an unsupported {field}",
        )
    return value


def _optional_closed(
    value: str | None,
    allowed: frozenset[str],
    field: str,
) -> str | None:
    """Apply the closed-set rule only when the evidence value is present."""
    return None if value is None else _closed(value, allowed, field)


def _agent(agent: AgentRecord, events: list[EventRecord]) -> SessionAgent:
    """Map one canonical Agent and its trigger events."""
    return SessionAgent(
        agent_id=agent.id,
        parent_agent_id=agent.parent_agent_id,
        kind=cast(AgentKind, agent.kind),
        agent_type=agent.agent_type,
        task_kind=_task_kind(agent.task_kind),
        team_name=agent.team_name,
        skill_name=agent.skill_name,
        label=_label(agent),
        desc=agent.description or "",
        tool_use_id=agent.tool_use_id,
        spawn_depth=agent.spawn_depth,
        lines=agent.lines,
        messages_count=agent.messages_count,
        execution_outcome=cast(
            ExecutionOutcome,
            _closed(agent.execution_outcome, EXECUTION_OUTCOMES, "execution outcome"),
        ),
        end_reason=cast(
            EndReason | None,
            _optional_closed(agent.end_reason, END_REASONS, "end reason"),
        ),
        agent_definition_hash=agent.agent_definition_hash,
        definition_source=cast(
            DefinitionSource | None,
            _optional_closed(
                agent.definition_source,
                DEFINITION_SOURCES,
                "definition source",
            ),
        ),
        events=[
            SessionEvent(
                line=event.line_no,
                kind=cast(EventKind, event.kind),
                name=event.name,
                desc=event.description or "",
                tool_use_id=event.tool_use_id,
                message_offset=event.message_offset,
                object_revision=event.object_revision,
                definition_hash=event.definition_hash,
                file_read_hash=event.file_read_hash,
                read_complete=event.read_complete,
                relation_confidence=cast(
                    RelationConfidence | None,
                    _optional_closed(
                        event.relation_confidence,
                        RELATION_CONFIDENCES,
                        "relation confidence",
                    ),
                ),
                document_id=event.document_id,
                document_revision=event.document_revision,
                source_path=event.source_path,
                retrieval_kind=event.retrieval_kind,
                retrieval_scope=event.retrieval_scope,
            )
            for event in events
        ],
    )


_SESSION_BAD_CASE_TYPES = frozenset({"self", "discovery"})
_SESSION_OBJECT_TYPES = frozenset({"skill", "agent"})


def _session_bad_case_fields(
    case: BadCaseRecord,
) -> tuple[Literal["self", "discovery"], Literal["skill", "agent"]]:
    """Validate the externally owned enum fields and degrade to safe defaults.

    The execution-tree read model is a Literal DTO; an invalid external value
    must stay visible rather than raise a validation error for the whole tree.
    """
    drifted: list[str] = []
    bad_case_type: Literal["self", "discovery"] = "self"
    if case.bad_case_type in _SESSION_BAD_CASE_TYPES:
        bad_case_type = cast(Literal["self", "discovery"], case.bad_case_type)
    else:
        drifted.append("bad_case_type")
    object_type: Literal["skill", "agent"] = "agent"
    if case.object_type in _SESSION_OBJECT_TYPES:
        object_type = cast(Literal["skill", "agent"], case.object_type)
    else:
        drifted.append("object_type")
    if drifted:
        logger.warning(
            "external session-tree problem fields drifted",
            extra={
                "event": "external.row_drift",
                "scope": "session_tree",
                "bad_case_id": case.bad_case_id,
                "codes": ["EXTERNAL_FIELD_INVALID"],
                "fields": drifted,
                "warning_count": len(drifted),
            },
        )
    return bad_case_type, object_type


def _bad_case(
    case: BadCaseRecord,
    *,
    agents_by_id: dict[str, AgentRecord],
    events_by_agent: dict[str, list[EventRecord]],
    main: AgentRecord,
) -> SessionBadCase:
    """Resolve one externally-owned problem to its prototype anchor semantics."""
    title, _ = derive_title(case.title, case.reason)
    bad_case_type, object_type = _session_bad_case_fields(case)
    anchor = resolve_problem_anchor(
        bad_case_type=bad_case_type,
        object_name=case.object_name,
        object_type=object_type,
        bad_case_agent_id=case.bad_case_agent_id,
        agents_by_id=agents_by_id,
        events_by_agent=events_by_agent,
        main=main,
    )
    if anchor.warning is not None:
        message = {
            "BAD_CASE_AGENT_NOT_FOUND": "bad case reporter Agent was not found",
            "BAD_CASE_SKILL_ANCHOR_NOT_FOUND": "bad case skill anchor was not found",
            "BAD_CASE_AGENT_ANCHOR_NOT_FOUND": "bad case Agent anchor was not found",
        }.get(anchor.warning, "bad case anchor was not found")
        logger.warning(
            message,
            extra={
                "badCaseId": case.bad_case_id,
                "agentId": case.bad_case_agent_id,
            },
        )

    return SessionBadCase(
        bad_case_id=case.bad_case_id,
        bad_case_type=bad_case_type,
        object_name=case.object_name,
        object_type=object_type,
        object_version=case.object_version,
        anchor=BadCaseAnchor(
            agent_id=anchor.agent_id,
            event_index=anchor.event_index,
        ),
        bad_case_agent=BadCaseAgent(
            session_id=case.bad_case_session_id,
            agent_id=case.bad_case_agent_id,
        ),
        title=title,
        reason=case.reason,
    )


class SessionService:
    """Assemble all public session read models from canonical storage."""

    def __init__(self, repository: SessionRepository) -> None:
        """Bind the service to its read-only persistence boundary."""
        self._repository = repository

    async def list(
        self,
        filters: SessionFilters,
        scope: WorkspaceReadScope,
    ) -> SessionListResponse:
        """Return one filtered and stably sorted session page."""
        # The service owns q normalization; the repository consumes this value.
        query = filters.query.strip() if filters.exact_query else filters.query
        records = await self._repository.list_sessions(
            query=query,
            status=filters.status,
            sort=filters.sort,
            limit=filters.limit,
            scope=scope,
            exact_query=filters.exact_query,
        )
        counts = await self._repository.bad_case_counts(
            [record.id for record in records],
            scope,
        )
        total = await self._repository.count_sessions(
            query=query,
            status=filters.status,
            scope=scope,
            exact_query=filters.exact_query,
        )
        pending_sessions = await self._repository.count_pending_sessions(scope)
        return SessionListResponse(
            items=[_list_item(record, counts.get(record.id, 0)) for record in records],
            total=total,
            pending_sessions=pending_sessions,
        )

    async def get(
        self,
        session_id: str,
        scope: WorkspaceReadScope,
    ) -> SessionListItem:
        """Return the same card shape used by the list response."""
        record = await self._repository.get(session_id, scope)
        if record is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.SESSION_NOT_FOUND,
                message="session not found",
            )
        counts = await self._repository.bad_case_counts([session_id], scope)
        return _list_item(record, counts.get(session_id, 0))

    async def tree(
        self,
        session_id: str,
        scope: WorkspaceReadScope,
    ) -> SessionTree:
        """Return a flat Agent tree with server-computed labels and anchors."""
        snapshot = await self._repository.tree_snapshot(session_id, scope)
        if snapshot is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.SESSION_NOT_FOUND,
                message="session not found",
            )
        agent_records = list(snapshot.agents)
        events_by_agent = self._repository.event_lookup(list(snapshot.events))
        agents_by_id = {agent.id: agent for agent in snapshot.agents}
        main = next(
            (agent for agent in agent_records if agent.kind == "main"),
            None,
        )
        if main is None:
            logger.warning(
                "canonical session tree has no main Agent", extra={"sessionId": session_id}
            )
            raise AppError(
                status_code=500,
                code=ErrorCode.INTERNAL,
                message="session tree is malformed",
            )
        return SessionTree(
            session_id=session_id,
            runtime_key=snapshot.session.runtime_key,
            agents=[
                _agent(agent, events_by_agent.get(agent.id, []))
                for agent in sorted(
                    agent_records,
                    key=lambda item: (
                        0 if item.kind == "main" else 1,
                        item.sort_key,
                        item.id,
                    ),
                )
            ],
            bad_cases=[
                _bad_case(
                    case,
                    agents_by_id=agents_by_id,
                    events_by_agent=events_by_agent,
                    main=main,
                )
                for case in snapshot.bad_cases
            ],
        )
