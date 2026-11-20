"""Public read contracts for one bad case's paged attributions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.service.evolution.attribution_contracts import (
    AttributionExecutionManifest,
    AttributionReportV2,
)
from app.service.identity.schemas import IdentityModel

AttributionObjectType = Literal["skill", "agent", "knowledge"]
AttributionConclusion = Literal["attributed", "non_target", "inconclusive"]
AttributionCategory = Literal["model", "prompt", "error", "flow", "context"]
TriggerOrder = Literal["before", "after", "same", "unknown"]
VersionState = Literal["exact", "unknown"]


class AttributionItem(IdentityModel):
    """One object/revision-scoped attribution shown in the error-detail list.

    ``attributionId`` is the stable deep-link id and maps ``probe_reports.probe_id``;
    ``runId`` prefers the last run that reused the conclusion so a deep link
    opens the run that produced the currently displayed row. ``objectRef`` and
    ``objectCommit`` are display-only evidence from that run; clients fall back
    to ``objectVersion`` when they are absent.
    """

    attribution_id: str = Field(max_length=64)
    bad_case_id: str = Field(max_length=64)
    object_type: AttributionObjectType
    object_name: str = Field(min_length=1, max_length=128)
    object_version: str | None = Field(default=None, max_length=96)
    object_ref: str | None = Field(default=None, max_length=96)
    object_commit: str | None = Field(default=None, max_length=40)
    conclusion: AttributionConclusion
    category: AttributionCategory | None
    confidence: float = Field(ge=0, le=1)
    run_id: str | None = Field(default=None, max_length=36)
    is_cached: bool
    reused_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class AttributionTriggerCompare(IdentityModel):
    """Trigger-point comparison for one attribution detail.

    ``order`` compares the case trigger against the object entry point; a
    missing or incomparable anchor stays ``unknown``. ``versionState`` is
    ``unknown`` when the attribution has no pinned object version, so clients
    must not present it as an exact revision hit.
    """

    object_trigger_at: datetime | None
    case_trigger_at: datetime | None
    order: TriggerOrder
    version_state: VersionState


class AttributionWarning(IdentityModel):
    """One fixed, non-sensitive evidence gap on an attribution detail."""

    code: str = Field(max_length=64)
    message: str = Field(max_length=500)


class AttributionDetail(AttributionItem):
    """One attribution with its reasoning, evidence warnings, and trigger compare."""

    reason: str
    reasoning: str
    policy_version: str = Field(max_length=16)
    attribution_engine: str = Field(max_length=64)
    report_schema_version: str | None = Field(default=None, max_length=32)
    report: AttributionReportV2 | None = None
    execution_manifest: AttributionExecutionManifest | None = None
    execution_manifest_hash: str | None = Field(default=None, max_length=64)
    trigger_compare: AttributionTriggerCompare
    warnings: list[AttributionWarning]


class AttributionPage(IdentityModel):
    """One deterministic newest-first page of a case's attributions."""

    items: list[AttributionItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
