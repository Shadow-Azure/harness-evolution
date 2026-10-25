"""Read-only persistence for session list, overview, and execution trees."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Database
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
    model: str | None
    models: tuple[str, ...]
    started_at: datetime
    duration_seconds: int
    status: str
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


@dataclass(frozen=True, slots=True)
class BadCaseRecord:
    """One read-only externally owned problem report."""

    bad_case_id: str
    bad_case_session_id: str
    bad_case_type: str
    object_name: str
    object_type: str
    object_version: str | None
    bad_case_agent_id: str | None
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
        model=str(row["model"]) if row["model"] is not None else None,
        models=_strings(row["models"]),
        started_at=row["started_at"],
        duration_seconds=int(row["duration_seconds"]),
        status=str(row["status"]),
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
        reason=str(row["reason"]),
    )


def _escape_like(value: str) -> str:
    """Treat user-provided LIKE metacharacters as literal text."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SessionRepository:
    """Run the SQL-backed read paths behind the session service."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to the application database."""
        self._database = database

    async def list_sessions(
        self,
        *,
        query: str,
        status: SessionStatusFilter,
        sort: SessionSort,
        limit: int,
    ) -> list[SessionRecord]:
        """List current session aggregates with stable server-side ordering."""
        conditions: list[ColumnElement[bool]] = []
        if query:
            conditions.append(
                session_families.c.search_text.like(
                    f"%{_escape_like(query.lower())}%",
                    escape="\\",
                ),
            )
        if status == "problem":
            conditions.append(session_families.c.status.in_(("partial", "fail")))
        elif status != "all":
            conditions.append(session_families.c.status == status)
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

    async def get(self, session_id: str) -> SessionRecord | None:
        """Return one canonical session aggregate by root id."""
        async with self._database.session() as session:
            row = (
                (
                    await session.execute(
                        select(session_families).where(
                            session_families.c.id == session_id,
                        ),
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _session_record(row) if row is not None else None

    async def tree_snapshot(self, session_id: str) -> SessionTreeSnapshot | None:
        """Read one complete tree version from a single database snapshot."""
        async with self._database.session() as session:
            family_row = (
                (
                    await session.execute(
                        select(session_families).where(
                            session_families.c.id == session_id,
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
                        .where(bad_cases.c.bad_case_session_id == session_id)
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

    async def bad_case_counts(self, session_ids: list[str]) -> dict[str, int]:
        """Aggregate external bad-case counts once for the current page."""
        if not session_ids:
            return {}
        statement = (
            select(
                bad_cases.c.bad_case_session_id,
                func.count().label("count"),
            )
            .where(bad_cases.c.bad_case_session_id.in_(session_ids))
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

    async def list_bad_cases(self, session_id: str) -> list[BadCaseRecord]:
        """Return externally owned problems in stable creation order."""
        statement = (
            select(bad_cases)
            .where(bad_cases.c.bad_case_session_id == session_id)
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
