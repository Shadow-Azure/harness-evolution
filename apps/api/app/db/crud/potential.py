"""Batched read-only queries behind the shared potential matcher.

Every method takes a set of identifiers and resolves it in bounded chunks, so a
preview never issues one query per bad case. Nothing in this module writes.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select

from app.db.base import Database
from app.db.crud.evolution_targets import EvolutionObjectType
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
    session_families,
)
from app.utils.time import SHANGHAI, as_shanghai

ObjectType = EvolutionObjectType

_QUERY_CHUNK = 500


def _chunks(values: Sequence[str], size: int = _QUERY_CHUNK) -> Iterator[tuple[str, ...]]:
    """Yield stable identifier chunks so one IN predicate stays bounded."""
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


@dataclass(frozen=True, slots=True)
class WindowCaseRecord:
    """One workspace bad case inside the resolved local time window."""

    bad_case_id: str
    session_id: str
    bad_case_type: str
    object_name: str
    object_type: str
    bad_case_agent_id: str | None
    created_at: datetime
    trigger_line: int | None = None


@dataclass(frozen=True, slots=True)
class SessionMetaRecord:
    """The session facts association and birth anchors need."""

    id: str
    short_title: str
    title: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class ObjectEventRecord:
    """One object trigger event with its owning Agent tree coordinates."""

    session_id: str
    agent_id: str
    event_index: int
    tree_index: int
    object_version: str | None
    object_revision: str | None
    definition_hash: str | None
    document_revision: str | None
    triggered_at: datetime | None


@dataclass(frozen=True, slots=True)
class AgentNodeRecord:
    """One Agent tree node reduced to anchor-resolution facts."""

    id: str
    root_session_id: str
    parent_agent_id: str | None
    kind: str
    tool_use_id: str | None
    tree_index: int


@dataclass(frozen=True, slots=True)
class AnchorEventRecord:
    """One skill or agent event used as a bad-case trigger anchor."""

    agent_id: str
    event_index: int
    kind: str
    name: str | None
    tool_use_id: str | None
    triggered_at: datetime | None
    line_no: int | None = None


def _time(value: object) -> datetime | None:
    """Normalize an optional stored timestamp to Asia/Shanghai."""
    return as_shanghai(value) if isinstance(value, datetime) else None


class PotentialRepository:
    """Read the window, sessions, triggers, anchors, and cache facts in batches."""

    def __init__(self, database: Database) -> None:
        """Bind this read-only repository to the application database."""
        self._database = database

    async def list_window_cases(
        self,
        *,
        workspace_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[WindowCaseRecord, ...]:
        """Return self/discovery cases created inside ``[start, end)``.

        Legacy catalog-sync rows may carry an out-of-contract type; excluding
        them keeps the potential denominator identical to the overview definition.
        """
        statement = (
            select(
                bad_cases.c.bad_case_id,
                bad_cases.c.bad_case_session_id,
                bad_cases.c.bad_case_type,
                bad_cases.c.object_name,
                bad_cases.c.object_type,
                bad_cases.c.bad_case_agent_id,
                bad_cases.c.created_at,
                bad_cases.c.trigger_line,
            )
            .where(
                WorkspaceReadScope.for_workspace(workspace_id).case_condition(),
                bad_cases.c.created_at >= window_start,
                bad_cases.c.created_at < window_end,
                bad_cases.c.bad_case_type.in_(("self", "discovery")),
            )
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(
            WindowCaseRecord(
                bad_case_id=str(row["bad_case_id"]),
                session_id=str(row["bad_case_session_id"]),
                bad_case_type=str(row["bad_case_type"]),
                object_name=str(row["object_name"]),
                object_type=str(row["object_type"]),
                bad_case_agent_id=(
                    str(row["bad_case_agent_id"]) if row["bad_case_agent_id"] is not None else None
                ),
                created_at=as_shanghai(row["created_at"]),
                trigger_line=row["trigger_line"],
            )
            for row in rows
        )

    async def list_sessions(
        self,
        session_ids: Sequence[str],
    ) -> dict[str, SessionMetaRecord]:
        """Return normalized session metadata for the requested roots."""
        found: dict[str, SessionMetaRecord] = {}
        for chunk in _chunks(tuple(dict.fromkeys(session_ids))):
            statement = select(
                session_families.c.id,
                session_families.c.short_title,
                session_families.c.title,
                session_families.c.started_at,
            ).where(session_families.c.id.in_(chunk))
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            for row in rows:
                found[str(row["id"])] = SessionMetaRecord(
                    id=str(row["id"]),
                    short_title=str(row["short_title"]),
                    title=str(row["title"]),
                    started_at=as_shanghai(row["started_at"]),
                )
        return found

    async def list_object_events(
        self,
        session_ids: Sequence[str],
        *,
        object_type: ObjectType,
        object_name: str,
    ) -> tuple[ObjectEventRecord, ...]:
        """Return every trigger event of one object kind/name in the sessions.

        Read all agents under each root. Observed versions are attribution evidence.
        """
        if not session_ids:
            return ()
        events: list[ObjectEventRecord] = []
        name = (
            agent_events.c.name.collate("utf8mb4_0900_bin")
            if self._database.dialect == "mysql"
            else agent_events.c.name
        )
        for chunk in _chunks(tuple(dict.fromkeys(session_ids))):
            statement = (
                select(
                    agents.c.root_session_id,
                    agent_events.c.agent_id,
                    agent_events.c.event_index,
                    agents.c.tree_index,
                    agent_events.c.object_version,
                    agent_events.c.object_revision,
                    agent_events.c.definition_hash,
                    agent_events.c.document_revision,
                    agent_events.c.triggered_at,
                )
                .select_from(agent_events)
                .join(agents, agents.c.id == agent_events.c.agent_id)
                .where(
                    agents.c.root_session_id.in_(chunk),
                    agent_events.c.kind == object_type,
                    name == object_name,
                )
                .order_by(
                    agents.c.root_session_id,
                    agents.c.tree_index,
                    agent_events.c.event_index,
                )
            )
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            events.extend(
                ObjectEventRecord(
                    session_id=str(row["root_session_id"]),
                    agent_id=str(row["agent_id"]),
                    event_index=int(row["event_index"]),
                    tree_index=int(row["tree_index"]),
                    object_version=(
                        str(row["object_version"]) if row["object_version"] is not None else None
                    ),
                    object_revision=(
                        str(row["object_revision"]) if row["object_revision"] is not None else None
                    ),
                    definition_hash=(
                        str(row["definition_hash"]) if row["definition_hash"] is not None else None
                    ),
                    document_revision=(
                        str(row["document_revision"])
                        if row["document_revision"] is not None
                        else None
                    ),
                    triggered_at=_time(row["triggered_at"]),
                )
                for row in rows
            )
        # Some transcripts identify the agent or skill on a node without logging a call.
        # Prefer event coordinates whenever the Session has recorded the invocation.
        if object_type in ("agent", "skill"):
            traced = {event.session_id for event in events}
            missing = tuple(dict.fromkeys(root for root in session_ids if root not in traced))
            identity = (
                func.coalesce(func.nullif(agents.c.agent_type, ""), agents.c.name)
                if object_type == "agent"
                else agents.c.skill_name
            )
            for chunk in _chunks(missing):
                nodes = select(agents.c.root_session_id, agents.c.id, agents.c.tree_index).where(
                    agents.c.root_session_id.in_(chunk), identity == object_name
                )
                async with self._database.session() as session:
                    for row in (await session.execute(nodes)).mappings():
                        events.append(
                            ObjectEventRecord(
                                session_id=str(row["root_session_id"]),
                                agent_id=str(row["id"]),
                                tree_index=int(row["tree_index"]),
                                event_index=-1,
                                object_version=None,
                                object_revision=None,
                                definition_hash=None,
                                document_revision=None,
                                triggered_at=None,
                            )
                        )
        return tuple(events)

    async def list_agents(
        self,
        session_ids: Sequence[str],
    ) -> tuple[AgentNodeRecord, ...]:
        """Return every Agent node of the associated session trees."""
        if not session_ids:
            return ()
        nodes: list[AgentNodeRecord] = []
        for chunk in _chunks(tuple(dict.fromkeys(session_ids))):
            statement = (
                select(
                    agents.c.id,
                    agents.c.root_session_id,
                    agents.c.parent_agent_id,
                    agents.c.kind,
                    agents.c.tool_use_id,
                    agents.c.tree_index,
                )
                .where(agents.c.root_session_id.in_(chunk))
                .order_by(agents.c.root_session_id, agents.c.tree_index)
            )
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            nodes.extend(
                AgentNodeRecord(
                    id=str(row["id"]),
                    root_session_id=str(row["root_session_id"]),
                    parent_agent_id=(
                        str(row["parent_agent_id"]) if row["parent_agent_id"] is not None else None
                    ),
                    kind=str(row["kind"]),
                    tool_use_id=(
                        str(row["tool_use_id"]) if row["tool_use_id"] is not None else None
                    ),
                    tree_index=int(row["tree_index"]),
                )
                for row in rows
            )
        return tuple(nodes)

    async def list_anchor_events(
        self,
        agent_ids: Sequence[str],
        skill_names: Sequence[str],
        trigger_lines: Sequence[int] = (),
    ) -> tuple[AnchorEventRecord, ...]:
        """Return parent-call events and the named skill triggers for anchors."""
        if not agent_ids:
            return ()
        anchor_conditions = [agent_events.c.kind == "agent"]
        if trigger_lines:
            anchor_conditions.append(agent_events.c.line_no.in_(trigger_lines))
        if skill_names:
            anchor_conditions.append(
                and_(
                    agent_events.c.kind == "skill",
                    agent_events.c.name.in_(tuple(dict.fromkeys(skill_names))),
                ),
            )
        events: list[AnchorEventRecord] = []
        for chunk in _chunks(tuple(dict.fromkeys(agent_ids))):
            statement = (
                select(
                    agent_events.c.agent_id,
                    agent_events.c.event_index,
                    agent_events.c.kind,
                    agent_events.c.name,
                    agent_events.c.tool_use_id,
                    agent_events.c.line_no,
                    agent_events.c.triggered_at,
                )
                .where(
                    agent_events.c.agent_id.in_(chunk),
                    or_(*anchor_conditions),
                )
                .order_by(agent_events.c.agent_id, agent_events.c.event_index)
            )
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            events.extend(
                AnchorEventRecord(
                    line_no=row["line_no"],
                    agent_id=str(row["agent_id"]),
                    event_index=int(row["event_index"]),
                    kind=str(row["kind"]),
                    name=str(row["name"]) if row["name"] is not None else None,
                    tool_use_id=(
                        str(row["tool_use_id"]) if row["tool_use_id"] is not None else None
                    ),
                    triggered_at=_time(row["triggered_at"]),
                )
                for row in rows
            )
        return tuple(events)

    async def existing_cache_keys(
        self,
        cache_keys: Sequence[str],
    ) -> set[str]:
        """Return which of the computed cache keys already have a probe row."""
        existing: set[str] = set()
        for chunk in _chunks(tuple(dict.fromkeys(cache_keys))):
            statement = select(probe_reports.c.cache_key).where(
                probe_reports.c.cache_key.in_(chunk),
            )
            async with self._database.session() as session:
                rows: Sequence[object] = (await session.execute(statement)).scalars().all()
            existing.update(str(value) for value in rows if value is not None)
        return existing

    async def count_non_target_cases(
        self,
        *,
        workspace_id: str,
        probe_type: ObjectType,
        probe_object: str,
        object_versions: Sequence[str],
    ) -> int:
        """Count distinct cases this object/version historically judged non-target."""
        statement = (
            select(func.count(func.distinct(bad_case_analysis.c.bad_case_id)))
            .select_from(bad_case_analysis)
            .join(
                probe_reports,
                probe_reports.c.probe_id == bad_case_analysis.c.probe_id,
            )
            .where(
                probe_reports.c.workspace_id == workspace_id,
                probe_reports.c.probe_type == probe_type,
                probe_reports.c.probe_object == probe_object,
                probe_reports.c.object_version.in_(tuple(dict.fromkeys(object_versions))),
                probe_reports.c.conclusion == "non_target",
            )
        )
        async with self._database.session() as session:
            count = (await session.execute(statement)).scalar_one()
        return int(count)


def window_day_boundaries(start: date, end: date) -> tuple[datetime, datetime]:
    """Return the half-open Asia/Shanghai instants for an inclusive day window."""
    return (
        datetime.combine(start, datetime.min.time(), tzinfo=SHANGHAI),
        datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=SHANGHAI),
    )
