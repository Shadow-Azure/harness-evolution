"""Platform-neutral baseline gate unit contract."""

from __future__ import annotations

import pytest

from app.service.evolution.engine.contracts import (
    EvalDirection,
    EvalMeasurement,
    EvalResult,
)
from app.service.evolution.eval_gate import (
    decision_sentence,
    gate_measurement,
    strictly_better,
)


def _measurement(
    score: float,
    direction: EvalDirection = "higher_is_better",
) -> EvalMeasurement:
    """Build one measurement with the SWE-bench primary metric."""
    return EvalMeasurement(
        candidate_score=score,
        primary_metric_key="resolved_rate",
        direction=direction,
        metrics=(
            {
                "metric_key": "resolved_rate",
                "value": score,
                "direction": direction,
            },
        ),
    )


def test_higher_is_better_requires_a_strict_improvement() -> None:
    """A tie rejects; one point above the baseline accepts."""
    tie = gate_measurement(
        _measurement(80.0),
        baseline_score=80.0,
        baseline_label="validation baseline",
    )
    better = gate_measurement(
        _measurement(80.1),
        baseline_score=80.0,
        baseline_label="validation baseline",
    )

    assert tie.accepted is False
    assert tie.result.external_verdict == "reject"
    assert better.accepted is True
    assert better.result.external_verdict == "accept"
    assert better.result.current_score == 80.0
    assert better.result.candidate_score == 80.1


def test_lower_is_better_flips_the_comparison() -> None:
    """The same strict rule compares a lower-is-better metric in reverse."""
    better = gate_measurement(
        _measurement(0.4, "lower_is_better"),
        baseline_score=0.5,
        baseline_label="validation baseline",
    )
    tie = gate_measurement(
        _measurement(0.5, "lower_is_better"),
        baseline_score=0.5,
        baseline_label="validation baseline",
    )

    assert strictly_better(0.4, 0.5, "lower_is_better") is True
    assert strictly_better(0.6, 0.5, "lower_is_better") is False
    assert better.accepted is True
    assert tie.accepted is False


def test_decision_sentence_names_the_metric_and_rule() -> None:
    """The accepted commit message and event carry the real decision rule."""
    decision = gate_measurement(
        _measurement(86.0),
        baseline_score=80.0,
        baseline_label="validation baseline",
    )

    assert "候选分 86.0 高于基线 80.0" in decision.reason
    assert "主指标 resolved_rate" in decision.reason
    assert "更高更优规则接纳" in decision.reason


def test_gated_result_round_trips_with_its_direction() -> None:
    """Persisting a lower-is-better result keeps the direction for apply/final."""
    result = EvalResult(
        current_score=0.5,
        candidate_score=0.4,
        external_verdict="accept",
        direction="lower_is_better",
    )

    restored = EvalResult.from_payload(result.to_payload())

    assert restored.direction == "lower_is_better"
    assert restored.external_verdict == "accept"


def test_non_finite_baselines_are_rejected() -> None:
    """A NaN baseline cannot silently accept or reject a candidate."""
    with pytest.raises(ValueError, match="finite"):
        gate_measurement(
            _measurement(80.0),
            baseline_score=float("nan"),
            baseline_label="validation baseline",
        )


def test_decision_sentence_still_translates_legacy_results() -> None:
    """Legacy external-verdict results keep a human-readable sentence."""
    sentence = decision_sentence(
        EvalResult(
            current_score=90.0,
            candidate_score=80.0,
            external_verdict="accept",
        ),
        accepted=True,
    )

    assert "低于基线" in sentence
    assert "接纳" in sentence
