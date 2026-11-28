"""Target-owned source rules and reporting-source read contracts."""

import hashlib
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.service.identity.schemas import IdentityModel

SourceKind = Literal["skill", "agent"]
ReportType = Literal["self", "discovery"]


class SourceRule(IdentityModel):
    kind: SourceKind
    name: str = Field(min_length=1, max_length=128)
    types: list[ReportType] = Field(min_length=1, max_length=2)
    relation: Literal["any", "before", "after"]


class CandidatePolicy(IdentityModel):
    mode: Literal["default", "combined", "custom"] = "default"
    rules: list[SourceRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_rules(self) -> Self:
        if (self.mode == "default") != (not self.rules):
            raise ValueError("custom modes require sources and default mode takes none")
        return self


def policy_version(policy: CandidatePolicy | None) -> str:
    """Stable 16-character identity for persisted policy snapshots and cache keys."""
    if policy is None or policy.mode == "default":
        return "v1"
    return hashlib.sha256(policy.model_dump_json().encode()).hexdigest()[:16]


class SourceCount(IdentityModel):
    kind: SourceKind
    name: str
    self_count: int
    discovery_count: int


class SourceReport(IdentityModel):
    id: str
    title: str
    report_type: ReportType
    label: str | None
    created_at: datetime


class SourceReportPage(IdentityModel):
    items: list[SourceReport]
    labels: list[str | None]
    total: int
    source_total: int
