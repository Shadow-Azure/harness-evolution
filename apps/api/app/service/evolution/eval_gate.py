"""Platform-neutral baseline gate for SkillOpt-style evolution decisions."""

# ruff: noqa: RUF001

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from app.service.evolution.engine.contracts import (
    EvalDirection,
    EvalMeasurement,
    EvalResult,
)


@dataclass(frozen=True, slots=True)
class EvalGateDecision:
    """One candidate-versus-baseline decision and its persisted result."""

    accepted: bool
    reason: str
    result: EvalResult
    baseline_score: float
    baseline_label: str


def gate_measurement(
    measurement: EvalMeasurement,
    *,
    baseline_score: float,
    baseline_label: str,
) -> EvalGateDecision:
    """Accept only a strict improvement over the active baseline.

    Ties always reject. ``direction`` comes from the platform metric item, so
    higher-is-better and lower-is-better metrics share one rule.
    """
    baseline = _finite_score(baseline_score, "baseline")
    accepted = strictly_better(
        measurement.candidate_score,
        baseline,
        measurement.direction,
    )
    result = EvalResult(
        current_score=baseline,
        candidate_score=measurement.candidate_score,
        external_verdict="accept" if accepted else "reject",
        metrics=measurement.metrics,
        direction=measurement.direction,
        primary_metric_key=measurement.primary_metric_key,
    )
    return EvalGateDecision(
        accepted=accepted,
        reason=decision_sentence(result, accepted=accepted),
        result=result,
        baseline_score=baseline,
        baseline_label=baseline_label,
    )


def strictly_better(
    candidate: float,
    baseline: float,
    direction: EvalDirection,
) -> bool:
    """Compare one candidate against its baseline under the metric direction."""
    if direction == "higher_is_better":
        return candidate > baseline
    return candidate < baseline


def decision_sentence(result: EvalResult, *, accepted: bool) -> str:
    """Translate one gated score comparison into one human-readable reason."""
    delta = result.candidate_score - result.current_score
    if math.isclose(delta, 0.0):
        relation = "等于"
    elif delta > 0:
        relation = "高于"
    else:
        relation = "低于"
    verdict = "接纳" if accepted else "拒绝"
    direction = "更高更优" if result.direction == "higher_is_better" else "更低更优"
    metric = result.primary_metric_key or _primary_metric_key(result.metrics)
    metric_text = f"主指标 {metric} 的" if metric else "主指标的"
    return (
        f"候选分 {result.candidate_score:.1f} {relation}基线 "
        f"{result.current_score:.1f}（{delta:+.1f}），"
        f"按{metric_text}{direction}规则{verdict}"
    )


def _primary_metric_key(
    metrics: tuple[Mapping[str, object], ...],
) -> str | None:
    """Read the primary metric key from the persisted result items."""
    for item in metrics:
        key = item.get("metric_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


def _finite_score(value: object, label: str) -> float:
    """Reject a non-numeric or non-finite baseline before persisting it."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} score must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{label} score must be finite")
    return float(value)


__all__ = [
    "EvalGateDecision",
    "decision_sentence",
    "gate_measurement",
    "strictly_better",
]
