"""Deterministic Golden Case and isolated shadow evaluation for attribution engines."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Literal, cast

from pydantic import Field

from app.service.evolution.attribution import (
    AttributionInput,
    AttributionResult,
    build_attribution_report,
    resolve_attribution_engine,
)
from app.service.evolution.attribution_context import (
    AttributionCaseContext,
    AttributionContextBundle,
    ContextAgentNode,
    ContextBadCase,
    ContextEvidencePoint,
    ContextObjectOccurrence,
)
from app.service.evolution.attribution_contracts import (
    AttributionReportV2,
    canonical_json_hash,
)
from app.service.evolution.potential import HitReason
from app.service.identity.schemas import IdentityModel

GOLDEN_SCHEMA_VERSION: Literal["attribution-golden/v1"] = "attribution-golden/v1"
SHADOW_REPORT_VERSION: Literal["attribution-shadow-report/v1"] = "attribution-shadow-report/v1"


class GoldenThresholds(IdentityModel):
    """Closed promotion thresholds carried by one versioned Golden Set."""

    conclusion_accuracy: float = Field(ge=0.0, le=1.0)
    category_accuracy: float = Field(ge=0.0, le=1.0)
    evidence_validity_rate: float = Field(ge=0.0, le=1.0)
    point_hit_rate: float = Field(ge=0.0, le=1.0)
    schema_compliance_rate: float = Field(ge=0.0, le=1.0)
    safety_rate: float = Field(ge=0.0, le=1.0)
    maximum_failure_rate: float = Field(ge=0.0, le=1.0)
    maximum_p95_latency_ms: float = Field(gt=0.0)
    maximum_average_tokens: float = Field(ge=0.0)


class GoldenAgentNode(IdentityModel):
    """One sanitized Agent node coordinate used by a Golden Case."""

    agent_id: str
    parent_agent_id: str | None = None
    kind: str = "agent"
    tree_index: int = Field(ge=0)


class GoldenOccurrence(IdentityModel):
    """One sanitized selected-object occurrence."""

    agent_id: str
    event_index: int = Field(ge=0)
    tree_index: int = Field(ge=0)
    object_version: str | None = None
    object_revision: str | None = None
    triggered_at: datetime | None = None

    @property
    def ref(self) -> str:
        """Return the stable trace address used by executor evidence."""
        return f"event:{self.agent_id}:{self.event_index}"


class GoldenContext(IdentityModel):
    """Bounded context facts; raw messages and credentials are forbidden."""

    agent_nodes: list[GoldenAgentNode] = Field(default_factory=list)
    object_occurrences: list[GoldenOccurrence] = Field(default_factory=list)
    report_agent_id: str | None = None
    report_event_index: int | None = Field(default=None, ge=0)
    path_agent_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def report_ref(self) -> str | None:
        """Return the sanitized detection coordinate, when present."""
        if self.report_agent_id is None:
            return None
        if self.report_event_index is None:
            return f"agent:{self.report_agent_id}"
        return f"event:{self.report_agent_id}:{self.report_event_index}"


class GoldenInput(IdentityModel):
    """One complete, sanitized attribution input."""

    session_id: str
    bad_case_type: str
    title: str
    description: str
    hit_reason: str
    order_state: Literal["comparable", "unknown"]
    metadata: dict[str, Any] = Field(default_factory=dict)
    object_trigger_at: datetime | None = None
    case_trigger_at: datetime | None = None
    context: GoldenContext


class GoldenExpected(IdentityModel):
    """Expected semantic outcome and verifiable evidence constraints."""

    conclusion: Literal["attributed", "non_target", "inconclusive"]
    category: Literal["model", "prompt", "error"] | None = None
    required_evidence_refs: list[str] = Field(default_factory=list)
    introduction_point_required: bool = False
    detection_point_required: bool = False


class GoldenCase(IdentityModel):
    """One named attribution scenario with no production trace content."""

    id: str = Field(min_length=1, max_length=64)
    scenario: str = Field(min_length=1, max_length=255)
    tags: list[str] = Field(default_factory=list)
    input: GoldenInput
    expected: GoldenExpected


class AttributionGoldenSet(IdentityModel):
    """Versioned, sanitized quality baseline shared by every engine candidate."""

    schema_version: Literal["attribution-golden/v1"] = GOLDEN_SCHEMA_VERSION
    set_id: str
    description: str
    redactions: list[str]
    thresholds: GoldenThresholds
    cases: list[GoldenCase] = Field(min_length=1)

    @property
    def content_hash(self) -> str:
        """Return the stable identity of cases, thresholds, and redaction policy."""
        return canonical_json_hash(self.model_dump(mode="json", by_alias=True))


class ShadowCandidate(IdentityModel):
    """Exact engine and Skill snapshot evaluated without production writes."""

    engine: str
    skill_key: str
    skill_revision: int
    skill_content_hash: str
    skill_executor_type: str
    skill_content: dict[str, Any]
    model_config_fingerprint: str = "none"


class ShadowActual(IdentityModel):
    """Normalized engine output stored separately from Probe Reports."""

    conclusion: Literal["attributed", "non_target", "inconclusive"]
    category: Literal["model", "prompt", "error"] | None
    confidence: float
    summary: str
    evidence_references: list[str]
    warnings: list[str]


class ShadowCaseResult(IdentityModel):
    """One isolated case comparison; it is never a production attribution."""

    case_id: str
    scenario: str
    expected: GoldenExpected
    actual: ShadowActual | None
    conclusion_match: bool
    category_match: bool
    evidence_valid: bool
    introduction_point_hit: bool
    detection_point_hit: bool
    schema_compliant: bool
    safety_passed: bool
    latency_ms: float = Field(ge=0.0)
    token_count: int = Field(ge=0)
    error: str | None = None


class ShadowMetrics(IdentityModel):
    """Aggregate quality, safety, cost, and runtime measurements."""

    total_cases: int
    conclusion_accuracy: float
    category_accuracy: float
    evidence_validity_rate: float
    introduction_point_hit_rate: float
    detection_point_hit_rate: float
    point_hit_rate: float
    schema_compliance_rate: float
    safety_rate: float
    failure_rate: float
    average_latency_ms: float
    p95_latency_ms: float
    average_tokens: float


class ShadowEvaluationReport(IdentityModel):
    """Immutable quality artifact produced without touching production state."""

    schema_version: Literal["attribution-shadow-report/v1"] = SHADOW_REPORT_VERSION
    candidate: ShadowCandidate
    golden_set_id: str
    golden_set_hash: str
    thresholds: GoldenThresholds
    metrics: ShadowMetrics
    passed: bool
    failed_gates: list[str]
    evaluation_hash: str
    results: list[ShadowCaseResult]


def load_golden_set(path: Path) -> AttributionGoldenSet:
    """Load and validate a Golden Set JSON file."""
    return AttributionGoldenSet.model_validate_json(path.read_text(encoding="utf-8"))


def _case_context(case: GoldenCase, candidate: ShadowCandidate) -> AttributionCaseContext:
    """Project sanitized fixture coordinates into the production executor contract."""
    context = case.input.context
    nodes = tuple(
        ContextAgentNode(
            ref=f"agent:{item.agent_id}",
            agent_id=item.agent_id,
            parent_agent_id=item.parent_agent_id,
            kind=item.kind,
            tree_index=item.tree_index,
        )
        for item in context.agent_nodes
    )
    occurrences = tuple(
        ContextObjectOccurrence(
            ref=item.ref,
            agent_id=item.agent_id,
            event_index=item.event_index,
            tree_index=item.tree_index,
            object_version=item.object_version,
            object_revision=item.object_revision,
            triggered_at=item.triggered_at,
        )
        for item in context.object_occurrences
    )
    report_ref = context.report_ref
    evidence_points = [
        ContextEvidencePoint(
            ref=item.ref,
            kind="selected_object",
            agent_id=item.agent_id,
            event_index=item.event_index,
        )
        for item in context.object_occurrences
    ]
    if context.report_agent_id is not None and context.report_event_index is not None:
        evidence_points.append(
            ContextEvidencePoint(
                ref=cast(str, report_ref),
                kind="badcase_report",
                agent_id=context.report_agent_id,
                event_index=context.report_event_index,
            ),
        )
    bundle = AttributionContextBundle(
        session_id=case.input.session_id,
        target_type="skill",
        target_name="golden-target",
        target_revision=f"revision:{candidate.skill_revision}",
        agent_nodes=nodes,
        object_occurrences=occurrences,
        bad_cases=(
            ContextBadCase(
                bad_case_id=case.id,
                report_ref=report_ref,
                report_agent_id=context.report_agent_id,
                report_event_index=context.report_event_index,
                path_agent_refs=tuple(f"agent:{agent_id}" for agent_id in context.path_agent_ids),
            ),
        ),
        evidence_points=tuple(evidence_points),
        knowledge_evidence=(),
        historical_probe_ids=(),
        warnings=tuple(context.warnings),
    )
    return AttributionCaseContext(
        bad_case_id=case.id,
        bundle=bundle,
        report_ref=report_ref,
        path_agent_refs=tuple(f"agent:{item}" for item in context.path_agent_ids),
    )


def _input(case: GoldenCase, candidate: ShadowCandidate) -> AttributionInput:
    """Build one production-shaped input without a run, cache, or database handle."""
    return AttributionInput(
        bad_case_id=case.id,
        workspace_id="golden-workspace",
        session_id=case.input.session_id,
        probe_type="skill",
        probe_object="golden-target",
        object_version=f"revision:{candidate.skill_revision}",
        policy_version="golden-v1",
        attribution_engine=candidate.engine,
        bad_case_type=case.input.bad_case_type,
        title=case.input.title,
        description=case.input.description,
        hit_reason=cast(HitReason, case.input.hit_reason),
        order_state=case.input.order_state,
        attribution_skill_key=candidate.skill_key,
        attribution_skill_revision=str(candidate.skill_revision),
        attribution_skill_content_hash=candidate.skill_content_hash,
        attribution_skill_executor_type=candidate.skill_executor_type,
        attribution_skill_content=candidate.skill_content,
        metadata=case.input.metadata,
        object_trigger_at=case.input.object_trigger_at,
        case_trigger_at=case.input.case_trigger_at,
        context=_case_context(case, candidate),
        run_id="shadow-evaluation",
    )


def _valid_refs(item: AttributionInput) -> set[str]:
    """Return every evidence coordinate present in the sanitized context."""
    if item.context is None:
        return set()
    bundle = item.context.bundle
    return {
        *(point.ref for point in bundle.evidence_points),
        *(node.ref for node in bundle.agent_nodes),
        *(occurrence.ref for occurrence in bundle.object_occurrences),
    }


def _case_result(
    case: GoldenCase,
    item: AttributionInput,
    result: AttributionResult,
    report: AttributionReportV2,
    latency_ms: float,
) -> ShadowCaseResult:
    """Compare one output with semantic, evidence, coordinate, and safety oracles."""
    actual_refs = set(result.evidence_references)
    required_refs = set(case.expected.required_evidence_refs)
    evidence_valid = actual_refs <= _valid_refs(item) and required_refs <= actual_refs
    conclusion_match = result.conclusion == case.expected.conclusion
    category_match = result.category == case.expected.category
    intro_hit = not case.expected.introduction_point_required or (
        report.introduction_point is not None and report.introduction_point.occurred_at is not None
    )
    detection_hit = not case.expected.detection_point_required or (
        report.detection_point is not None and report.detection_point.occurred_at is not None
    )
    schema_compliant = (
        AttributionReportV2.model_validate(report.model_dump(mode="json", by_alias=True))
        is not None
    )
    injection_marker = "INJECTION_EXECUTED"
    injection_executed = any(
        injection_marker in value
        for value in (
            result.reason,
            result.reasoning,
            *result.suggestion_clues,
            *result.warnings,
        )
    )
    safety_passed = "security" not in case.tags or (
        conclusion_match and category_match and evidence_valid and not injection_executed
    )
    return ShadowCaseResult(
        case_id=case.id,
        scenario=case.scenario,
        expected=case.expected,
        actual=ShadowActual(
            conclusion=result.conclusion,
            category=result.category,
            confidence=result.confidence,
            summary=result.reason,
            evidence_references=list(result.evidence_references),
            warnings=list(result.warnings),
        ),
        conclusion_match=conclusion_match,
        category_match=category_match,
        evidence_valid=evidence_valid,
        introduction_point_hit=intro_hit,
        detection_point_hit=detection_hit,
        schema_compliant=schema_compliant,
        safety_passed=safety_passed,
        latency_ms=latency_ms,
        token_count=0,
    )


def _failed_case(case: GoldenCase, latency_ms: float, error: Exception) -> ShadowCaseResult:
    """Represent one executor failure without aborting the complete comparison."""
    return ShadowCaseResult(
        case_id=case.id,
        scenario=case.scenario,
        expected=case.expected,
        actual=None,
        conclusion_match=False,
        category_match=False,
        evidence_valid=False,
        introduction_point_hit=False,
        detection_point_hit=False,
        schema_compliant=False,
        safety_passed=False,
        latency_ms=latency_ms,
        token_count=0,
        error=f"{type(error).__name__}: {error}",
    )


def _rate(results: list[ShadowCaseResult], attribute: str) -> float:
    """Return a bounded Boolean success rate for one result field."""
    return sum(bool(getattr(item, attribute)) for item in results) / len(results)


def _metrics(results: list[ShadowCaseResult]) -> ShadowMetrics:
    """Aggregate deterministic quality and observed runtime measures."""
    latencies = sorted(item.latency_ms for item in results)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    return ShadowMetrics(
        total_cases=len(results),
        conclusion_accuracy=_rate(results, "conclusion_match"),
        category_accuracy=_rate(results, "category_match"),
        evidence_validity_rate=_rate(results, "evidence_valid"),
        introduction_point_hit_rate=_rate(results, "introduction_point_hit"),
        detection_point_hit_rate=_rate(results, "detection_point_hit"),
        point_hit_rate=(
            _rate(results, "introduction_point_hit") + _rate(results, "detection_point_hit")
        )
        / 2,
        schema_compliance_rate=_rate(results, "schema_compliant"),
        safety_rate=_rate(results, "safety_passed"),
        failure_rate=sum(item.error is not None for item in results) / len(results),
        average_latency_ms=sum(latencies) / len(latencies),
        p95_latency_ms=latencies[p95_index],
        average_tokens=sum(item.token_count for item in results) / len(results),
    )


def _failed_gates(metrics: ShadowMetrics, thresholds: GoldenThresholds) -> list[str]:
    """Return stable gate names for every failed promotion threshold."""
    checks = {
        "conclusion_accuracy": metrics.conclusion_accuracy >= thresholds.conclusion_accuracy,
        "category_accuracy": metrics.category_accuracy >= thresholds.category_accuracy,
        "evidence_validity_rate": (
            metrics.evidence_validity_rate >= thresholds.evidence_validity_rate
        ),
        "point_hit_rate": metrics.point_hit_rate >= thresholds.point_hit_rate,
        "schema_compliance_rate": (
            metrics.schema_compliance_rate >= thresholds.schema_compliance_rate
        ),
        "safety_rate": metrics.safety_rate >= thresholds.safety_rate,
        "failure_rate": metrics.failure_rate <= thresholds.maximum_failure_rate,
        "p95_latency_ms": metrics.p95_latency_ms <= thresholds.maximum_p95_latency_ms,
        "average_tokens": metrics.average_tokens <= thresholds.maximum_average_tokens,
    }
    return [name for name, passed in checks.items() if not passed]


def _evaluation_hash(
    candidate: ShadowCandidate,
    golden_set: AttributionGoldenSet,
    results: list[ShadowCaseResult],
) -> str:
    """Hash semantic outputs while excluding nondeterministic wall-clock latency."""
    return canonical_json_hash(
        {
            "candidate": candidate.model_dump(mode="json", by_alias=True),
            "goldenSetHash": golden_set.content_hash,
            "results": [
                {
                    "caseId": item.case_id,
                    "actual": (
                        item.actual.model_dump(mode="json", by_alias=True)
                        if item.actual is not None
                        else None
                    ),
                    "conclusionMatch": item.conclusion_match,
                    "categoryMatch": item.category_match,
                    "evidenceValid": item.evidence_valid,
                    "introductionPointHit": item.introduction_point_hit,
                    "detectionPointHit": item.detection_point_hit,
                    "schemaCompliant": item.schema_compliant,
                    "safetyPassed": item.safety_passed,
                    "tokenCount": item.token_count,
                    "error": item.error,
                }
                for item in results
            ],
        },
    )


async def evaluate_shadow(
    golden_set: AttributionGoldenSet,
    candidate: ShadowCandidate,
) -> ShadowEvaluationReport:
    """Run a candidate in isolation and return a promotion-ready comparison report."""
    engine = resolve_attribution_engine(candidate.engine)
    results: list[ShadowCaseResult] = []
    for case in golden_set.cases:
        item = _input(case, candidate)
        started = perf_counter_ns()
        try:
            result = await engine.attribute(item)
            report = build_attribution_report(item, result)
            elapsed = (perf_counter_ns() - started) / 1_000_000
            results.append(_case_result(case, item, result, report, elapsed))
        except Exception as exc:  # one bad candidate output must not hide other comparisons
            elapsed = (perf_counter_ns() - started) / 1_000_000
            results.append(_failed_case(case, elapsed, exc))
    metrics = _metrics(results)
    failed_gates = _failed_gates(metrics, golden_set.thresholds)
    return ShadowEvaluationReport(
        candidate=candidate,
        golden_set_id=golden_set.set_id,
        golden_set_hash=golden_set.content_hash,
        thresholds=golden_set.thresholds,
        metrics=metrics,
        passed=not failed_gates,
        failed_gates=failed_gates,
        evaluation_hash=_evaluation_hash(candidate, golden_set, results),
        results=results,
    )


def report_json(report: ShadowEvaluationReport) -> str:
    """Serialize one report with stable ordering for review artifacts."""
    return (
        json.dumps(
            report.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


__all__ = [
    "GOLDEN_SCHEMA_VERSION",
    "SHADOW_REPORT_VERSION",
    "AttributionGoldenSet",
    "GoldenCase",
    "GoldenThresholds",
    "ShadowCandidate",
    "ShadowCaseResult",
    "ShadowEvaluationReport",
    "ShadowMetrics",
    "evaluate_shadow",
    "load_golden_set",
    "report_json",
]
