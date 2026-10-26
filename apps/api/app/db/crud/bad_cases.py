"""Read-only persistence for externally owned issue and attribution tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import Select, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.utils.time import as_shanghai


@dataclass(frozen=True, slots=True)
class BadCaseRow:
    """One externally owned issue row at the database boundary."""

    bad_case_id: str
    bad_case_session_id: str
    bad_case_type: str
    object_name: str
    object_type: str
    object_version: str | None
    bad_case_agent_id: str | None
    reason: str
    meta_data: object | None
    source: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BadCaseAnalysisRow:
    """One externally owned attribution-state row."""

    bad_case_id: str
    analysis_status: str
    probe_id: str | None
    analysis_result: object | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProbeReportRow:
    """One externally owned root-cause report row."""

    probe_id: str
    session_id: str
    probe_type: str
    probe_object: str
    object_version: str | None
    attribute_type: str
    probe_description: str
    probe_analysis: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProbeSourceCandidate:
    """One reverse probe link with nullable joined identities for validation."""

    case_id: str
    analysis_status: str
    case_session_id: str | None
    probe_session_id: str | None


@dataclass(frozen=True, slots=True)
class BadCaseSnapshot:
    """External rows used to construct issue view models from one snapshot."""

    cases: tuple[BadCaseRow, ...]
    analyses: tuple[BadCaseAnalysisRow, ...]
    probes: tuple[ProbeReportRow, ...]


@dataclass(frozen=True, slots=True)
class ProbeSnapshot:
    """One probe and its reverse links from one database snapshot."""

    probe: ProbeReportRow | None
    sources: tuple[ProbeSourceCandidate, ...]


class BadCaseRepositoryProtocol(Protocol):
    """Read-only operations required by the bad-case service."""

    async def list_by_session(self, session_id: str) -> tuple[BadCaseRow, ...]:
        """Return cases for one root session in stable order."""

    async def list_snapshot(self, session_id: str) -> BadCaseSnapshot:
        """Return session cases, analyses, and probes from one snapshot."""

    async def get_case(self, case_id: str) -> BadCaseRow | None:
        """Return one case by stable id."""

    async def get_case_snapshot(self, case_id: str) -> BadCaseSnapshot:
        """Return one case and related rows from one snapshot."""

    async def analyses_by_case_ids(
        self,
        case_ids: tuple[str, ...],
    ) -> tuple[BadCaseAnalysisRow, ...]:
        """Return attribution rows for a batch of cases."""

    async def get_analysis(self, case_id: str) -> BadCaseAnalysisRow | None:
        """Return one attribution row by case id."""

    async def probes_by_ids(
        self,
        probe_ids: tuple[str, ...],
    ) -> tuple[ProbeReportRow, ...]:
        """Return root-cause reports for a batch of ids."""

    async def get_probe(self, probe_id: str) -> ProbeReportRow | None:
        """Return one root-cause report by id."""

    async def probe_source_candidates(
        self,
        probe_id: str,
    ) -> tuple[ProbeSourceCandidate, ...]:
        """Return reverse-linked source candidates with joined identities."""

    async def get_probe_snapshot(self, probe_id: str) -> ProbeSnapshot:
        """Return one probe and reverse links from one snapshot."""


def _text(value: object) -> str | None:
    """Preserve a non-empty string without coercing arbitrary database values."""
    return value if isinstance(value, str) and value else None


def _row_bad_case(mapping: RowMapping) -> BadCaseRow:
    """Convert one selected bad-case mapping into a boundary DTO."""
    return BadCaseRow(
        bad_case_id=mapping["bad_case_id"],
        bad_case_session_id=mapping["bad_case_session_id"],
        bad_case_type=mapping["bad_case_type"],
        object_name=mapping["object_name"],
        object_type=mapping["object_type"],
        object_version=_text(mapping["object_version"]),
        bad_case_agent_id=_text(mapping["bad_case_agent_id"]),
        reason=mapping["reason"],
        meta_data=mapping["meta_data"],
        source=_text(mapping["source"]),
        created_at=as_shanghai(mapping["created_at"]),
        updated_at=as_shanghai(mapping["updated_at"]),
    )


def _row_analysis(mapping: RowMapping) -> BadCaseAnalysisRow:
    """Convert one selected attribution mapping into a boundary DTO."""
    return BadCaseAnalysisRow(
        bad_case_id=mapping["bad_case_id"],
        analysis_status=mapping["analysis_status"],
        probe_id=_text(mapping["probe_id"]),
        analysis_result=mapping["analysis_result"],
        updated_at=as_shanghai(mapping["updated_at"]),
    )


def _row_probe(mapping: RowMapping) -> ProbeReportRow:
    """Convert one selected root-cause mapping into a boundary DTO."""
    return ProbeReportRow(
        probe_id=mapping["probe_id"],
        session_id=mapping["session_id"],
        probe_type=mapping["probe_type"],
        probe_object=mapping["probe_object"],
        object_version=_text(mapping["object_version"]),
        attribute_type=mapping["attribute_type"],
        probe_description=mapping["probe_description"],
        probe_analysis=mapping["probe_analysis"],
        created_at=as_shanghai(mapping["created_at"]),
        updated_at=as_shanghai(mapping["updated_at"]),
    )


class BadCaseRepository:
    """Query external issue-side tables without exposing any write operation."""

    def __init__(self, database: Database) -> None:
        """Bind this read-only repository to one application database."""
        self._database = database

    async def list_by_session(self, session_id: str) -> tuple[BadCaseRow, ...]:
        """Return a session's cases in deterministic creation order."""
        statement = (
            select(bad_cases)
            .where(bad_cases.c.bad_case_session_id == session_id)
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_bad_case(row) for row in rows)

    async def list_snapshot(self, session_id: str) -> BadCaseSnapshot:
        """Read a session's cases and related rows in one database session."""
        case_statement = (
            select(bad_cases)
            .where(bad_cases.c.bad_case_session_id == session_id)
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            cases = tuple(
                _row_bad_case(row)
                for row in (await session.execute(case_statement)).mappings().all()
            )
            analyses, probes = await self._related_rows(
                session,
                tuple(case.bad_case_id for case in cases),
            )
        return BadCaseSnapshot(cases=cases, analyses=analyses, probes=probes)

    async def get_case(self, case_id: str) -> BadCaseRow | None:
        """Return one external issue by its stable id."""
        statement = select(bad_cases).where(bad_cases.c.bad_case_id == case_id)
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _row_bad_case(row) if row is not None else None

    async def get_case_snapshot(self, case_id: str) -> BadCaseSnapshot:
        """Read one case and related rows in one database session."""
        statement = select(bad_cases).where(bad_cases.c.bad_case_id == case_id)
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
            if row is None:
                return BadCaseSnapshot(cases=(), analyses=(), probes=())
            cases = (_row_bad_case(row),)
            analyses, probes = await self._related_rows(session, (case_id,))
        return BadCaseSnapshot(cases=cases, analyses=analyses, probes=probes)

    async def analyses_by_case_ids(
        self,
        case_ids: tuple[str, ...],
    ) -> tuple[BadCaseAnalysisRow, ...]:
        """Return attribution states for a case batch in one SELECT."""
        if not case_ids:
            return ()
        statement = (
            select(bad_case_analysis)
            .where(bad_case_analysis.c.bad_case_id.in_(case_ids))
            .order_by(bad_case_analysis.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_analysis(row) for row in rows)

    async def get_analysis(self, case_id: str) -> BadCaseAnalysisRow | None:
        """Return one case's attribution state."""
        statement = select(bad_case_analysis).where(
            bad_case_analysis.c.bad_case_id == case_id,
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _row_analysis(row) if row is not None else None

    async def probes_by_ids(
        self,
        probe_ids: tuple[str, ...],
    ) -> tuple[ProbeReportRow, ...]:
        """Return root-cause reports for a probe batch in one SELECT."""
        if not probe_ids:
            return ()
        statement = (
            select(probe_reports)
            .where(probe_reports.c.probe_id.in_(probe_ids))
            .order_by(probe_reports.c.probe_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_probe(row) for row in rows)

    async def get_probe(self, probe_id: str) -> ProbeReportRow | None:
        """Return one root-cause report by stable id."""
        statement = select(probe_reports).where(probe_reports.c.probe_id == probe_id)
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _row_probe(row) if row is not None else None

    async def probe_source_candidates(
        self,
        probe_id: str,
    ) -> tuple[ProbeSourceCandidate, ...]:
        """Return reverse links with joined case and probe identities."""
        statement = self._probe_source_statement(probe_id)
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(
            ProbeSourceCandidate(
                case_id=row["bad_case_id"],
                analysis_status=row["analysis_status"],
                case_session_id=_text(row["bad_case_session_id"]),
                probe_session_id=_text(row["session_id"]),
            )
            for row in rows
            if _text(row["bad_case_id"]) is not None
        )

    async def get_probe_snapshot(self, probe_id: str) -> ProbeSnapshot:
        """Read one probe and reverse links in one database session."""
        probe_statement = select(probe_reports).where(
            probe_reports.c.probe_id == probe_id,
        )
        source_statement = self._probe_source_statement(probe_id)
        async with self._database.session() as session:
            probe_row = (await session.execute(probe_statement)).mappings().one_or_none()
            source_rows = (await session.execute(source_statement)).mappings().all()
        return ProbeSnapshot(
            probe=_row_probe(probe_row) if probe_row is not None else None,
            sources=tuple(
                ProbeSourceCandidate(
                    case_id=row["bad_case_id"],
                    analysis_status=row["analysis_status"],
                    case_session_id=_text(row["bad_case_session_id"]),
                    probe_session_id=_text(row["session_id"]),
                )
                for row in source_rows
                if _text(row["bad_case_id"]) is not None
            ),
        )

    async def _related_rows(
        self,
        session: AsyncSession,
        case_ids: tuple[str, ...],
    ) -> tuple[tuple[BadCaseAnalysisRow, ...], tuple[ProbeReportRow, ...]]:
        """Load analyses and probes without a per-case query loop."""
        if not case_ids:
            return (), ()
        analysis_statement = (
            select(bad_case_analysis)
            .where(bad_case_analysis.c.bad_case_id.in_(case_ids))
            .order_by(bad_case_analysis.c.bad_case_id)
        )
        analyses = tuple(
            _row_analysis(row)
            for row in (await session.execute(analysis_statement)).mappings().all()
        )
        probe_ids = tuple(
            sorted(
                {probe_id for row in analyses if (probe_id := _text(row.probe_id)) is not None},
            ),
        )
        if not probe_ids:
            return analyses, ()
        probe_statement = (
            select(probe_reports)
            .where(probe_reports.c.probe_id.in_(probe_ids))
            .order_by(probe_reports.c.probe_id)
        )
        probes = tuple(
            _row_probe(row) for row in (await session.execute(probe_statement)).mappings().all()
        )
        return analyses, probes

    def _probe_source_statement(self, probe_id: str) -> Select[tuple[object, ...]]:
        """Build the reverse-source SELECT used by both read operations."""
        return (
            select(
                bad_case_analysis.c.bad_case_id,
                bad_case_analysis.c.analysis_status,
                bad_cases.c.bad_case_session_id,
                probe_reports.c.session_id,
            )
            .select_from(bad_case_analysis)
            .outerjoin(
                bad_cases,
                bad_cases.c.bad_case_id == bad_case_analysis.c.bad_case_id,
            )
            .outerjoin(
                probe_reports,
                probe_reports.c.probe_id == bad_case_analysis.c.probe_id,
            )
            .where(bad_case_analysis.c.probe_id == probe_id)
            .order_by(bad_case_analysis.c.bad_case_id)
        )
