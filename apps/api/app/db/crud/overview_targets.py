"""Batched read-only queries behind the evolution-target overview endpoints.

The service evaluates potential through the shared M10 matcher; this module only
supplies the facts that projection needs: window cases (with their display
titles), observed object versions, and attribution links for the potential case
ids. Every query is pinned to one workspace, so a broad identifier set can never
mix rows from another space. Nothing in this module writes.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.db.base import Database
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
)
from app.utils.time import as_shanghai

_QUERY_CHUNK = 500


def _chunks(values: Sequence[str], size: int = _QUERY_CHUNK) -> Iterator[tuple[str, ...]]:
    """Yield stable identifier chunks so one IN predicate stays bounded."""
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


@dataclass(frozen=True, slots=True)
class WindowCaseFact:
    """One reported case inside the overview window and its display facts."""

    bad_case_id: str
    session_id: str
    bad_case_type: str
    source: str
    title: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ObjectVersionRecord:
    """One object trigger's persisted version and revision identities."""

    object_version: str | None
    object_revision: str | None


@dataclass(frozen=True, slots=True)
class AttributionLinkRecord:
    """One case-to-probe link reduced to what the target overview displays."""

    bad_case_id: str
    attribution_id: str
    object_version: str | None
    conclusion: str
    category: str | None
    created_at: datetime
    updated_at: datetime


class TargetOverviewRepository:
    """Read the case, version, and attribution facts for one workspace at a time."""

    def __init__(self, database: Database) -> None:
        """Bind this read-only repository to the application database."""
        self._database = database

    async def list_window_cases(
        self,
        *,
        workspace_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[WindowCaseFact, ...]:
        """Return self/discovery cases in ``[start, end)`` with their titles.

        The type predicate matches the shared overview and matcher definition:
        legacy catalog-sync rows outside self/discovery never enter any target
        aggregate, so potential and its three states stay on the same denominator.
        """
        statement = (
            select(
                bad_cases.c.bad_case_id,
                bad_cases.c.bad_case_session_id,
                bad_cases.c.bad_case_type,
                bad_cases.c.object_name,
                bad_cases.c.title,
                bad_cases.c.created_at,
            )
            .where(
                bad_cases.c.workspace_id == workspace_id,
                bad_cases.c.created_at >= window_start,
                bad_cases.c.created_at < window_end,
                bad_cases.c.bad_case_type.in_(("self", "discovery")),
            )
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(
            WindowCaseFact(
                bad_case_id=str(row["bad_case_id"]),
                session_id=str(row["bad_case_session_id"]),
                bad_case_type=str(row["bad_case_type"]),
                source=str(row["object_name"]),
                title=str(row["title"]),
                created_at=as_shanghai(row["created_at"]),
            )
            for row in rows
        )

    async def list_object_versions(
        self,
        session_ids: Sequence[str],
        *,
        object_type: str,
        object_name: str,
    ) -> tuple[ObjectVersionRecord, ...]:
        """Return the distinct object trigger identities of one kind/name.

        Version filtering is deliberately left to the shared matcher: this query
        returns the raw identity pair so the service can discover the versions a
        target actually appeared as, including knowledge digest revisions.
        """
        if not session_ids:
            return ()
        records: list[ObjectVersionRecord] = []
        for chunk in _chunks(tuple(dict.fromkeys(session_ids))):
            statement = (
                select(
                    agent_events.c.object_version,
                    agent_events.c.object_revision,
                )
                .select_from(agent_events)
                .join(agents, agents.c.id == agent_events.c.agent_id)
                .where(
                    agents.c.root_session_id.in_(chunk),
                    agent_events.c.kind == object_type,
                    agent_events.c.name == object_name,
                )
                .distinct()
            )
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            records.extend(
                ObjectVersionRecord(
                    object_version=(
                        str(row["object_version"]) if row["object_version"] is not None else None
                    ),
                    object_revision=(
                        str(row["object_revision"]) if row["object_revision"] is not None else None
                    ),
                )
                for row in rows
            )
        return tuple(records)

    async def list_attributions(
        self,
        *,
        workspace_id: str,
        object_type: str,
        object_name: str,
        case_ids: Sequence[str],
    ) -> tuple[AttributionLinkRecord, ...]:
        """Return newest-first links for one target identity and the given cases.

        Only the two product conclusions are readable here; rows with another
        stored value stay invisible so they cannot turn a potential case into an
        unexpected fourth state. Ordering is stable on ties through ``probe_id``.
        """
        if not case_ids:
            return ()
        records: list[AttributionLinkRecord] = []
        for chunk in _chunks(tuple(dict.fromkeys(case_ids))):
            statement = (
                select(
                    bad_case_analysis.c.bad_case_id,
                    probe_reports.c.probe_id,
                    probe_reports.c.object_version,
                    probe_reports.c.conclusion,
                    probe_reports.c.attribute_type,
                    probe_reports.c.created_at,
                    probe_reports.c.updated_at,
                )
                .select_from(
                    bad_case_analysis.join(
                        probe_reports,
                        probe_reports.c.probe_id == bad_case_analysis.c.probe_id,
                    ),
                )
                .where(
                    bad_case_analysis.c.bad_case_id.in_(chunk),
                    probe_reports.c.workspace_id == workspace_id,
                    probe_reports.c.probe_type == object_type,
                    probe_reports.c.probe_object == object_name,
                    probe_reports.c.conclusion.in_(("attributed", "non_target")),
                )
                .order_by(
                    probe_reports.c.updated_at.desc(),
                    probe_reports.c.probe_id.desc(),
                )
            )
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            records.extend(
                AttributionLinkRecord(
                    bad_case_id=str(row["bad_case_id"]),
                    attribution_id=str(row["probe_id"]),
                    object_version=(
                        str(row["object_version"]) if row["object_version"] is not None else None
                    ),
                    conclusion=str(row["conclusion"]),
                    category=(
                        str(row["attribute_type"]) if row["attribute_type"] is not None else None
                    ),
                    created_at=as_shanghai(row["created_at"]),
                    updated_at=as_shanghai(row["updated_at"]),
                )
                for row in rows
            )
        return tuple(records)
