"""Public contracts for the evolution-target overview endpoints."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.db.crud.evolution_targets import EvolutionObjectType
from app.service.identity.schemas import IdentityModel
from app.service.overview.schemas import OverviewWindow, TrendGrain

TargetState = Literal["attributed", "nonTarget", "unanalyzed"]
"""The closed three-state vocabulary of one potential case under one version."""

TARGET_STATES: tuple[TargetState, ...] = ("attributed", "nonTarget", "unanalyzed")
"""Every state in display order; empty filters mean this full set."""


class TargetOverviewSummary(IdentityModel):
    """Totals across every enabled target in the workspace and the window."""

    targets: int = Field(ge=0)
    sessions: int = Field(
        ge=0,
        description=(
            "Sum of each target's associated Session count; a Session that contains "
            "several targets is counted once per target."
        ),
    )
    potential: int = Field(ge=0)
    attributed: int = Field(ge=0)
    non_target: int = Field(
        validation_alias="nonTarget",
        serialization_alias="nonTarget",
        ge=0,
    )
    unanalyzed: int = Field(ge=0)


class TargetOverviewItem(IdentityModel):
    """One target's potential cases and their three-state attribution split.

    ``potential`` counts one row per ``(badCaseId, targetVersion)`` pair, so the
    same bad case may contribute once for each version it is potential under;
    ``attributed + nonTarget + unanalyzed`` therefore always equals ``potential``.
    """

    target_id: str = Field(max_length=36)
    object_type: EvolutionObjectType
    object_name: str = Field(min_length=1, max_length=128)
    versions: list[str] = Field(
        description=(
            "Versions this target was observed at inside the window, plus its "
            "configured defaultRef, ordered by descending natural version."
        ),
    )
    sessions: int = Field(ge=0)
    potential: int = Field(ge=0)
    attributed: int = Field(ge=0)
    non_target: int = Field(
        validation_alias="nonTarget",
        serialization_alias="nonTarget",
        ge=0,
    )
    unanalyzed: int = Field(ge=0)
    evolvable: int = Field(
        ge=0,
        description="Attributed plus unanalyzed potential rows; the list sort key.",
    )


class TargetOverviewListResponse(IdentityModel):
    """One target page plus the workspace-wide summary."""

    summary: TargetOverviewSummary
    items: list[TargetOverviewItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class TargetTrendByTarget(IdentityModel):
    """One target's contribution to one trend bucket."""

    target_id: str = Field(max_length=36)
    object_type: EvolutionObjectType
    object_name: str = Field(min_length=1, max_length=128)
    attributed: int = Field(ge=0)
    non_target: int = Field(
        validation_alias="nonTarget",
        serialization_alias="nonTarget",
        ge=0,
    )
    unanalyzed: int = Field(ge=0)


class TargetTrendBucket(IdentityModel):
    """One continuous, zero-filled target trend bucket."""

    bucket: date
    label: str = Field(description="MM-DD for day/week buckets, YYYY-MM for month buckets.")
    attributed: int = Field(ge=0)
    non_target: int = Field(
        validation_alias="nonTarget",
        serialization_alias="nonTarget",
        ge=0,
    )
    unanalyzed: int = Field(ge=0)
    by_target: list[TargetTrendByTarget]


class TargetTrendMeta(IdentityModel):
    """The bucket-time policy the response actually applied."""

    bucket_policy: str = Field(
        description=(
            "attributed and nonTarget rows use probe updatedAt; unanalyzed rows use "
            "the bad case createdAt."
        ),
    )


class TargetTrendResponse(IdentityModel):
    """The continuous target trend series and its effective grain."""

    window: OverviewWindow
    grain: TrendGrain
    buckets: list[TargetTrendBucket]
    meta: TargetTrendMeta


class TargetCaseItem(IdentityModel):
    """One potential case under one target version, with its attribution state."""

    bad_case_id: str = Field(max_length=64)
    object_type: EvolutionObjectType
    object_name: str = Field(min_length=1, max_length=128)
    object_version: str = Field(max_length=128)
    source: str = Field(description="The object name the bad case was reported against.")
    state: TargetState
    bad_case_type: Literal["self", "discovery"]
    title: str
    created_at: datetime
    session_id: str = Field(max_length=36)
    attribution_id: str | None = Field(
        default=None,
        max_length=64,
        description="The probe id of the newest attribution for this target version.",
    )
    category: Literal["model", "prompt", "error"] | None = Field(
        default=None,
        description="Attribution category; only present for the attributed state.",
    )


class TargetCaseListResponse(IdentityModel):
    """One filtered page of potential cases plus its authoritative total."""

    items: list[TargetCaseItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class TargetDetailTarget(IdentityModel):
    """The configured target a detail card is about and every version it has."""

    target_id: str = Field(max_length=36)
    object_type: EvolutionObjectType
    object_name: str = Field(min_length=1, max_length=128)
    default_ref: str = Field(max_length=128)
    versions: list[str]


class TargetDetailStats(IdentityModel):
    """The detail card's four counters."""

    sessions: int = Field(ge=0)
    potential: int = Field(ge=0)
    distinct_cases: int = Field(ge=0)
    versions: int = Field(ge=0)


class TargetDetailVersion(IdentityModel):
    """One version's contribution inside the selected detail scope."""

    version: str = Field(max_length=128)
    potential: int = Field(ge=0)
    attributed: int = Field(ge=0)
    non_target: int = Field(
        validation_alias="nonTarget",
        serialization_alias="nonTarget",
        ge=0,
    )
    unanalyzed: int = Field(ge=0)


class TargetDetailSource(IdentityModel):
    """One reported source and its potential cases inside the selected scope."""

    source: str
    total: int = Field(ge=0)
    distinct_cases: int = Field(ge=0)


class TargetDetailResponse(IdentityModel):
    """One target's version and source analysis under an independent filter."""

    target: TargetDetailTarget
    stats: TargetDetailStats
    by_version: list[TargetDetailVersion]
    by_source: list[TargetDetailSource]
