"""Public read models for externally owned issues and attribution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

BadCaseType = Literal["self", "discovery"]
BadCaseObjectType = Literal["skill", "agent"]
AnalysisStatus = Literal["unanalyzed", "analyzed_nonissue", "analyzed_issue"]
AttributeType = Literal["model", "prompt", "error"]
DisplayState = Literal[
    "unanalyzed",
    "analyzed_nonissue",
    "analyzed_issue_model",
    "analyzed_issue_prompt",
    "analyzed_issue_error",
]


@dataclass(frozen=True, slots=True)
class ExternalReadWarning:
    """One sanitized diagnostic emitted while merging external rows."""

    code: str
    message: str
    bad_case_id: str | None = None
    probe_id: str | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class BadCaseAnalysisReadModel:
    """Merged attribution state used by issue list and detail responses."""

    status: AnalysisStatus
    probe_id: str | None
    attribute_type: AttributeType | None
    result: Mapping[str, object] | None
    display_state: DisplayState


@dataclass(frozen=True, slots=True)
class BadCaseReadModel:
    """One issue with its validated external attribution state."""

    bad_case_id: str
    session_id: str
    bad_case_type: BadCaseType | None
    object_name: str
    object_type: BadCaseObjectType | None
    object_version: str | None
    bad_case_agent_id: str | None
    reason: str
    meta_data: Mapping[str, object] | None
    source: str | None
    created_at: datetime
    updated_at: datetime
    analysis: BadCaseAnalysisReadModel
    warnings: tuple[ExternalReadWarning, ...]

    @property
    def display_state(self) -> DisplayState:
        """Expose the list-item display state used by the prototype."""
        return self.analysis.display_state


@dataclass(frozen=True, slots=True)
class BadCaseListReadModel:
    """Stable issue list plus non-fatal external schema diagnostics."""

    items: tuple[BadCaseReadModel, ...]
    warnings: tuple[ExternalReadWarning, ...]


@dataclass(frozen=True, slots=True)
class ProbeReportReadModel:
    """One root-cause report with reverse-linked source issue ids."""

    probe_id: str
    session_id: str
    probe_type: BadCaseObjectType | None
    probe_object: str
    object_version: str | None
    attribute_type: AttributeType | None
    probe_description: str
    probe_analysis: str
    created_at: datetime
    updated_at: datetime
    from_bad_cases: tuple[str, ...]
    from_bad_cases_count: int
    warnings: tuple[ExternalReadWarning, ...]


@dataclass(frozen=True, slots=True)
class ProbeReportLookup:
    """Probe read result with diagnostics for externally drifted identity rows."""

    model: ProbeReportReadModel | None
    warnings: tuple[ExternalReadWarning, ...]
