"""Public contracts for read-only Session problems and probes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, RootModel

from app.service.bad_cases.schemas import AnalysisStatus, AttributeType, DisplayState
from app.service.identity.schemas import IdentityModel
from app.service.sessions.schemas import BadCaseAgent, BadCaseAnchor


class IssueAnalysisResult(IdentityModel):
    """Public result shape for an attribution that classifies an issue."""

    summary: str


class NonIssueAnalysisResult(IdentityModel):
    """Public result shape for an attribution that classifies a non-issue."""

    reason: str
    reasoning: list[str]


class _BadCaseAnalysisBase(IdentityModel):
    """Fields shared by every public attribution display state."""

    probe_id: str | None
    attribute_type: AttributeType | None
    display_state: DisplayState


class UnanalyzedBadCaseAnalysis(_BadCaseAnalysisBase):
    """No attribution result exists for this problem."""

    status: Literal["unanalyzed"]
    display_state: Literal["unanalyzed"]
    result: None


class NonIssueBadCaseAnalysis(_BadCaseAnalysisBase):
    """An analyzed non-issue result always carries its explanation."""

    status: Literal["analyzed_nonissue"]
    display_state: Literal["analyzed_nonissue"]
    result: NonIssueAnalysisResult


class IssueBadCaseAnalysis(_BadCaseAnalysisBase):
    """An analyzed issue result always carries its public summary."""

    status: Literal["analyzed_issue"]
    display_state: Literal[
        "analyzed_issue_model",
        "analyzed_issue_prompt",
        "analyzed_issue_error",
    ]
    result: IssueAnalysisResult


class BadCaseAnalysis(
    RootModel[
        Annotated[
            UnanalyzedBadCaseAnalysis | NonIssueBadCaseAnalysis | IssueBadCaseAnalysis,
            Field(discriminator="status"),
        ]
    ]
):
    """One of the three status-specific public attribution states."""

    @property
    def display_state(self) -> DisplayState:
        """Expose the flat display state used by list cards."""
        return self.root.display_state


def build_bad_case_analysis(
    *,
    status: AnalysisStatus,
    probe_id: str | None,
    attribute_type: AttributeType | None,
    display_state: DisplayState,
    result: Mapping[str, object] | None,
) -> BadCaseAnalysis:
    """Build the status-specific public attribution contract."""
    if status == "unanalyzed":
        return BadCaseAnalysis.model_validate(
            {
                "status": status,
                "probe_id": probe_id,
                "attribute_type": attribute_type,
                "display_state": display_state,
                "result": None,
            },
        )
    if status == "analyzed_nonissue":
        return BadCaseAnalysis.model_validate(
            {
                "status": status,
                "probe_id": probe_id,
                "attribute_type": attribute_type,
                "display_state": display_state,
                "result": dict(result or {}),
            },
        )
    if status == "analyzed_issue":
        return BadCaseAnalysis.model_validate(
            {
                "status": status,
                "probe_id": probe_id,
                "attribute_type": attribute_type,
                "display_state": display_state,
                "result": dict(result or {}),
            },
        )
    raise ValueError(f"unsupported analysis status: {status}")


class BadCase(IdentityModel):
    """Complete public problem card used by list and detail routes.

    ``title`` is the short display title and ``reason`` the description body;
    ``reason`` maps from the ``bad_cases.bad_case_description`` column.
    """

    bad_case_id: str
    session_id: str
    session_title: str
    bad_case_type: Literal["self", "discovery"]
    object_name: str
    object_type: Literal["skill", "agent"]
    object_version: str | None
    anchor: BadCaseAnchor
    bad_case_agent: BadCaseAgent
    title: str
    reason: str
    meta_data: dict[str, Any] | None
    analysis: BadCaseAnalysis
    degraded: bool = False
    diagnostic_code: str | None = None


class BadCaseListResponse(IdentityModel):
    """A Session's problems in external creation order."""

    items: list[BadCase]


class ProbeReport(IdentityModel):
    """One root-cause report with validated reverse source ids."""

    probe_id: str
    session_id: str
    probe_type: Literal["skill", "agent"] | None
    probe_object: str
    object_version: str | None
    attribute_type: AttributeType | None
    probe_description: str
    probe_analysis: str
    created_at: datetime
    updated_at: datetime
    from_bad_cases: list[str]
    from_bad_cases_count: int


class ProbeListResponse(IdentityModel):
    """A Session's root-cause reports."""

    items: list[ProbeReport]
