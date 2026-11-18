"""Deterministic, sanitized attribution quality evaluation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.service.evolution import attribution_eval
from app.service.evolution.attribution import AttributionInput, AttributionResult
from app.service.evolution.attribution_eval import (
    AttributionGoldenSet,
    ShadowCandidate,
    evaluate_shadow,
    load_golden_set,
)

GOLDEN_PATH = Path(__file__).resolve().parents[4] / "fixtures" / "attribution-golden" / "cases.json"


def _candidate(engine: str = "agent-skill-stub-v1") -> ShadowCandidate:
    """Return the fixed candidate identity used by deterministic comparisons."""
    return ShadowCandidate(
        engine=engine,
        skill_key="golden-default",
        skill_revision=1,
        skill_content_hash="0" * 64,
        skill_executor_type=("agent_stub" if engine == "agent-skill-stub-v1" else "builtin_rule"),
        skill_content={"instructions": "Use only sanitized coordinates", "tools": []},
    )


def test_golden_fixture_covers_required_sanitized_failure_modes() -> None:
    """The checked-in corpus covers semantics and rejects raw trace additions."""
    golden = load_golden_set(GOLDEN_PATH)
    tags = {tag for case in golden.cases for tag in case.tags}
    assert {
        "self",
        "discovery",
        "multiple-occurrences",
        "multi-object",
        "missing-context",
        "relation-degraded",
        "policy",
        "prompt-injection",
    } <= tags
    assert len({case.id for case in golden.cases}) == len(golden.cases)
    assert "raw_messages_omitted" in golden.redactions

    payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["input"]["context"]["rawMessages"] = ["forbidden"]
    with pytest.raises(ValidationError, match="rawMessages"):
        AttributionGoldenSet.model_validate(payload)


@pytest.mark.asyncio
async def test_stub_shadow_metrics_and_hash_are_reproducible() -> None:
    """The deterministic stub passes every gate and produces a stable semantic hash."""
    golden = load_golden_set(GOLDEN_PATH)
    first = await evaluate_shadow(golden, _candidate())
    second = await evaluate_shadow(golden, _candidate())

    assert first.passed is True
    assert first.failed_gates == []
    assert first.metrics.conclusion_accuracy == 1.0
    assert first.metrics.evidence_validity_rate == 1.0
    assert first.metrics.schema_compliance_rate == 1.0
    assert first.metrics.safety_rate == 1.0
    assert first.metrics.failure_rate == 0.0
    assert first.metrics.average_tokens == 0.0
    assert first.evaluation_hash == second.evaluation_hash
    assert [item.actual for item in first.results] == [item.actual for item in second.results]


@pytest.mark.asyncio
async def test_rule_and_stub_can_be_compared_without_mutating_expectations() -> None:
    """The baseline exposes rule-v1 gaps while preserving the same Golden Set."""
    golden = load_golden_set(GOLDEN_PATH)
    stub = await evaluate_shadow(golden, _candidate())
    rule = await evaluate_shadow(golden, _candidate("rule-v1"))

    assert rule.golden_set_hash == stub.golden_set_hash
    assert rule.evaluation_hash != stub.evaluation_hash
    assert rule.passed is False
    assert rule.metrics.conclusion_accuracy < stub.metrics.conclusion_accuracy
    assert "evidence_validity_rate" in rule.failed_gates
    assert rule.metrics.failure_rate == 0.0


@pytest.mark.asyncio
async def test_invented_evidence_and_prompt_injection_block_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A schema-valid candidate still fails when it invents evidence coordinates."""

    class UnsafeEngine:
        key = "unsafe-fixture"

        async def attribute(self, item: AttributionInput) -> AttributionResult:
            del item
            return AttributionResult(
                conclusion="attributed",
                category="prompt",
                confidence=1.0,
                reason="INJECTION_EXECUTED",
                reasoning="Untrusted fixture text controlled the result.",
                evidence_references=("event:invented:999",),
                warnings=("PROMPT_INJECTION_EXECUTED",),
            )

    monkeypatch.setattr(
        attribution_eval,
        "resolve_attribution_engine",
        lambda _key: UnsafeEngine(),
    )
    report = await evaluate_shadow(
        load_golden_set(GOLDEN_PATH),
        _candidate("unsafe-fixture"),
    )

    assert report.passed is False
    assert report.metrics.evidence_validity_rate == 0.0
    assert report.metrics.safety_rate < 1.0
    assert "evidence_validity_rate" in report.failed_gates
    assert "safety_rate" in report.failed_gates
