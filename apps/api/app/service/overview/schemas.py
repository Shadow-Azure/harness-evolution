"""Public contracts for the workspace overview summary, trend, sources, and list."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.service.bad_cases.session_status import BadCaseTraceStatus
from app.service.identity.schemas import IdentityModel

BadCaseType = Literal["self", "discovery"]
TrendGrain = Literal["day", "week", "month"]


class OverviewWindow(IdentityModel):
    """The inclusive Asia/Shanghai window the response was computed over."""

    date_from: date = Field(
        validation_alias="from",
        serialization_alias="from",
        description="Inclusive Asia/Shanghai start date.",
    )
    date_to: date = Field(
        validation_alias="to",
        serialization_alias="to",
        description="Inclusive Asia/Shanghai end date.",
    )


class OverviewTotals(IdentityModel):
    """Summary counters; ``quota``/``used`` ignore the window and every filter."""

    bad_cases: int = Field(ge=0)
    self_cases: int = Field(validation_alias="self", serialization_alias="self", ge=0)
    discovery_cases: int = Field(
        validation_alias="discovery",
        serialization_alias="discovery",
        ge=0,
    )
    sessions: int = Field(
        ge=0,
        description=(
            "Distinct root sessions reported in the window, including roots without a "
            "normalized trace. This is not the Session page total; pending roots are "
            "counted here and pendingSessions is a separate Session page figure."
        ),
    )
    sources: int = Field(ge=0, description="Distinct object names in the window.")
    quota: int = Field(ge=0, description="Workspace bad-case quota; independent of the window.")
    used: int = Field(
        ge=0,
        description="Every bad case owned by the workspace; independent of the window.",
    )


class OverviewSummary(IdentityModel):
    """One workspace overview header: window, totals, and object options."""

    window: OverviewWindow
    totals: OverviewTotals
    objects: list[str] = Field(
        description=(
            "Distinct object names in the window, ignoring the object filter, "
            "sorted case-insensitively by name."
        ),
    )


class TrendBucket(IdentityModel):
    """One continuous, zero-filled trend bucket."""

    bucket: date
    label: str = Field(description="MM-DD for day/week buckets, YYYY-MM for month buckets.")
    self_cases: int = Field(validation_alias="self", serialization_alias="self", ge=0)
    discovery_cases: int = Field(
        validation_alias="discovery",
        serialization_alias="discovery",
        ge=0,
    )
    total: int = Field(ge=0)


class TrendResponse(IdentityModel):
    """The continuous trend series plus the grain actually used."""

    window: OverviewWindow
    grain: TrendGrain = Field(
        description=(
            "Effective grain: a day request longer than 92 days is served as week, "
            "and the response always states the grain its buckets use."
        ),
    )
    buckets: list[TrendBucket]


class SourceRow(IdentityModel):
    """One object's share of the window, split by bad-case type."""

    object: str
    total: int = Field(ge=0)
    self_cases: int = Field(validation_alias="self", serialization_alias="self", ge=0)
    discovery_cases: int = Field(
        validation_alias="discovery",
        serialization_alias="discovery",
        ge=0,
    )
    sessions: int = Field(ge=0)


class SourceListResponse(IdentityModel):
    """Source distribution ordered by total descending, then object name."""

    items: list[SourceRow]


class BadCaseListItem(IdentityModel):
    """One row of the filtered overview list."""

    bad_case_id: str
    session_id: str
    object_name: str
    bad_case_type: BadCaseType
    bad_case_type_label: str
    title: str
    trigger_at: datetime = Field(
        description=(
            "Trigger timestamp. Until object trigger coordinates land in m9-04 this "
            "temporarily equals createdAt."
        ),
    )
    trigger_line: int | None = Field(
        ge=0,
        description=(
            "1-based log line of the report's trigger point in the root Session (the same "
            "coordinate as the Session tree event line), or "
            "null when the report did not carry one. It is never derived from "
            "createdAt or an event index; the overview and error-detail flow share "
            "this trigger coordinate."
        ),
    )
    created_at: datetime
    sync_status: BadCaseTraceStatus = Field(
        description=(
            "Derived trace readiness: ready, pending, syncing, failed, or unavailable. "
            "The case itself exists whenever it appears in this list."
        ),
    )
    session_ready: bool = Field(
        description="Whether the normalized Session projection can already be read.",
    )
    last_error: str | None = Field(
        description="Stable root-sync failure code while the trace is not ready.",
    )
    retryable: bool = Field(
        description=(
            "Whether automatic sync can still make progress. Deterministic failures "
            "report false until their source configuration changes."
        ),
    )
    next_retry_at: datetime | None = Field(
        description="Next scheduled automatic retry, when one is planned.",
    )
    attribution_count: int = Field(
        ge=0,
        description=(
            "Distinct (probeType, probeObject, objectVersion) attributions reached through "
            "bad_case_analysis; the canonical definition is 06 §4.2.1."
        ),
    )


class OverviewBadCaseListResponse(IdentityModel):
    """One filtered page plus its authoritative total."""

    items: list[BadCaseListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
