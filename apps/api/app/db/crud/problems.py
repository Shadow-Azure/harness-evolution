"""Single-snapshot reads for public Session problem views."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.crud.bad_cases import (
    BadCaseAnalysisRow,
    BadCaseRow,
    ProbeReportRow,
    ProbeSourceCandidate,
    _row_analysis,
    _row_bad_case,
    _row_probe,
    _text,
)
from app.db.crud.sessions import (
    AgentRecord,
    EventRecord,
    SessionRecord,
    _agent_record,
    _event_record,
    _session_record,
)
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
    session_families,
)


@dataclass(frozen=True, slots=True)
class ProblemSnapshot:
    """Canonical Session structure and external rows from one DB snapshot."""

    session: SessionRecord
    agents: tuple[AgentRecord, ...]
    events: tuple[EventRecord, ...]
    cases: tuple[BadCaseRow, ...]
    analyses: tuple[BadCaseAnalysisRow, ...]
    probes: tuple[ProbeReportRow, ...]


@dataclass(frozen=True, slots=True)
class ProbeListSnapshot:
    """One Session's probes and reverse sources from one DB snapshot."""

    session: SessionRecord
    probes: tuple[ProbeReportRow, ...]
    sources: tuple[ProbeSourceCandidate, ...]


class ProblemRepository:
    """Read Session and external problem tables without any write path."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to one application database."""
        self._database = database

    async def session_snapshot(self, session_id: str) -> ProblemSnapshot | None:
        """Return one coherent Session/problem version for a Session route."""
        async with self._database.session() as session:
            family = await self._family(session, session_id)
            if family is None:
                return None
            cases = await self._cases(session, session_id=session_id)
            analyses, probes = await self._related(session, tuple(row.bad_case_id for row in cases))
            return ProblemSnapshot(
                session=family,
                agents=await self._agents(session, session_id),
                events=await self._events(session, session_id),
                cases=cases,
                analyses=analyses,
                probes=probes,
            )

    async def case_snapshot(self, case_id: str) -> ProblemSnapshot | None:
        """Return one coherent case, Session, tree, and external-row version."""
        async with self._database.session() as session:
            case = await self._case(session, case_id)
            if case is None:
                return None
            family = await self._family(session, case.bad_case_session_id)
            if family is None:
                return None
            analyses, probes = await self._related(session, (case_id,))
            return ProblemSnapshot(
                session=family,
                agents=await self._agents(session, family.id),
                events=await self._events(session, family.id),
                cases=(case,),
                analyses=analyses,
                probes=probes,
            )

    async def session_probes(self, session_id: str) -> ProbeListSnapshot | None:
        """Return one Session's probes with batched reverse links."""
        async with self._database.session() as session:
            family = await self._family(session, session_id)
            if family is None:
                return None
            probes = tuple(
                _row_probe(row)
                for row in (
                    await session.execute(
                        select(probe_reports)
                        .where(probe_reports.c.session_id == session_id)
                        .order_by(probe_reports.c.created_at, probe_reports.c.probe_id),
                    )
                )
                .mappings()
                .all()
            )
            if not probes:
                return ProbeListSnapshot(session=family, probes=(), sources=())
            sources = tuple(
                self._source_candidate(row)
                for row in (
                    await session.execute(
                        self._batch_source_statement(
                            tuple(probe.probe_id for probe in probes),
                        ),
                    )
                )
                .mappings()
                .all()
            )
            return ProbeListSnapshot(session=family, probes=probes, sources=sources)

    async def _family(
        self,
        session: AsyncSession,
        session_id: str,
    ) -> SessionRecord | None:
        row = (
            (
                await session.execute(
                    select(session_families).where(session_families.c.id == session_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        return _session_record(row) if row is not None else None

    async def _agents(
        self,
        session: AsyncSession,
        session_id: str,
    ) -> tuple[AgentRecord, ...]:
        rows = (
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
        return tuple(_agent_record(row) for row in rows)

    async def _events(
        self,
        session: AsyncSession,
        session_id: str,
    ) -> tuple[EventRecord, ...]:
        rows = (
            (
                await session.execute(
                    select(agent_events)
                    .join(agents, agents.c.id == agent_events.c.agent_id)
                    .where(agents.c.root_session_id == session_id)
                    .order_by(agent_events.c.agent_id, agent_events.c.event_index),
                )
            )
            .mappings()
            .all()
        )
        return tuple(_event_record(row) for row in rows)

    async def _case(self, session: AsyncSession, case_id: str) -> BadCaseRow | None:
        row = (
            (
                await session.execute(
                    select(bad_cases).where(bad_cases.c.bad_case_id == case_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        return _row_bad_case(row) if row is not None else None

    async def _cases(
        self,
        session: AsyncSession,
        *,
        session_id: str,
    ) -> tuple[BadCaseRow, ...]:
        rows = (
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
        return tuple(_row_bad_case(row) for row in rows)

    async def _related(
        self,
        session: AsyncSession,
        case_ids: tuple[str, ...],
    ) -> tuple[tuple[BadCaseAnalysisRow, ...], tuple[ProbeReportRow, ...]]:
        if not case_ids:
            return (), ()
        analyses = tuple(
            _row_analysis(row)
            for row in (
                await session.execute(
                    select(bad_case_analysis)
                    .where(bad_case_analysis.c.bad_case_id.in_(case_ids))
                    .order_by(bad_case_analysis.c.bad_case_id),
                )
            )
            .mappings()
            .all()
        )
        probe_ids = tuple(
            sorted(
                {probe_id for row in analyses if (probe_id := _text(row.probe_id)) is not None},
            ),
        )
        if not probe_ids:
            return analyses, ()
        probes = tuple(
            _row_probe(row)
            for row in (
                await session.execute(
                    select(probe_reports)
                    .where(probe_reports.c.probe_id.in_(probe_ids))
                    .order_by(probe_reports.c.probe_id),
                )
            )
            .mappings()
            .all()
        )
        return analyses, probes

    def _batch_source_statement(self, probe_ids: tuple[str, ...]) -> Select[tuple[object, ...]]:
        return (
            select(
                bad_case_analysis.c.probe_id.label("source_probe_id"),
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
            .where(bad_case_analysis.c.probe_id.in_(probe_ids))
            .order_by(bad_case_analysis.c.probe_id, bad_case_analysis.c.bad_case_id)
        )

    @staticmethod
    def _source_candidate(row: RowMapping) -> ProbeSourceCandidate:
        return ProbeSourceCandidate(
            case_id=row["bad_case_id"],
            analysis_status=row["analysis_status"],
            case_session_id=_text(row["bad_case_session_id"]),
            probe_session_id=_text(row["session_id"]),
            probe_id=_text(row["source_probe_id"]),
        )
