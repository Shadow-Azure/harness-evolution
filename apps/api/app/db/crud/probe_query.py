"""Read-only persistence for launch-wizard probe hit queries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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

_CASE_AGENT = agents.alias("case_agent")

_ATTRIBUTE_TYPES: tuple[str, ...] = ("model", "prompt", "error")


@dataclass(frozen=True, slots=True)
class ProbeHitRow:
    """One matched probe with its linked bad case and session facts."""

    bad_case_id: str
    analysis_status: str
    probe_id: str
    probe_session_id: str
    probe_type: str
    probe_object: str
    object_version: str | None
    attribute_type: str
    probe_description: str
    probe_analysis: str
    session_title: str | None
    case_agent_model: str | None
    session_model: str | None
    probe_started_at: datetime | None


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
    """Query probe reports as the root-cause source for wizard previews."""

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

    def _hit_selection(self) -> Any:
        """Return the shared probe/case/session selection without filters."""
        return (
            select(
                bad_cases.c.bad_case_id,
                bad_case_analysis.c.analysis_status,
                probe_reports.c.probe_id,
                probe_reports.c.session_id.label("probe_session_id"),
                probe_reports.c.probe_type,
                probe_reports.c.probe_object,
                probe_reports.c.object_version,
                probe_reports.c.attribute_type,
                probe_reports.c.probe_description,
                probe_reports.c.probe_analysis,
                session_families.c.title.label("session_title"),
                session_families.c.started_at.label("probe_started_at"),
                session_families.c.model.label("session_model"),
                _CASE_AGENT.c.model.label("case_agent_model"),
            )
            .select_from(probe_reports)
            .join(
                bad_case_analysis,
                bad_case_analysis.c.probe_id == probe_reports.c.probe_id,
            )
            .join(
                bad_cases,
                bad_cases.c.bad_case_id == bad_case_analysis.c.bad_case_id,
            )
            .outerjoin(
                session_families,
                session_families.c.id == probe_reports.c.session_id,
            )
            .outerjoin(
                _CASE_AGENT,
                _CASE_AGENT.c.id == bad_cases.c.bad_case_agent_id,
            )
        )

    async def list_rows_by_ids(
        self,
        probe_ids: Sequence[str],
    ) -> tuple[ProbeHitRow, ...]:
        """Return joined probe rows for explicit identifiers without hit filtering.

        Args:
            probe_ids: Probe identifiers selected by a run's cluster links.

        Returns:
            Hit rows in probe-id order carrying case, session, and model facts.
        """
        if not probe_ids:
            return ()
        statement = (
            self._hit_selection()
            .where(probe_reports.c.probe_id.in_(probe_ids))
            .order_by(probe_reports.c.probe_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_hit(cast(Mapping[str, Any], row)) for row in rows)

    async def list_hit_rows(self, query: ProbeHitQuery) -> tuple[ProbeHitRow, ...]:
        """Return every probe reported for one object pair with linked case facts.

        Args:
            query: Normalized wizard condition with a resolved target version.

        Returns:
            Hit rows starting from `probe_reports`, ordered by probe session
            start and probe id, already narrowed by the probe session-time
            window and selected model chips.
        """
        statement = (
            self._hit_selection()
            .where(
                probe_reports.c.probe_object == query.target_name,
                probe_reports.c.object_version == query.target_version,
                probe_reports.c.probe_type == query.target_type,
            )
            .order_by(session_families.c.started_at, probe_reports.c.probe_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        hits = [_row_hit(cast(Mapping[str, Any], row)) for row in rows]
        hits = [hit for hit in hits if _in_window(hit.probe_started_at, query)]
        if query.models:
            tree_models = await self.session_models(
                tuple(sorted({hit.probe_session_id for hit in hits})),
            )
            selected = frozenset(query.models)
            hits = [
                hit for hit in hits if tree_models.get(hit.probe_session_id, frozenset()) & selected
            ]
        return tuple(hits)


def _row_hit(row: Mapping[str, Any]) -> ProbeHitRow:
    """Convert one joined hit mapping into the boundary DTO."""
    return ProbeHitRow(
        bad_case_id=str(row["bad_case_id"]),
        analysis_status=str(row["analysis_status"]),
        probe_id=str(row["probe_id"]),
        probe_session_id=str(row["probe_session_id"]),
        probe_type=str(row["probe_type"]),
        probe_object=str(row["probe_object"]),
        object_version=_text(row["object_version"]),
        attribute_type=str(row["attribute_type"]),
        probe_description=str(row["probe_description"]),
        probe_analysis=str(row["probe_analysis"]),
        session_title=_text(row["session_title"]),
        case_agent_model=_text(row["case_agent_model"]),
        session_model=_text(row["session_model"]),
        probe_started_at=_time(row["probe_started_at"]),
    )


def _text(value: object) -> str | None:
    """Preserve a non-empty string without coercing database values."""
    return value if isinstance(value, str) and value else None


def _time(value: object) -> datetime | None:
    """Normalize an optional database timestamp to Asia/Shanghai."""
    return as_shanghai(cast(datetime, value)) if value is not None else None


def _in_window(moment: datetime | None, query: ProbeHitQuery) -> bool:
    """Return whether one probe session moment falls inside the selected window."""
    if moment is None:
        return query.window_from is None and query.window_to is None
    day = moment.date()
    if query.window_from is not None and day < query.window_from:
        return False
    return not (query.window_to is not None and day > query.window_to)
