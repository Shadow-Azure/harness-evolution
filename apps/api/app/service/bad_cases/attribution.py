"""Paged attribution reads and one-case deep-link ownership checks."""

from __future__ import annotations

from typing import Literal, cast

from app.db.crud.attributions import (
    AttributionRecord,
    AttributionRepository,
    CandidateTriggerRecord,
)
from app.db.crud.problems import ProblemRepository
from app.db.crud.read_scope import WorkspaceReadScope
from app.errors import AppError, ErrorCode
from app.service.bad_cases.attribution_schemas import (
    AttributionCategory,
    AttributionConclusion,
    AttributionDetail,
    AttributionItem,
    AttributionObjectType,
    AttributionPage,
    AttributionTriggerCompare,
    AttributionWarning,
    VersionState,
)

TriggerOrder = Literal["before", "after", "same", "unknown"]


class AttributionReadService:
    """Expose one case's several attribution conclusions to the error detail.

    The service owns two rules that the repository must not encode: a case is
    only readable inside the caller's workspace scope, and an attribution id
    must still be linked to the requested case before its detail is returned.
    """

    def __init__(
        self,
        attributions: AttributionRepository,
        problems: ProblemRepository,
    ) -> None:
        """Bind the read service to its attribution and case-visibility reads."""
        self._attributions = attributions
        self._problems = problems

    async def page(
        self,
        case_id: str,
        scope: WorkspaceReadScope,
        page: int,
        page_size: int,
    ) -> AttributionPage:
        """Return one newest-first page after validating case ownership."""
        await self._require_case(case_id, scope)
        total = await self._attributions.count_links(case_id)
        rows = await self._attributions.list_attributions(
            case_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return AttributionPage(
            items=[self._item(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def detail(
        self,
        case_id: str,
        attribution_id: str,
        scope: WorkspaceReadScope,
    ) -> AttributionDetail:
        """Return one attribution only while it is linked to the requested case."""
        await self._require_case(case_id, scope)
        record = await self._attributions.get_attribution(case_id, attribution_id)
        if record is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.ATTRIBUTION_NOT_FOUND,
                message="attribution not found for this bad case",
            )
        candidate = await self._attributions.latest_candidate_trigger(attribution_id)
        return self._detail(record, candidate)

    async def _require_case(self, case_id: str, scope: WorkspaceReadScope) -> None:
        """Reject an unknown or out-of-workspace case before any attribution read."""
        if not await self._problems.case_visible(case_id, scope):
            raise AppError(
                status_code=404,
                code=ErrorCode.BAD_CASE_NOT_FOUND,
                message="bad case not found",
            )

    def _item(self, record: AttributionRecord) -> AttributionItem:
        """Project one joined row into the list contract."""
        return AttributionItem(
            attribution_id=record.probe_id,
            bad_case_id=record.bad_case_id,
            object_type=cast(AttributionObjectType, record.probe_type),
            object_name=record.probe_object,
            object_version=record.object_version,
            conclusion=cast(AttributionConclusion, record.conclusion),
            category=cast(AttributionCategory | None, record.attribute_type),
            confidence=record.confidence,
            run_id=record.last_reused_run_id or record.created_run_id,
            is_cached=record.last_reused_run_id is not None,
            reused_count=record.reused_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _detail(
        self,
        record: AttributionRecord,
        candidate: CandidateTriggerRecord | None,
    ) -> AttributionDetail:
        """Project one joined row into the detail contract with trigger evidence."""
        item = self._item(record)
        order = _trigger_order(candidate)
        version_state: VersionState = "exact" if record.object_version is not None else "unknown"
        return AttributionDetail(
            **item.model_dump(),
            reason=record.probe_description,
            reasoning=record.probe_analysis,
            policy_version=record.policy_version,
            attribution_engine=record.attribution_engine,
            trigger_compare=AttributionTriggerCompare(
                object_trigger_at=(candidate.object_trigger_at if candidate is not None else None),
                case_trigger_at=(candidate.case_trigger_at if candidate is not None else None),
                order=order,
                version_state=version_state,
            ),
            warnings=_evidence_warnings(record, order),
        )


def _evidence_warnings(
    record: AttributionRecord,
    order: TriggerOrder,
) -> list[AttributionWarning]:
    """Return fixed, non-sensitive evidence gaps a client can display.

    The messages never interpolate external fields, so a drifted row cannot
    leak content through the warning channel.
    """
    warnings: list[AttributionWarning] = []
    if record.object_version is None:
        warnings.append(
            AttributionWarning(
                code="ATTRIBUTION_VERSION_UNKNOWN",
                message="The attribution has no pinned object version.",
            ),
        )
    if order == "unknown":
        warnings.append(
            AttributionWarning(
                code="ATTRIBUTION_TRIGGER_UNKNOWN",
                message="The two trigger points cannot be compared.",
            ),
        )
    if record.attribution_engine == "legacy-probe-import":
        warnings.append(
            AttributionWarning(
                code="ATTRIBUTION_LEGACY_IMPORT",
                message="The attribution was imported from a legacy probe.",
            ),
        )
    if record.last_reused_run_id is None and record.created_run_id is None:
        warnings.append(
            AttributionWarning(
                code="ATTRIBUTION_RUN_UNKNOWN",
                message="No evolution run is recorded for this attribution.",
            ),
        )
    return warnings


def _trigger_order(candidate: CandidateTriggerRecord | None) -> TriggerOrder:
    """Compare the case trigger against the object entry point.

    Wall-clock timestamps win when both sides carry one; otherwise the
    ``(tree_index, event_index)`` lexicographic order is used. A candidate that
    prepare already marked incomparable, or one whose coordinates are
    incomplete, stays ``unknown`` and never claims "after".
    """
    if candidate is None or candidate.order_state != "comparable":
        return "unknown"
    object_at = candidate.object_trigger_at
    case_at = candidate.case_trigger_at
    if object_at is not None and case_at is not None:
        if case_at < object_at:
            return "before"
        if case_at == object_at:
            return "same"
        return "after"
    object_tree = candidate.object_trigger_tree_index
    object_event = candidate.object_trigger_event_index
    case_tree = candidate.case_trigger_tree_index
    case_event = candidate.case_trigger_event_index
    if None in (object_tree, object_event, case_tree, case_event):
        return "unknown"
    object_key = (object_tree, object_event)
    case_key = (case_tree, case_event)
    if case_key < object_key:
        return "before"
    if case_key == object_key:
        return "same"
    return "after"
