"""Compose Session structure and external issue tables into public contracts."""

from __future__ import annotations

import logging

from app.db.crud.problems import ProbeListSnapshot, ProblemRepository, ProblemSnapshot
from app.db.crud.sessions import EventRecord
from app.errors import AppError, ErrorCode
from app.service.bad_cases.schemas import BadCaseReadModel, ProbeReportReadModel
from app.service.bad_cases.service import BadCaseService
from app.service.problems.anchor import resolve_problem_anchor
from app.service.problems.schemas import (
    BadCase,
    BadCaseAnalysis,
    BadCaseListResponse,
    ProbeListResponse,
    ProbeReport,
    build_bad_case_analysis,
)
from app.service.sessions.schemas import BadCaseAgent, BadCaseAnchor

logger = logging.getLogger(__name__)


def _events_by_agent(events: tuple[EventRecord, ...]) -> dict[str, list[EventRecord]]:
    grouped: dict[str, list[EventRecord]] = {}
    for event in events:
        grouped.setdefault(event.agent_id, []).append(event)
    return grouped


class ProblemService:
    """Read one coherent Session/problem snapshot and expose public DTOs."""

    def __init__(self, repository: ProblemRepository, bad_cases: BadCaseService) -> None:
        """Bind the public service to its snapshot and external read boundaries."""
        self._repository = repository
        self._bad_cases = bad_cases

    async def list_for_session(self, session_id: str) -> BadCaseListResponse:
        """Return all problems for one Session with tree-derived anchors."""
        snapshot = await self._repository.session_snapshot(session_id)
        if snapshot is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.SESSION_NOT_FOUND,
                message="session not found",
            )
        merged = self._bad_cases.merge_snapshot(
            snapshot.cases,
            snapshot.analyses,
            snapshot.probes,
        )
        return BadCaseListResponse(
            items=self._public_cases(snapshot, merged.items),
        )

    async def get_case(self, case_id: str, session_id: str | None) -> BadCase:
        """Return one problem after enforcing optional Session ownership."""
        snapshot = await self._repository.case_snapshot(case_id)
        if snapshot is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.BAD_CASE_NOT_FOUND,
                message="bad case not found",
            )
        self._check_owner(snapshot.cases[0].bad_case_session_id, session_id)
        merged = self._bad_cases.merge_snapshot(
            snapshot.cases,
            snapshot.analyses,
            snapshot.probes,
        )
        if not merged.items:
            raise AppError(
                status_code=404,
                code=ErrorCode.BAD_CASE_NOT_FOUND,
                message="bad case not found",
            )
        return self._public_cases(snapshot, merged.items)[0]

    async def get_analysis(
        self,
        case_id: str,
        session_id: str | None,
    ) -> BadCaseAnalysis:
        """Return the case's analysis placeholder without fetching a probe row."""
        case = await self.get_case(case_id, session_id)
        return case.analysis

    async def get_probe(self, probe_id: str) -> ProbeReport:
        """Return one validated probe and its reverse source links."""
        result = await self._bad_cases.get_probe_result(probe_id)
        if result.model is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.PROBE_NOT_FOUND,
                message="probe not found",
            )
        return self._public_probe(result.model)

    async def list_probes(self, session_id: str) -> ProbeListResponse:
        """Return every probe belonging to one Session."""
        snapshot = await self._repository.session_probes(session_id)
        if snapshot is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.SESSION_NOT_FOUND,
                message="session not found",
            )
        return ProbeListResponse(items=self._probes(snapshot))

    def _probes(self, snapshot: ProbeListSnapshot) -> list[ProbeReport]:
        models = self._bad_cases.merge_probe_rows(
            snapshot.probes,
            snapshot.sources,
        )
        return [self._public_probe(model) for model in models]

    def _public_cases(
        self,
        snapshot: ProblemSnapshot,
        items: tuple[BadCaseReadModel, ...],
    ) -> list[BadCase]:
        agents_by_id = {agent.id: agent for agent in snapshot.agents}
        mains = [agent for agent in snapshot.agents if agent.kind == "main"]
        if len(mains) != 1:
            raise AppError(
                status_code=500,
                code=ErrorCode.INTERNAL,
                message="session problem tree is malformed",
            )
        events = _events_by_agent(snapshot.events)
        result: list[BadCase] = []
        for item in items:
            title_degraded = any(
                warning.code == "EXTERNAL_FIELD_MISSING" and warning.field == "title"
                for warning in item.warnings
            )
            degraded = item.bad_case_type is None or item.object_type is None or title_degraded
            diagnostic_code: str | None = None
            if degraded:
                diagnostic_code = next(
                    (
                        warning.code
                        for warning in item.warnings
                        if warning.field in {"bad_case_type", "object_type", "title"}
                    ),
                    "EXTERNAL_FIELD_INVALID",
                )
                logger.warning(
                    "public problem has invalid external presentation fields",
                    extra={"bad_case_id": item.bad_case_id},
                )
                anchor = resolve_problem_anchor(
                    bad_case_type=None,
                    object_name=item.object_name,
                    object_type=None,
                    bad_case_agent_id=None,
                    agents_by_id=agents_by_id,
                    events_by_agent=events,
                    main=mains[0],
                )
            else:
                anchor = resolve_problem_anchor(
                    bad_case_type=item.bad_case_type,
                    object_name=item.object_name,
                    object_type=item.object_type,
                    bad_case_agent_id=item.bad_case_agent_id,
                    agents_by_id=agents_by_id,
                    events_by_agent=events,
                    main=mains[0],
                )
            if anchor.warning is not None:
                logger.warning(
                    anchor.warning,
                    extra={"bad_case_id": item.bad_case_id},
                )
            analysis_status = item.analysis.status
            analysis_probe_id = item.analysis.probe_id
            analysis_attribute_type = item.analysis.attribute_type
            analysis_display_state = item.analysis.display_state
            analysis_result = (
                dict(item.analysis.result) if item.analysis.result is not None else None
            )
            if analysis_status != "unanalyzed" and analysis_result is None:
                analysis_status = "unanalyzed"
                analysis_probe_id = None
                analysis_attribute_type = None
                analysis_display_state = "unanalyzed"
            result.append(
                BadCase(
                    bad_case_id=item.bad_case_id,
                    session_id=item.session_id,
                    session_title=snapshot.session.title,
                    bad_case_type=item.bad_case_type or "self",
                    object_name=item.object_name,
                    object_type=item.object_type or "agent",
                    object_version=item.object_version,
                    anchor=BadCaseAnchor(
                        agent_id=anchor.agent_id,
                        event_index=anchor.event_index,
                    ),
                    bad_case_agent=BadCaseAgent(
                        session_id=item.session_id,
                        agent_id=item.bad_case_agent_id,
                    ),
                    title=item.title,
                    reason=item.reason,
                    meta_data=dict(item.meta_data) if item.meta_data is not None else None,
                    analysis=build_bad_case_analysis(
                        status=analysis_status,
                        probe_id=analysis_probe_id,
                        attribute_type=analysis_attribute_type,
                        display_state=analysis_display_state,
                        result=analysis_result,
                    ),
                    degraded=degraded,
                    diagnostic_code=diagnostic_code,
                ),
            )
        return result

    @staticmethod
    def _public_probe(model: ProbeReportReadModel) -> ProbeReport:
        probe = model
        return ProbeReport(
            probe_id=probe.probe_id,
            session_id=probe.session_id,
            probe_type=probe.probe_type,
            probe_object=probe.probe_object,
            object_version=probe.object_version,
            attribute_type=probe.attribute_type,
            probe_description=probe.probe_description,
            probe_analysis=probe.probe_analysis,
            created_at=probe.created_at,
            updated_at=probe.updated_at,
            from_bad_cases=list(probe.from_bad_cases),
            from_bad_cases_count=probe.from_bad_cases_count,
        )

    @staticmethod
    def _check_owner(actual: str, requested: str | None) -> None:
        if requested is not None and requested != actual:
            raise AppError(
                status_code=409,
                code=ErrorCode.BAD_CASE_SESSION_MISMATCH,
                message="bad case does not belong to the requested session",
            )
