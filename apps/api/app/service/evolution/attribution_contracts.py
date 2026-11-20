"""Versioned attribution report and immutable execution-manifest contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.service.identity.schemas import IdentityModel

REPORT_SCHEMA_VERSION: Literal["probe-report/v2"] = "probe-report/v2"
EXECUTION_MANIFEST_VERSION: Literal["attribution-execution/v1"] = "attribution-execution/v1"
DEFAULT_SKILL_KEY = "platform-default"
DEFAULT_SKILL_REVISION = "builtin-v1"
NO_MODEL_FINGERPRINT = "none"

AttributionConclusion = Literal["attributed", "non_target", "inconclusive"]
AttributionCategory = Literal["model", "prompt", "error", "flow", "context"]


class AttributionTargetRef(IdentityModel):
    """The exact evolution object revision evaluated by one report."""

    object_type: Literal["skill", "agent", "knowledge"]
    object_name: str = Field(min_length=1, max_length=128)
    object_version: str | None = Field(default=None, max_length=96)


class AttributionPoint(IdentityModel):
    """A bounded introduction or detection point in the selected Session."""

    occurred_at: datetime | None = None
    label: str = Field(min_length=1, max_length=64)


class AttributionEvidence(IdentityModel):
    """One structured, non-raw evidence reference used by the analysis."""

    kind: Literal["bad_case", "knowledge", "trace", "warning"]
    summary: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=512)


class AttributionAnalysis(IdentityModel):
    """Human-readable summary and detailed reasoning produced by the engine."""

    summary: str
    reasoning: str


class AttributionReportV2(IdentityModel):
    """Structured V2 payload stored beside legacy report text columns."""

    source_report: dict[str, object] | None = None
    schema_version: Literal["probe-report/v2"] = REPORT_SCHEMA_VERSION
    target: AttributionTargetRef
    conclusion: AttributionConclusion
    category: AttributionCategory | None = None
    introduction_point: AttributionPoint | None = None
    detection_point: AttributionPoint | None = None
    evidence: list[AttributionEvidence] = Field(default_factory=list)
    analysis: AttributionAnalysis
    suggestion_clues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AttributionSkillRevision(IdentityModel):
    """Resolved Skill identity that can invalidate cached attribution output."""

    key: str = Field(min_length=1, max_length=128)
    revision: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(min_length=1, max_length=128)


class AttributionExecutionManifest(IdentityModel):
    """Immutable inputs that determine one attribution report and cache identity."""

    manifest_version: Literal["attribution-execution/v1"] = EXECUTION_MANIFEST_VERSION
    workspace_id: str = Field(min_length=1, max_length=36)
    bad_case_id: str = Field(min_length=1, max_length=64)
    target: AttributionTargetRef
    policy_version: str = Field(min_length=1, max_length=16)
    engine: str = Field(min_length=1, max_length=64)
    skill: AttributionSkillRevision
    model_config_fingerprint: str = Field(min_length=1, max_length=128)
    context_snapshot_hash: str = Field(min_length=1, max_length=128)
    output_schema_version: Literal["probe-report/v2"] = REPORT_SCHEMA_VERSION

    @property
    def content_hash(self) -> str:
        """Return the canonical cache identity for this exact manifest."""
        return canonical_json_hash(self.model_dump(mode="json", by_alias=True))


def canonical_json_hash(value: object) -> str:
    """Hash one JSON-compatible value with stable keys and compact separators."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def context_snapshot_hash(
    *,
    session_id: str,
    bad_case_id: str,
    hit_reason: str,
    order_state: str,
    object_trigger_at: datetime | None,
    case_trigger_at: datetime | None,
    evidence_fingerprint: Mapping[str, object] | Sequence[object] | None = None,
) -> str:
    """Fingerprint the bounded candidate context without storing a raw trace."""
    return canonical_json_hash(
        {
            "sessionId": session_id,
            "badCaseId": bad_case_id,
            "hitReason": hit_reason,
            "orderState": order_state,
            "objectTriggerAt": (
                object_trigger_at.isoformat() if object_trigger_at is not None else None
            ),
            "caseTriggerAt": case_trigger_at.isoformat() if case_trigger_at is not None else None,
            "evidence": evidence_fingerprint,
        },
    )


def default_skill_revision(engine: str) -> AttributionSkillRevision:
    """Describe the built-in engine as the platform default pluggable Skill."""
    content_hash = canonical_json_hash({"engine": engine, "revision": DEFAULT_SKILL_REVISION})
    return AttributionSkillRevision(
        key=DEFAULT_SKILL_KEY,
        revision=DEFAULT_SKILL_REVISION,
        content_hash=content_hash,
    )


def default_execution_manifest(
    *,
    workspace_id: str,
    bad_case_id: str,
    target_type: Literal["skill", "agent", "knowledge"],
    target_name: str,
    target_version: str | None,
    policy_version: str,
    engine: str,
    session_id: str,
    hit_reason: str,
    order_state: str,
    object_trigger_at: datetime | None,
    case_trigger_at: datetime | None,
    skill_key: str | None = None,
    skill_revision: str | None = None,
    skill_content_hash: str | None = None,
    prepared_context_snapshot_hash: str | None = None,
    model_fingerprint: str = NO_MODEL_FINGERPRINT,
) -> AttributionExecutionManifest:
    """Build a manifest from candidate coordinates and a frozen Skill snapshot."""
    skill = (
        AttributionSkillRevision(
            key=skill_key,
            revision=skill_revision,
            content_hash=skill_content_hash,
        )
        if skill_key and skill_revision and skill_content_hash
        else default_skill_revision(engine)
    )
    return AttributionExecutionManifest(
        workspace_id=workspace_id,
        bad_case_id=bad_case_id,
        target=AttributionTargetRef(
            object_type=target_type,
            object_name=target_name,
            object_version=target_version,
        ),
        policy_version=policy_version,
        engine=engine,
        skill=skill,
        model_config_fingerprint=model_fingerprint,
        context_snapshot_hash=(
            prepared_context_snapshot_hash
            or context_snapshot_hash(
                session_id=session_id,
                bad_case_id=bad_case_id,
                hit_reason=hit_reason,
                order_state=order_state,
                object_trigger_at=object_trigger_at,
                case_trigger_at=case_trigger_at,
            )
        ),
    )


__all__ = [
    "DEFAULT_SKILL_KEY",
    "DEFAULT_SKILL_REVISION",
    "EXECUTION_MANIFEST_VERSION",
    "NO_MODEL_FINGERPRINT",
    "REPORT_SCHEMA_VERSION",
    "AttributionAnalysis",
    "AttributionCategory",
    "AttributionConclusion",
    "AttributionEvidence",
    "AttributionExecutionManifest",
    "AttributionPoint",
    "AttributionReportV2",
    "AttributionSkillRevision",
    "AttributionTargetRef",
    "canonical_json_hash",
    "context_snapshot_hash",
    "default_execution_manifest",
    "default_skill_revision",
]
