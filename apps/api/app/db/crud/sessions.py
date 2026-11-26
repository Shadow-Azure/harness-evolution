"""Read-only persistence for session list, overview, and execution trees."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Database
from app.db.crud.read_scope import WorkspaceReadScope, bad_cases_table_present
from app.db.models.domain import (
    agent_events,
    agents,
    bad_cases,
    session_families,
)

SessionStatusFilter = Literal["all", "ok", "partial", "fail", "problem"]
SessionSort = Literal["latest", "userTurns", "messages", "agents"]


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One canonical session aggregate row."""

    id: str
    short_title: str
    title: str
    repo_name: str
    runtime_key: str
    model: str | None
    models: tuple[str, ...]
    started_at: datetime
    duration_seconds: int
    status: str
    execution_outcome: str
    skill_names: tuple[str, ...]
    user_turns_count: int
    messages_count: int
    tools_count: int
    errors_count: int
    agents_count: int
    tokens_total: int


@dataclass(frozen=True, slots=True)
class AgentRecord:
    """One canonical flat Agent node."""

    id: str
    root_session_id: str
    parent_agent_id: str | None
    kind: str
    agent_type: str | None
    task_kind: str | None
    team_name: str | None
    name: str | None
    skill_name: str | None
    description: str | None
    tool_use_id: str | None
    spawn_depth: int
    lines: int
    messages_count: int
    execution_outcome: str
    end_reason: str | None
    agent_definition_hash: str | None
    definition_source: str | None
    sort_key: float


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One canonical trigger event on an Agent node."""

    agent_id: str
    event_index: int
    line_no: int
    message_offset: int
    kind: str
    name: str | None
    description: str | None
    tool_use_id: str | None
    object_revision: str | None
    definition_hash: str | None
    file_read_hash: str | None
    read_complete: bool | None
    relation_confidence: str | None
    document_id: str | None
    document_revision: str | None
    source_path: str | None
    retrieval_kind: str | None
    retrieval_scope: str | None


@dataclass(frozen=True, slots=True)
class BadCaseRecord:
    """One read-only externally owned problem report.

    ``reason`` maps the renamed ``bad_case_description`` column; the public DTO
    keeps the shorter ``reason`` field name.
    """

    bad_case_id: str
    bad_case_session_id: str
    bad_case_type: str
    object_name: str
    object_type: str
    object_version: str | None
    bad_case_agent_id: str | None
    title: str
    reason: str


@dataclass(frozen=True, slots=True)
class SessionTreeSnapshot:
    """One consistent canonical and external read-model version for a tree."""

    session: SessionRecord
    agents: tuple[AgentRecord, ...]
    events: tuple[EventRecord, ...]
    bad_cases: tuple[BadCaseRecord, ...]


def _strings(value: object) -> tuple[str, ...]:
    """Normalize a JSON string array from SQLAlchemy mappings."""
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


def _session_record(row: Any) -> SessionRecord:
    """Convert one selected mapping into a stable session DTO."""
    return SessionRecord(
        id=str(row["id"]),
        short_title=str(row["short_title"]),
        title=str(row["title"]),
        repo_name=str(row["repo_name"]),
        runtime_key=str(row["runtime_key"]),
        model=str(row["model"]) if row["model"] is not None else None,
        models=_strings(row["models"]),
        started_at=row["started_at"],
        duration_seconds=int(row["duration_seconds"]),
        status=str(row["status"]),
        execution_outcome=str(row["execution_outcome"]),
        skill_names=_strings(row["skill_names"]),
        user_turns_count=int(row["user_turns_count"]),
        messages_count=int(row["messages_count"]),
        tools_count=int(row["tools_count"]),
        errors_count=int(row["errors_count"]),
        agents_count=int(row["agents_count"]),
        tokens_total=int(row["tokens_total"]),
    )


def _agent_record(row: Any) -> AgentRecord:
    """Convert one selected mapping into a flat Agent DTO."""
    return AgentRecord(
        id=str(row["id"]),
        root_session_id=str(row["root_session_id"]),
        parent_agent_id=(
            str(row["parent_agent_id"]) if row["parent_agent_id"] is not None else None
        ),
        kind=str(row["kind"]),
        agent_type=str(row["agent_type"]) if row["agent_type"] is not None else None,
        task_kind=str(row["task_kind"]) if row["task_kind"] is not None else None,
        team_name=str(row["team_name"]) if row["team_name"] is not None else None,
        name=str(row["name"]) if row["name"] is not None else None,
        skill_name=str(row["skill_name"]) if row["skill_name"] is not None else None,
        description=str(row["description"]) if row["description"] is not None else None,
        tool_use_id=str(row["tool_use_id"]) if row["tool_use_id"] is not None else None,
        spawn_depth=int(row["spawn_depth"]),
        lines=int(row["lines"]),
        messages_count=int(row["messages_count"]),
        execution_outcome=str(row["execution_outcome"]),
        end_reason=str(row["end_reason"]) if row["end_reason"] is not None else None,
        agent_definition_hash=(
            str(row["agent_definition_hash"]) if row["agent_definition_hash"] is not None else None
        ),
        definition_source=(
            str(row["definition_source"]) if row["definition_source"] is not None else None
        ),
        sort_key=float(row["sort_key"]),
    )


def _event_record(row: Any) -> EventRecord:
    """Convert one selected mapping into a trigger-event DTO."""
    return EventRecord(
        agent_id=str(row["agent_id"]),
        event_index=int(row["event_index"]),
        line_no=int(row["line_no"]),
        message_offset=int(row["message_offset"]),
        kind=str(row["kind"]),
        name=str(row["name"]) if row["name"] is not None else None,
        description=str(row["description"]) if row["description"] is not None else None,
        tool_use_id=str(row["tool_use_id"]) if row["tool_use_id"] is not None else None,
        object_revision=(
            str(row["object_revision"]) if row["object_revision"] is not None else None
        ),
        definition_hash=(
            str(row["definition_hash"]) if row["definition_hash"] is not None else None
        ),
        file_read_hash=(str(row["file_read_hash"]) if row["file_read_hash"] is not None else None),
        read_complete=(bool(row["read_complete"]) if row["read_complete"] is not None else None),
        relation_confidence=(
            str(row["relation_confidence"]) if row["relation_confidence"] is not None else None
        ),
        document_id=str(row["document_id"]) if row["document_id"] is not None else None,
        document_revision=(
            str(row["document_revision"]) if row["document_revision"] is not None else None
        ),
        source_path=str(row["source_path"]) if row["source_path"] is not None else None,
        retrieval_kind=(str(row["retrieval_kind"]) if row["retrieval_kind"] is not None else None),
        retrieval_scope=(
            str(row["retrieval_scope"]) if row["retrieval_scope"] is not None else None
        ),
    )


def _bad_case_record(row: Any) -> BadCaseRecord:
    """Convert one external bad-case row without adding write semantics."""
    return BadCaseRecord(
        bad_case_id=str(row["bad_case_id"]),
        bad_case_session_id=str(row["bad_case_session_id"]),
        bad_case_type=str(row["bad_case_type"]),
        object_name=str(row["object_name"]),
        object_type=str(row["object_type"]),
        object_version=(str(row["object_version"]) if row["object_version"] is not None else None),
        bad_case_agent_id=(
            str(row["bad_case_agent_id"]) if row["bad_case_agent_id"] is not None else None
        ),
        title=str(row["title"]) if row["title"] is not None else "",
        reason=(
            str(row["bad_case_description"]) if row["bad_case_description"] is not None else ""
        ),
    )


def _escape_like(value: str) -> str:
    """Treat user-provided LIKE metacharacters as literal text."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _session_conditions(
    *,
    query: str,
    status: SessionStatusFilter,
    exact_query: bool,
    scope: WorkspaceReadScope,
) -> list[ColumnElement[bool]]:
    """Build the one predicate set shared by listing and counting.

    ``query`` arrives already normalized by the session service; this function
    only interpolates it into the exact or fuzzy predicate.
    """
    conditions: list[ColumnElement[bool]] = [scope.session_condition()]
    if exact_query:
        if query:
            conditions.append(func.lower(session_families.c.id) == query.lower())
    elif query:
        pattern = f"%{_escape_like(query.lower())}%"
        conditions.append(
            or_(
                session_families.c.search_text.like(pattern, escape="\\"),
                func.lower(session_families.c.id).like(pattern, escape="\\"),
            ),
        )
    if status == "problem":
        conditions.append(session_families.c.status.in_(("partial", "fail")))
    elif status != "all":
        conditions.append(session_families.c.status == status)
    return conditions


