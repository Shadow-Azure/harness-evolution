"""Agent Skill executor contracts and deterministic adapter behavior."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.service.evolution.attribution import AgentSkillStubEngine, AttributionInput
from app.service.evolution.attribution_executor import (
    AgentSkillStubExecutor,
    AttributionExecutorBadCase,
    AttributionExecutorContext,
    AttributionExecutorRequest,
    AttributionExecutorResponse,
    AttributionExecutorSkill,
    AttributionExecutorTarget,
)
from app.utils.time import SHANGHAI


def _request(*, hit_reason: str = "self_report") -> AttributionExecutorRequest:
    """Build one bounded executor request without a Session payload."""
    return AttributionExecutorRequest(
        workspace_id="ws-default",
        run_id="run-agent-stub",
        target=AttributionExecutorTarget(
            object_type="skill",
            object_name="deep-research",
            object_version="tag:v2",
            introduction_ref="event:agent-main:1",
        ),
        bad_case=AttributionExecutorBadCase(
            bad_case_id="bc-agent-stub",
            bad_case_type="self",
            title="索引读取失败",
            description="没有验证索引 revision",
            report_ref="event:agent-main:2",
            hit_reason=hit_reason,
            order_state="comparable",
        ),
        skill=AttributionExecutorSkill(
            key="workspace-attribution",
            revision="1",
            content_hash="a" * 64,
            content={"instructions": "analyze evidence references"},
        ),
        context=AttributionExecutorContext(
            session_id="session-agent-stub",
            snapshot_hash="b" * 64,
            evidence_refs=["event:agent-main:1", "event:agent-main:2"],
        ),
    )


@pytest.mark.asyncio
async def test_stub_is_deterministic_and_marks_offline_execution() -> None:
    """Repeated requests return identical validated output without external calls."""
    executor = AgentSkillStubExecutor()

    first = await executor.execute(_request())
    second = await executor.execute(_request())

    assert first == second
    assert first.conclusion == "attributed"
    assert first.category == "prompt"
    assert first.evidence_references == ["event:agent-main:1", "event:agent-main:2"]
    assert first.warnings == ["AGENT_EXECUTOR_STUB", "SESSION_CONTEXT_UNAVAILABLE"]


@pytest.mark.asyncio
async def test_stub_preserves_a_confident_non_target_result() -> None:
    """A comparable report before object introduction stays out of clustering."""
    output = await AgentSkillStubExecutor().execute(_request(hit_reason="before_object"))

    assert output.conclusion == "non_target"
    assert output.category is None
    assert output.confidence == pytest.approx(0.9)


def test_executor_output_rejects_incompatible_category() -> None:
    """Malformed adapter output fails schema validation before persistence."""
    with pytest.raises(ValidationError):
        AttributionExecutorResponse(
            conclusion="non_target",
            category="error",
            confidence=0.8,
            summary="invalid",
            reasoning="invalid",
        )


@pytest.mark.asyncio
async def test_engine_projects_executor_output_to_existing_result() -> None:
    """The engine adapter consumes a frozen Skill revision and remains cacheable."""
    item = AttributionInput(
        bad_case_id="bc-agent-stub",
        run_id="run-agent-stub",
        workspace_id="ws-default",
        session_id="session-agent-stub",
        probe_type="skill",
        probe_object="deep-research",
        object_version="tag:v2",
        policy_version="v1",
        attribution_engine="agent-skill-stub-v1",
        attribution_skill_key="workspace-attribution",
        attribution_skill_revision="1",
        attribution_skill_content_hash="a" * 64,
        attribution_skill_executor_type="agent_stub",
        attribution_skill_content={"instructions": "analyze evidence references"},
        bad_case_type="self",
        title="索引读取失败",
        description="没有验证索引 revision",
        hit_reason="self_report",
        order_state="comparable",
        object_trigger_at=datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI),
        case_trigger_at=datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI),
    )

    result = await AgentSkillStubEngine().attribute(item)

    assert result.conclusion == "attributed"
    assert result.category == "prompt"
    assert "AGENT_EXECUTOR_STUB" in result.warnings
    assert "SESSION_CONTEXT_UNAVAILABLE" in result.warnings
