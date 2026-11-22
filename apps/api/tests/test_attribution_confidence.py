"""Deterministic evidence-completeness confidence for the rule-v1 engine."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.service.evolution.attribution import AttributionInput, RuleBasedEngine
from app.service.evolution.attribution_confidence import (
    LOW_CONFIDENCE_CLUSTER_GATE_ENABLED,
    LOW_CONFIDENCE_CLUSTER_THRESHOLD,
    EvidenceSignals,
    attribution_confidence,
    evidence_score,
    extract_signals,
    failure_signature,
    version_identity_forms,
)
from app.utils.time import SHANGHAI

OBJECT_TRIGGER = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
CASE_TRIGGER = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)


def attribution_input(
    *,
    hit_reason: str = "self_report",
    order_state: str = "comparable",
    bad_case_type: str = "self",
    title: str = "检索索引读取失败",
    description: str = "deep-research 读取索引时未校验快照字段",
    metadata: dict[str, object] | None = None,
    object_version: str | None = "tag:v2.0.0",
    case_object_type: str | None = "skill",
    case_object_name: str | None = "deep-research",
    case_object_version: str | None = "v2.0.0",
) -> AttributionInput:
    """Build one engine input whose default evidence names the target object/version."""
    return AttributionInput(
        bad_case_id="bc-confidence-a",
        workspace_id="ws-confidence",
        session_id="94000000-0000-4000-8000-000000000001",
        probe_type="skill",
        probe_object="deep-research",
        object_version=object_version,
        policy_version="v1",
        attribution_engine="rule-v1",
        bad_case_type=bad_case_type,
        title=title,
        description=description,
        metadata=metadata or {},
        hit_reason=hit_reason,  # type: ignore[arg-type]
        order_state=order_state,  # type: ignore[arg-type]
        object_trigger_at=OBJECT_TRIGGER,
        case_trigger_at=CASE_TRIGGER,
        case_object_type=case_object_type,
        case_object_name=case_object_name,
        case_object_version=case_object_version,
    )


def test_failure_signature_is_case_folded_and_blank_safe() -> None:
    """Object identity is compared case-insensitively, never as a partial value."""
    assert failure_signature(" Skill ", " Deep-Research ") == ("skill", "deep-research")
    assert failure_signature(None, "deep-research") is None
    assert failure_signature("skill", "   ") is None


def test_version_identity_forms_keep_prefix_free_variants() -> None:
    """A normalized tag and a normalized digest both accept their bare form."""
    assert version_identity_forms("tag:v2.0.0") == {"tag:v2.0.0", "v2.0.0"}
    assert version_identity_forms("digest:" + "a" * 64) == {
        "digest:" + "a" * 64,
        "a" * 64,
    }
    assert version_identity_forms(None) == frozenset()


def test_extract_signals_accepts_a_bare_body_hash_case_version() -> None:
    """A trace-persisted bare body hash still counts as direct version proof."""
    signals = extract_signals(
        order_state="comparable",
        case_object_type="skill",
        case_object_name="deep-research",
        case_object_version="a" * 64,
        probe_type="skill",
        probe_object="deep-research",
        target_revision="digest:" + "a" * 64,
    )

    assert signals == EvidenceSignals(
        order_comparable=True,
        failure_signature_match=True,
        version_proof=True,
    )
    assert signals.votes == 3


def test_extract_signals_marks_a_different_object_as_no_signature() -> None:
    """A failure that names another object cannot satisfy the signature check."""
    signals = extract_signals(
        order_state="comparable",
        case_object_type="agent",
        case_object_name="helper",
        case_object_version=None,
        probe_type="skill",
        probe_object="deep-research",
        target_revision="tag:v2.0.0",
    )

    assert signals.failure_signature_match is False
    assert signals.version_proof is False
    assert signals.votes == 1


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (EvidenceSignals(False, False, False), 0.3),
        (EvidenceSignals(True, False, False), 0.5),
        (EvidenceSignals(False, True, False), 0.5),
        (EvidenceSignals(True, True, False), 0.8),
        (EvidenceSignals(False, True, True), 0.8),
        (EvidenceSignals(True, True, True), 0.9),
        (EvidenceSignals(False, False, True), 0.2),
        (EvidenceSignals(True, False, True), 0.2),
    ],
)
def test_band_matrix_pins_every_vote_and_contradiction(
    signals: EvidenceSignals,
    expected: float,
) -> None:
    """Each vote/contradiction combination lands in its documented band."""
    assert evidence_score(signals) == pytest.approx(expected)


def test_band_boundaries_match_the_documented_ranges() -> None:
    """Three votes are at least 0.9, two sit inside 0.7-0.9, one is around 0.5."""
    three = evidence_score(EvidenceSignals(True, True, True))
    two = evidence_score(EvidenceSignals(True, True, False))
    one = evidence_score(EvidenceSignals(True, False, False))
    none = evidence_score(EvidenceSignals(False, False, False))
    contradiction = evidence_score(EvidenceSignals(False, False, True))

    assert three >= 0.9
    assert 0.7 <= two < 0.9
    assert one == pytest.approx(0.5)
    assert none < 0.5
    assert contradiction < 0.5


def test_scores_are_deterministic() -> None:
    """The same evidence always produces the same number."""
    signals = EvidenceSignals(True, True, True)

    assert evidence_score(signals) == evidence_score(signals)
    assert attribution_confidence("attributed", signals) == 0.9


def test_non_target_confidence_is_the_complement_of_attribution_evidence() -> None:
    """Absent attribution evidence supports the non-target conclusion."""
    full = EvidenceSignals(True, True, True)
    none = EvidenceSignals(False, False, False)
    contradiction = EvidenceSignals(True, False, True)

    assert attribution_confidence("non_target", full) == pytest.approx(0.1)
    assert attribution_confidence("non_target", none) == pytest.approx(0.7)
    assert attribution_confidence("non_target", contradiction) == pytest.approx(0.8)


def test_low_confidence_cluster_gate_stays_off() -> None:
    """The optional clustering gate ships as an off-by-default constant."""
    assert LOW_CONFIDENCE_CLUSTER_GATE_ENABLED is False
    assert LOW_CONFIDENCE_CLUSTER_THRESHOLD == 0.5


@pytest.mark.asyncio
async def test_engine_scores_a_fully_evidenced_self_report_at_the_top_band() -> None:
    """Comparable order, matching identity, and exact version reach 0.9."""
    result = await RuleBasedEngine().attribute(
        attribution_input(metadata={"error": "ENOENT"}),
    )

    assert result.conclusion == "attributed"
    assert result.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_engine_scores_one_signal_at_the_middle_band() -> None:
    """A self report that names the object but has no order/version stays at 0.5."""
    result = await RuleBasedEngine().attribute(
        attribution_input(
            hit_reason="self_report",
            order_state="unknown",
            case_object_version=None,
        ),
    )

    assert result.conclusion == "attributed"
    assert result.confidence == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_engine_lowers_confidence_for_contradictory_identity() -> None:
    """A different object with the exact target version is contradictory evidence."""
    result = await RuleBasedEngine().attribute(
        attribution_input(
            hit_reason="after_object",
            bad_case_type="discovery",
            case_object_name="helper",
        ),
    )

    assert result.conclusion == "attributed"
    assert result.confidence == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_engine_non_target_confidence_uses_the_complement() -> None:
    """A non-target conclusion is less certain when attribution evidence is strong."""
    result = await RuleBasedEngine().attribute(
        attribution_input(title="   ", description="  "),
    )

    assert result.conclusion == "non_target"
    assert result.confidence == pytest.approx(0.1)
