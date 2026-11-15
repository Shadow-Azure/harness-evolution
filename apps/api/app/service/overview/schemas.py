"""Public contracts for the workspace overview summary, trend, sources, and list."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

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
    sessions: int = Field(ge=0, description="Distinct root sessions in the window.")
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
    created_at: datetime
    attribution_count: int = Field(
        ge=0,
        description="Distinct (probe type, probe object, object version) attributions.",
    )


class OverviewBadCaseListResponse(IdentityModel):
    """One filtered page plus its authoritative total."""

    items: list[BadCaseListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
