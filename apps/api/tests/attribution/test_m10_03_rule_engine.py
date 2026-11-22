"""Pure rule-v1 attribution behavior and deterministic evidence handling."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.service.evolution.attribution import (
    AttributionInput,
    KnowledgeEvidence,
    RuleBasedEngine,
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
    knowledge: tuple[KnowledgeEvidence, ...] = (),
    object_version: str | None = "tag:v2.0.0",
    case_object_type: str = "skill",
    case_object_name: str = "deep-research",
    case_object_version: str | None = "v2.0.0",
) -> AttributionInput:
    """Build one pure engine input with deterministic defaults.

    The default evidence names the attributed object and the selected version,
    so the three signals all hold and the completeness score is the top band.
    """
    return AttributionInput(
        bad_case_id="bc-rule-a",
        workspace_id="ws-rule",
        session_id="95000000-0000-4000-8000-000000000001",
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
        knowledge_evidence=knowledge,
        case_object_type=case_object_type,
        case_object_name=case_object_name,
        case_object_version=case_object_version,
    )


@pytest.mark.asyncio
async def test_self_report_with_error_evidence_is_attributed_error() -> None:
    """A self report with full evidence scores in the top completeness band."""
    result = await RuleBasedEngine().attribute(
        attribution_input(metadata={"error": "ENOENT", "file": "index.ts"}),
    )

    assert result.conclusion == "attributed"
    assert result.category == "error"
    assert result.confidence == pytest.approx(0.9)
    assert "检索索引读取失败" in result.reason
    assert "ENOENT" in result.reason
    assert "deep-research@tag:v2.0.0" in result.reasoning
    assert "v1/rule-v1" in result.reasoning


@pytest.mark.asyncio
async def test_self_report_without_error_evidence_is_attributed_prompt() -> None:
    """A self report without an error signal stays a prompt attribution."""
    result = await RuleBasedEngine().attribute(
        attribution_input(metadata={"file": "skills/deep-research/SKILL.md"}),
    )

    assert result.conclusion == "attributed"
    assert result.category == "prompt"
    assert result.confidence == pytest.approx(0.9)
    assert "未发现错误证据" in result.reasoning


@pytest.mark.asyncio
async def test_after_object_discovery_is_attributed_error() -> None:
    """A discovery case triggered after object entry is an error attribution."""
    result = await RuleBasedEngine().attribute(
        attribution_input(hit_reason="after_object", bad_case_type="discovery"),
    )

    assert result.conclusion == "attributed"
    assert result.category == "error"
    assert result.confidence == pytest.approx(0.9)
    assert "after_object" in result.reasoning
    assert "discovery" in result.reasoning


@pytest.mark.asyncio
async def test_unknown_order_is_non_target_without_category() -> None:
    """An incomparable order cannot attribute the case to the object."""
    result = await RuleBasedEngine().attribute(
        attribution_input(hit_reason="order_unknown", order_state="unknown"),
    )

    assert result.conclusion == "non_target"
    assert result.category is None
    assert result.confidence == pytest.approx(0.2)
    assert "非该对象问题" in result.reason
    assert "不进簇" in result.reasoning


@pytest.mark.asyncio
async def test_empty_self_report_is_non_target_by_insufficient_evidence() -> None:
    """An included case with no title or description has no usable evidence."""
    result = await RuleBasedEngine().attribute(
        attribution_input(title="   ", description="  "),
    )

    assert result.conclusion == "non_target"
    assert result.category is None
    assert result.confidence == pytest.approx(0.1)
    assert "证据不足" in result.reasoning


@pytest.mark.asyncio
async def test_knowledge_evidence_is_used_for_prompt_category_and_reasoning() -> None:
    """Knowledge document evidence turns a plain self report into a prompt cue."""
    result = await RuleBasedEngine().attribute(
        attribution_input(
            knowledge=(
                KnowledgeEvidence(
                    document_id="KB-READ-001",
                    document_revision="digest:" + "a" * 64,
                    source_path="/kb/retrieval.md",
                    retrieval_kind="file_read",
                ),
            ),
        ),
    )

    assert result.conclusion == "attributed"
    assert result.category == "prompt"
    assert "/kb/retrieval.md" in result.reasoning
    assert "digest:" + "a" * 64 in result.reasoning
    assert "file_read" in result.reasoning


@pytest.mark.asyncio
async def test_engine_output_is_deterministic() -> None:
    """The same input produces byte-identical reason and reasoning."""
    engine = RuleBasedEngine()
    item = attribution_input(metadata={"error": "timeout"})

    first = await engine.attribute(item)
    second = await engine.attribute(item)

    assert first == second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"exitCode": 2},
        {"status": "failed"},
        {"stderr": "traceback"},
    ],
)
async def test_other_error_evidence_shapes_stay_error(metadata: dict[str, object]) -> None:
    """Exit codes, failed status, and stderr are concrete error evidence."""
    result = await RuleBasedEngine().attribute(attribution_input(metadata=metadata))

    assert result.conclusion == "attributed"
    assert result.category == "error"


@pytest.mark.parametrize(
    "changes",
    [
        {"conclusion": "maybe"},
        {"confidence": 1.5},
        {"conclusion": "non_target", "category": "error"},
        {"conclusion": "attributed", "category": None},
    ],
)
def test_result_rejects_invalid_closed_sets(changes: dict[str, object]) -> None:
    """A malformed engine result cannot reach a probe row."""
    from app.service.evolution.attribution import AttributionResult

    values: dict[str, object] = {
        "conclusion": "attributed",
        "category": "error",
        "confidence": 0.8,
        "reason": "reason",
        "reasoning": "reasoning",
    }
    values.update(changes)
    with pytest.raises(ValueError):
        AttributionResult(**values)  # type: ignore[arg-type]
