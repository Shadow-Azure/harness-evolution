"""Read-only persistence for launch-wizard probe hit queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import select

from app.db.base import Database
from app.db.models.domain import (
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
    session_families,
)
from app.utils.time import as_shanghai

_CASE_SESSION = session_families.alias("case_session")
_CASE_AGENT = agents.alias("case_agent")


@dataclass(frozen=True, slots=True)
class ProbeHitRow:
    """One matched bad case with optional probe and session facts."""

    bad_case_id: str
    analysis_status: str | None
    probe_id: str | None
    probe_session_id: str | None
    probe_type: str | None
    probe_object: str | None
    object_version: str | None
    attribute_type: str | None
    probe_description: str | None
    session_title: str | None
    case_agent_model: str | None
    session_model: str | None
    session_started_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProbeHitQuery:
    """Normalized wizard condition used by read operations."""

    target_type: str
    target_name: str
    target_version: str
    window_from: date | None
    window_to: date | None
    models: tuple[str, ...]


class ProbeQueryRepository:
    """Query external issue-side tables for launch-wizard hit previews."""

    def __init__(self, database: Database) -> None:
        """Bind this read-only repository to the application database."""
        self._database = database

    async def session_models(
        self,
        session_ids: tuple[str, ...],
    ) -> dict[str, frozenset[str]]:
        """Return the set of agent models used inside each session tree.

        Args:
            session_ids: Root session identifiers to inspect.

        Returns:
            Mapping from root session id to the non-null agent models in its tree.
        """
        if not session_ids:
            return {}
        statement = select(
            agents.c.root_session_id,
            agents.c.model,
        ).where(
            agents.c.root_session_id.in_(session_ids),
            agents.c.model.is_not(None),
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).all()
        models: dict[str, set[str]] = {}
        for root_session_id, model in rows:
            models.setdefault(str(root_session_id), set()).add(str(model))
        return {session_id: frozenset(values) for session_id, values in models.items()}

    async def list_hit_rows(self, query: ProbeHitQuery) -> tuple[ProbeHitRow, ...]:
        """Return every bad case reported for one object pair with probe facts.

        Args:
            query: Normalized wizard condition with a resolved target version.

        Returns:
            Hit rows ordered by case creation time and id, already narrowed by
            the session-time window and selected model chips.
        """
        statement = (
            select(
                bad_cases.c.bad_case_id,
                bad_case_analysis.c.analysis_status,
                bad_case_analysis.c.probe_id,
                probe_reports.c.session_id.label("probe_session_id"),
                probe_reports.c.probe_type,
                probe_reports.c.probe_object,
                probe_reports.c.object_version,
                probe_reports.c.attribute_type,
                probe_reports.c.probe_description,
                session_families.c.title.label("session_title"),
                session_families.c.started_at.label("probe_started_at"),
                session_families.c.model.label("session_model"),
                _CASE_AGENT.c.model.label("case_agent_model"),
                _CASE_SESSION.c.started_at.label("case_started_at"),
            )
            .select_from(bad_cases)
            .outerjoin(
                bad_case_analysis,
                bad_case_analysis.c.bad_case_id == bad_cases.c.bad_case_id,
            )
            .outerjoin(
                probe_reports,
                probe_reports.c.probe_id == bad_case_analysis.c.probe_id,
            )
            .outerjoin(
                session_families,
                session_families.c.id == probe_reports.c.session_id,
            )
            .outerjoin(
                _CASE_SESSION,
                _CASE_SESSION.c.id == bad_cases.c.bad_case_session_id,
            )
            .outerjoin(
                _CASE_AGENT,
                _CASE_AGENT.c.id == bad_cases.c.bad_case_agent_id,
            )
            .where(
                bad_cases.c.object_type == query.target_type,
                bad_cases.c.object_name == query.target_name,
                bad_cases.c.object_version == query.target_version,
            )
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        hits = [_row_hit(cast(Mapping[str, Any], row)) for row in rows]
        hits = [hit for hit in hits if _in_window(hit.session_started_at, query)]
        if query.models:
            tree_models = await self.session_models(
                tuple(sorted({hit.probe_session_id or "" for hit in hits if hit.probe_session_id})),
            )
            selected = frozenset(query.models)
            hits = [
                hit
                for hit in hits
                if hit.probe_session_id is None
                or tree_models.get(hit.probe_session_id, frozenset()) & selected
            ]
        return tuple(hits)


def _row_hit(row: Mapping[str, Any]) -> ProbeHitRow:
    """Convert one joined hit mapping into the boundary DTO."""
    return ProbeHitRow(
        bad_case_id=str(row["bad_case_id"]),
        analysis_status=_text(row["analysis_status"]),
        probe_id=_text(row["probe_id"]),
        probe_session_id=_text(row["probe_session_id"]),
        probe_type=_text(row["probe_type"]),
        probe_object=_text(row["probe_object"]),
        object_version=_text(row["object_version"]),
        attribute_type=_text(row["attribute_type"]),
        probe_description=_text(row["probe_description"]),
        session_title=_text(row["session_title"]),
        case_agent_model=_text(row["case_agent_model"]),
        session_model=_text(row["session_model"]),
        session_started_at=_time(row["probe_started_at"] or row["case_started_at"]),
    )


def _text(value: object) -> str | None:
    """Preserve a non-empty string without coercing database values."""
    return value if isinstance(value, str) and value else None


def _time(value: object) -> datetime | None:
    """Normalize an optional database timestamp to Asia/Shanghai."""
    return as_shanghai(cast(datetime, value)) if value is not None else None


def _in_window(moment: datetime | None, query: ProbeHitQuery) -> bool:
    """Return whether one session moment falls inside the selected window."""
    if moment is None:
        return query.window_from is None and query.window_to is None
    day = moment.date()
    if query.window_from is not None and day < query.window_from:
        return False
    return not (query.window_to is not None and day > query.window_to)
