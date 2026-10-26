"""Merge external issue, analysis, and probe rows into read models."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from app.db.crud.bad_cases import (
    BadCaseAnalysisRow,
    BadCaseRepositoryProtocol,
    BadCaseRow,
    ProbeReportRow,
    ProbeSourceCandidate,
)
from app.service.bad_cases.schemas import (
    AnalysisStatus,
    AttributeType,
    BadCaseAnalysisReadModel,
    BadCaseListReadModel,
    BadCaseObjectType,
    BadCaseReadModel,
    BadCaseType,
    DisplayState,
    ExternalReadWarning,
    ProbeReportLookup,
    ProbeReportReadModel,
)

logger = logging.getLogger(__name__)


def _safe_text(value: object) -> str | None:
    """Return one non-empty external text value without coercing other types."""
    return value if isinstance(value, str) and value else None


def _safe_mapping(value: object) -> Mapping[str, object] | None:
    """Freeze an external JSON object while rejecting scalar or array drift."""
    if not isinstance(value, Mapping):
        return None
    return MappingProxyType(dict(value))


def _literal[T](value: object, allowed: tuple[T, ...]) -> T | None:
    """Return a value only when it belongs to a closed external enum."""
    return value if value in allowed else None


def _warning(
    code: str,
    message: str,
    *,
    bad_case_id: str | None = None,
    probe_id: str | None = None,
    field: str | None = None,
) -> ExternalReadWarning:
    """Build and emit one sanitized external read-model warning."""
    logger.warning(
        message,
        extra={
            "code": code,
            "bad_case_id": bad_case_id,
            "probe_id": probe_id,
            "field": field,
        },
    )
    return ExternalReadWarning(
        code=code,
        message=message,
        bad_case_id=bad_case_id,
        probe_id=probe_id,
        field=field,
    )


def _empty_analysis() -> BadCaseAnalysisReadModel:
    """Return the canonical unattributed view."""
    return BadCaseAnalysisReadModel(
        status="unanalyzed",
        probe_id=None,
        attribute_type=None,
        result=None,
        display_state="unanalyzed",
    )


def _display_state(attribute_type: AttributeType) -> DisplayState:
    """Map a valid issue attribution type to its prototype display state."""
    if attribute_type == "model":
        return "analyzed_issue_model"
    if attribute_type == "prompt":
        return "analyzed_issue_prompt"
    return "analyzed_issue_error"


def _validated_analysis_result(
    status: AnalysisStatus,
    value: object,
) -> tuple[Mapping[str, object] | None, bool]:
    """Return a valid status-specific snapshot and whether it matched its shape."""
    if status == "unanalyzed":
        return None, value is None
    result = _safe_mapping(value)
    if result is None:
        return None, False
    if status == "analyzed_issue":
        valid = _safe_text(result.get("summary")) is not None
        return (result if valid else None), valid
    reasoning = result.get("reasoning")
    if (
        _safe_text(result.get("reason")) is None
        or not isinstance(reasoning, list)
        or not all(isinstance(item, str) for item in reasoning)
    ):
        return None, False
    return result, True


class BadCaseService:
    """Expose validated read models; all writes remain external to this service."""

    def __init__(self, repository: BadCaseRepositoryProtocol) -> None:
        """Bind the service to its read-only repository."""
        self._repository = repository

    async def list_for_session(self, session_id: str) -> BadCaseListReadModel:
        """Return a session's issues in stable order with merged attribution."""
        snapshot = await self._repository.list_snapshot(session_id)
        return self.merge_snapshot(snapshot.cases, snapshot.analyses, snapshot.probes)

    async def get_case(self, case_id: str) -> BadCaseReadModel | None:
        """Return one issue by id or ``None`` when the external table has no row."""
        snapshot = await self._repository.get_case_snapshot(case_id)
        if not snapshot.cases:
            return None
        result = self.merge_snapshot(
            snapshot.cases,
            snapshot.analyses,
            snapshot.probes,
        )
        return result.items[0] if result.items else None

    async def get_probe(self, probe_id: str) -> ProbeReportReadModel | None:
        """Return one root-cause report with reverse-linked source issues."""
        return (await self.get_probe_result(probe_id)).model

    async def get_probe_result(self, probe_id: str) -> ProbeReportLookup:
        """Return one probe and diagnostics, or no model when identity is invalid."""
        snapshot = await self._repository.get_probe_snapshot(probe_id)
        if snapshot.probe is None:
            return ProbeReportLookup(model=None, warnings=())
        return self._probe_model(snapshot.probe, snapshot.sources)

    def merge_snapshot(
        self,
        rows: tuple[BadCaseRow, ...],
        analysis_rows: tuple[BadCaseAnalysisRow, ...],
        probe_rows: tuple[ProbeReportRow, ...],
    ) -> BadCaseListReadModel:
        """Batch-load attribution and probe rows before assembling each case."""
        cases: list[tuple[BadCaseRow, str, tuple[ExternalReadWarning, ...]]] = []
        warnings: list[ExternalReadWarning] = []
        for row in rows:
            case_id = _safe_text(row.bad_case_id)
            session_id = _safe_text(row.bad_case_session_id)
            if case_id is None or session_id is None:
                warning = _warning(
                    "EXTERNAL_FIELD_MISSING",
                    "external issue identity is missing",
                    field="bad_case_id" if case_id is None else "bad_case_session_id",
                )
                warnings.append(warning)
                continue
            cases.append((row, session_id, ()))

        if not cases:
            return BadCaseListReadModel(items=(), warnings=tuple(warnings))

        analyses = {row.bad_case_id: row for row in analysis_rows}
        probes = {row.probe_id: row for row in probe_rows if _safe_text(row.probe_id) is not None}

        items: list[BadCaseReadModel] = []
        for row, session_id, row_warnings in cases:
            case_id = _safe_text(row.bad_case_id)
            if case_id is None:
                continue
            model_warnings = list(row_warnings)
            analysis = self._analysis_model(
                case_id,
                session_id,
                analyses.get(case_id),
                probes,
                model_warnings,
            )
            items.append(
                self._case_model(
                    row,
                    session_id,
                    analysis,
                    tuple(model_warnings),
                ),
            )
            warnings.extend(model_warnings)
        return BadCaseListReadModel(items=tuple(items), warnings=tuple(warnings))

    def merge_probe_rows(
        self,
        probe_rows: tuple[ProbeReportRow, ...],
        source_rows: tuple[ProbeSourceCandidate, ...],
    ) -> tuple[ProbeReportReadModel, ...]:
        """Merge a batched probe set using the same validation as detail reads."""
        by_probe: dict[str, list[ProbeSourceCandidate]] = {}
        for source in source_rows:
            if source.probe_id is not None:
                by_probe.setdefault(source.probe_id, []).append(source)
        models: list[ProbeReportReadModel] = []
        for row in probe_rows:
            lookup = self._probe_model(
                row,
                tuple(by_probe.get(row.probe_id, ())),
            )
            if lookup.model is not None:
                models.append(lookup.model)
        return tuple(models)

    def _case_model(
        self,
        row: BadCaseRow,
        session_id: str,
        analysis: BadCaseAnalysisReadModel,
        warnings: tuple[ExternalReadWarning, ...],
    ) -> BadCaseReadModel:
        """Convert one identity-valid row and its merged attribution."""
        mutable_warnings = list(warnings)
        bad_case_type: BadCaseType | None = _literal(
            row.bad_case_type,
            ("self", "discovery"),
        )
        object_type: BadCaseObjectType | None = _literal(
            row.object_type,
            ("skill", "agent"),
        )
        object_name = _safe_text(row.object_name)
        reason = _safe_text(row.reason)
        meta_data = _safe_mapping(row.meta_data)
        if bad_case_type is None:
            warning = _warning(
                "EXTERNAL_FIELD_INVALID",
                "external issue type is invalid",
                bad_case_id=row.bad_case_id,
                field="bad_case_type",
            )
            mutable_warnings.append(warning)
        if object_type is None:
            warning = _warning(
                "EXTERNAL_FIELD_INVALID",
                "external issue object type is invalid",
                bad_case_id=row.bad_case_id,
                field="object_type",
            )
            mutable_warnings.append(warning)
        if object_name is None or reason is None:
            warning = _warning(
                "EXTERNAL_FIELD_MISSING",
                "external issue presentation field is missing",
                bad_case_id=row.bad_case_id,
                field="object_name" if object_name is None else "reason",
            )
            mutable_warnings.append(warning)
        if row.meta_data is not None and meta_data is None:
            warning = _warning(
                "EXTERNAL_FIELD_INVALID",
                "external issue metadata is not an object",
                bad_case_id=row.bad_case_id,
                field="meta_data",
            )
            mutable_warnings.append(warning)
        return BadCaseReadModel(
            bad_case_id=row.bad_case_id,
            session_id=session_id,
            bad_case_type=bad_case_type,
            object_name=object_name or "",
            object_type=object_type,
            object_version=_safe_text(row.object_version),
            bad_case_agent_id=_safe_text(row.bad_case_agent_id),
            reason=reason or "",
            meta_data=meta_data,
            source=_safe_text(row.source),
            created_at=row.created_at,
            updated_at=row.updated_at,
            analysis=analysis,
            warnings=tuple(mutable_warnings),
        )

    def _analysis_model(
        self,
        case_id: str,
        session_id: str,
        row: BadCaseAnalysisRow | None,
        probes: Mapping[str, ProbeReportRow],
        warnings: list[ExternalReadWarning],
    ) -> BadCaseAnalysisReadModel:
        """Validate one external attribution state and probe relationship."""
        if row is None:
            return _empty_analysis()

        status: AnalysisStatus | None = _literal(
            row.analysis_status,
            ("unanalyzed", "analyzed_nonissue", "analyzed_issue"),
        )
        probe_id = _safe_text(row.probe_id)
        if status is None:
            warnings.append(
                _warning(
                    "INVALID_ANALYSIS_STATUS",
                    "external analysis status is invalid",
                    bad_case_id=case_id,
                    field="analysis_status",
                ),
            )
            return _empty_analysis()
        if (status == "analyzed_issue") != (probe_id is not None):
            warnings.append(
                _warning(
                    "ANALYSIS_PROBE_MISMATCH",
                    "external analysis and probe link disagree",
                    bad_case_id=case_id,
                    probe_id=probe_id,
                    field="probe_id",
                ),
            )
            return _empty_analysis()

        result, result_valid = _validated_analysis_result(status, row.analysis_result)
        if not result_valid:
            warnings.append(
                _warning(
                    "ANALYSIS_RESULT_INVALID",
                    "external analysis result does not match its status",
                    bad_case_id=case_id,
                    field="analysis_result",
                ),
            )
        if status != "analyzed_issue":
            display: DisplayState = (
                "analyzed_nonissue" if status == "analyzed_nonissue" else "unanalyzed"
            )
            return BadCaseAnalysisReadModel(
                status=status,
                probe_id=None,
                attribute_type=None,
                result=result,
                display_state=display,
            )

        probe = probes.get(probe_id or "")
        if probe is None:
            warnings.append(
                _warning(
                    "PROBE_NOT_FOUND",
                    "external analysis references a missing probe",
                    bad_case_id=case_id,
                    probe_id=probe_id,
                ),
            )
            return _empty_analysis()
        if _safe_text(probe.session_id) != session_id:
            warnings.append(
                _warning(
                    "PROBE_SESSION_MISMATCH",
                    "external probe belongs to a different session",
                    bad_case_id=case_id,
                    probe_id=probe_id,
                ),
            )
            return _empty_analysis()
        attribute_type: AttributeType | None = _literal(
            probe.attribute_type,
            ("model", "prompt", "error"),
        )
        if attribute_type is None:
            warnings.append(
                _warning(
                    "INVALID_ATTRIBUTE_TYPE",
                    "external probe attribute type is invalid",
                    bad_case_id=case_id,
                    probe_id=probe_id,
                    field="attribute_type",
                ),
            )
            return _empty_analysis()
        return BadCaseAnalysisReadModel(
            status=status,
            probe_id=probe_id,
            attribute_type=attribute_type,
            result=result,
            display_state=_display_state(attribute_type),
        )

    def _probe_model(
        self,
        row: ProbeReportRow,
        sources: tuple[ProbeSourceCandidate, ...],
    ) -> ProbeReportLookup:
        """Convert one externally owned probe and its reverse source links."""
        warnings: list[ExternalReadWarning] = []
        probe_id = _safe_text(row.probe_id)
        session_id = _safe_text(row.session_id)
        if probe_id is None or session_id is None:
            warning = _warning(
                "EXTERNAL_FIELD_MISSING",
                "external probe identity is missing",
                probe_id=probe_id,
                field="probe_id" if probe_id is None else "session_id",
            )
            return ProbeReportLookup(model=None, warnings=(warning,))
        probe_type = _literal(row.probe_type, ("skill", "agent"))
        attribute_type = _literal(row.attribute_type, ("model", "prompt", "error"))
        if probe_type is None:
            warnings.append(
                _warning(
                    "EXTERNAL_FIELD_INVALID",
                    "external probe type is invalid",
                    probe_id=probe_id,
                    field="probe_type",
                ),
            )
        if attribute_type is None:
            warnings.append(
                _warning(
                    "INVALID_ATTRIBUTE_TYPE",
                    "external probe attribute type is invalid",
                    probe_id=probe_id,
                    field="attribute_type",
                ),
            )
        probe_object = _safe_text(row.probe_object)
        probe_description = _safe_text(row.probe_description)
        probe_analysis = _safe_text(row.probe_analysis)
        for field, value in (
            ("probe_object", probe_object),
            ("probe_description", probe_description),
            ("probe_analysis", probe_analysis),
        ):
            if value is None:
                warnings.append(
                    _warning(
                        "EXTERNAL_FIELD_MISSING",
                        "external probe presentation field is missing",
                        probe_id=probe_id,
                        field=field,
                    ),
                )
        valid_source_ids: list[str] = []
        invalid_source = False
        for source in sources:
            valid = (
                source.analysis_status == "analyzed_issue"
                and source.case_session_id == session_id
                and source.probe_session_id == session_id
            )
            if not valid:
                invalid_source = True
                continue
            valid_source_ids.append(source.case_id)
        if invalid_source:
            warnings.append(
                _warning(
                    "INVALID_PROBE_SOURCE_LINK",
                    "external probe contains an invalid source link",
                    probe_id=probe_id,
                    field="from_bad_cases",
                ),
            )
        source_ids = tuple(dict.fromkeys(valid_source_ids))
        model = ProbeReportReadModel(
            probe_id=probe_id or "",
            session_id=session_id or "",
            probe_type=cast(BadCaseObjectType | None, probe_type),
            probe_object=probe_object or "",
            object_version=_safe_text(row.object_version),
            attribute_type=cast(AttributeType | None, attribute_type),
            probe_description=probe_description or "",
            probe_analysis=probe_analysis or "",
            created_at=row.created_at,
            updated_at=row.updated_at,
            from_bad_cases=source_ids,
            from_bad_cases_count=len(source_ids),
            warnings=tuple(warnings),
        )
        return ProbeReportLookup(model=model, warnings=tuple(warnings))