class SessionRepository:
    """Run the SQL-backed read paths behind the session service."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to the application database."""
        self._database = database
        self._bad_cases_ready = False

    async def _scoped_reads_available(self) -> bool:
        """Return whether the external bad-case projection can be queried."""
        if not self._bad_cases_ready:
            self._bad_cases_ready = await bad_cases_table_present(self._database)
        return self._bad_cases_ready

    async def list_sessions(
        self,
        *,
        query: str,
        status: SessionStatusFilter,
        sort: SessionSort,
        limit: int,
        scope: WorkspaceReadScope,
        exact_query: bool = False,
    ) -> list[SessionRecord]:
        """List current session aggregates with stable server-side ordering."""
        if not await self._scoped_reads_available():
            return []
        conditions = _session_conditions(
            query=query,
            status=status,
            exact_query=exact_query,
            scope=scope,
        )
        sort_columns = {
            "latest": session_families.c.started_at,
            "userTurns": session_families.c.user_turns_count,
            "messages": session_families.c.messages_count,
            "agents": session_families.c.agents_count,
        }
        order = (
            sort_columns[sort].desc()
            if sort not in {"latest"}
            else session_families.c.started_at.desc()
        )
        statement = (
            select(session_families)
            .where(*conditions)
            .order_by(order, session_families.c.id)
            .limit(limit)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [_session_record(row) for row in rows]

    async def count_sessions(
        self,
        *,
        query: str,
        status: SessionStatusFilter,
        scope: WorkspaceReadScope,
        exact_query: bool = False,
    ) -> int:
        """Count every matching session without applying the page limit."""
        if not await self._scoped_reads_available():
            return 0
        statement = (
            select(func.count())
            .select_from(session_families)
            .where(
                *_session_conditions(
                    query=query,
                    status=status,
                    exact_query=exact_query,
                    scope=scope,
                )
            )
        )
        async with self._database.session() as session:
            return int((await session.execute(statement)).scalar_one())

    async def count_pending_sessions(self, scope: WorkspaceReadScope) -> int:
        """Count distinct scoped roots whose traces are not normalized yet."""
        if not await self._scoped_reads_available():
            return 0
        statement = (
            select(func.count(func.distinct(bad_cases.c.bad_case_session_id)))
            .select_from(bad_cases)
            .where(
                scope.case_condition(),
                ~select(session_families.c.id)
                .where(session_families.c.id == bad_cases.c.bad_case_session_id)
                .exists(),
            )
        )
        async with self._database.session() as session:
            return int((await session.execute(statement)).scalar_one())

    async def get(
        self,
        session_id: str,
        scope: WorkspaceReadScope,
    ) -> SessionRecord | None:
        """Return one canonical session aggregate by root id."""
        if not await self._scoped_reads_available():
            return None
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(session_families).where(
                            session_families.c.id == session_id,
                            scope.session_condition(),
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _session_record(row) if row is not None else None

    async def tree_snapshot(
        self,
        session_id: str,
        scope: WorkspaceReadScope,
    ) -> SessionTreeSnapshot | None:
        """Read one complete tree version from a single database snapshot."""
        if not await self._scoped_reads_available():
            return None
        async with self._database.session() as session:
            family_row = (
                (
                    await session.execute(
                        select(session_families).where(
                            session_families.c.id == session_id,
                            scope.session_condition(),
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if family_row is None:
                return None

            agent_rows = (
                (
                    await session.execute(
                        select(agents)
                        .where(agents.c.root_session_id == session_id)
                        .order_by(agents.c.sort_key, agents.c.id),
                    )
                )
                .mappings()
                .all()
            )
            agent_records = tuple(_agent_record(row) for row in agent_rows)
            agent_ids = [agent.id for agent in agent_records]

            if agent_ids:
                event_rows = (
                    (
                        await session.execute(
                            select(agent_events)
                            .where(agent_events.c.agent_id.in_(agent_ids))
                            .order_by(
                                agent_events.c.agent_id,
                                agent_events.c.event_index,
                            ),
                        )
                    )
                    .mappings()
                    .all()
                )
            else:
                event_rows = []

            bad_case_rows = (
                (
                    await session.execute(
                        select(bad_cases)
                        .where(
                            bad_cases.c.bad_case_session_id == session_id,
                            scope.case_condition(),
                        )
                        .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id),
                    )
                )
                .mappings()
                .all()
            )

            return SessionTreeSnapshot(
                session=_session_record(family_row),
                agents=agent_records,
                events=tuple(_event_record(row) for row in event_rows),
                bad_cases=tuple(_bad_case_record(row) for row in bad_case_rows),
            )

    async def bad_case_counts(
        self,
        session_ids: list[str],
        scope: WorkspaceReadScope,
    ) -> dict[str, int]:
        """Aggregate external bad-case counts once for the current page."""
        if not session_ids or not await self._scoped_reads_available():
            return {}
        statement = (
            select(
                bad_cases.c.bad_case_session_id,
                func.count().label("count"),
            )
            .where(
                bad_cases.c.bad_case_session_id.in_(session_ids),
                scope.case_condition(),
            )
            .group_by(bad_cases.c.bad_case_session_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).all()
        return {str(session_id): int(str(count)) for session_id, count in rows}

    async def list_agents(self, session_id: str) -> list[AgentRecord]:
        """Return the root's flat Agent set in canonical display order."""
        statement = (
            select(agents)
            .where(agents.c.root_session_id == session_id)
            .order_by(agents.c.sort_key, agents.c.id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [_agent_record(row) for row in rows]

    async def list_events(self, agent_ids: list[str]) -> list[EventRecord]:
        """Return all trigger events for the supplied Agent ids."""
        if not agent_ids:
            return []
        statement = (
            select(agent_events)
            .where(agent_events.c.agent_id.in_(agent_ids))
            .order_by(agent_events.c.agent_id, agent_events.c.event_index)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [_event_record(row) for row in rows]

    async def list_bad_cases(
        self,
        session_id: str,
        scope: WorkspaceReadScope,
    ) -> list[BadCaseRecord]:
        """Return externally owned problems in stable creation order."""
        if not await self._scoped_reads_available():
            return []
        statement = (
            select(bad_cases)
            .where(
                bad_cases.c.bad_case_session_id == session_id,
                scope.case_condition(),
            )
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [_bad_case_record(row) for row in rows]

    @staticmethod
    def event_lookup(
        events: list[EventRecord],
    ) -> dict[str, list[EventRecord]]:
        """Group events by Agent id while preserving query order."""
        grouped: dict[str, list[EventRecord]] = {}
        for event in events:
            grouped.setdefault(event.agent_id, []).append(event)
        return grouped
