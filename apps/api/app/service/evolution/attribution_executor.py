"""Versioned executor boundary for pluggable Agent Skill attribution."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from app.service.identity.schemas import IdentityModel

EXECUTOR_INPUT_VERSION: Literal["attribution-executor-input/v1"] = "attribution-executor-input/v1"
EXECUTOR_OUTPUT_VERSION: Literal["attribution-executor-output/v1"] = (
    "attribution-executor-output/v1"
)
AGENT_SKILL_STUB_ENGINE = "agent-skill-stub-v1"


class AttributionExecutorTarget(IdentityModel):
    """Selected evolution object and its introduction coordinate."""

    object_type: Literal["skill", "agent", "knowledge"]
    object_name: str
    object_version: str | None = None
    introduction_ref: str | None = None
    introduction_at: str | None = None


class AttributionExecutorBadCase(IdentityModel):
    """Reported Badcase and its distinct detection coordinate."""

    bad_case_id: str
    bad_case_type: str
    title: str
    description: str
    report_ref: str | None = None
    detection_at: str | None = None
    hit_reason: str
    order_state: str
    error_signal: str | None = None


class AttributionExecutorSkill(IdentityModel):
    """Immutable Skill revision supplied to an executor."""

    key: str
    revision: str
    content_hash: str
    content: dict[str, Any]


class AttributionExecutorContext(IdentityModel):
    """Bounded Session context snapshot and evidence addresses."""

    session_id: str
    snapshot_hash: str
    payload: dict[str, Any] | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AttributionExecutorRequest(IdentityModel):
    """Stable, redacted input contract for an attribution executor."""

    schema_version: Literal["attribution-executor-input/v1"] = EXECUTOR_INPUT_VERSION
    workspace_id: str
    run_id: str
    target: AttributionExecutorTarget
    bad_case: AttributionExecutorBadCase
    skill: AttributionExecutorSkill
    context: AttributionExecutorContext


class AttributionExecutorResponse(IdentityModel):
    """Validated executor output projected into a Probe Report V2."""

    schema_version: Literal["attribution-executor-output/v1"] = EXECUTOR_OUTPUT_VERSION
    conclusion: Literal["attributed", "non_target", "inconclusive"]
    category: Literal["model", "prompt", "error"] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    evidence_references: list[str] = Field(default_factory=list)
    suggestion_clues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    token_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_category(self) -> AttributionExecutorResponse:
        """Keep the output compatible with the closed Probe Report semantics."""
        if self.conclusion == "attributed" and self.category is None:
            raise ValueError("attributed executor output requires a category")
        if self.conclusion != "attributed" and self.category is not None:
            raise ValueError("non-attributed executor output must not carry a category")
        return self


class AttributionExecutor(Protocol):
    """Replaceable boundary implemented by the future intranet Agent adapter."""

    key: str

    async def execute(self, request: AttributionExecutorRequest) -> AttributionExecutorResponse:
        """Return one schema-validated attribution result without persistence."""


class AgentSkillStubExecutor:
    """Deterministic offline executor used to verify the complete adapter path."""

    key = AGENT_SKILL_STUB_ENGINE

    async def execute(self, request: AttributionExecutorRequest) -> AttributionExecutorResponse:
        """Classify from bounded coordinates only; never access a model or network."""
        case = request.bad_case
        warnings = ["AGENT_EXECUTOR_STUB", *request.context.warnings]
        if request.context.payload is None:
            warnings.append("SESSION_CONTEXT_UNAVAILABLE")
        evidence = list(dict.fromkeys(request.context.evidence_refs))
        headline = (case.title.strip() or case.description.strip() or "(无标题)")[:200]
        if case.hit_reason in {"self_report", "both"}:
            category: Literal["prompt", "error"] = (
                "error" if case.error_signal is not None else "prompt"
            )
            return AttributionExecutorResponse(
                conclusion="attributed",
                category=category,
                confidence=0.8,
                summary=f"对象自身上报：{headline}",  # noqa: RUF001
                reasoning=(
                    "确定性执行器桩根据 self_report/both 命中归因；"  # noqa: RUF001
                    f"errorSignal={case.error_signal or 'none'}。"
                ),
                evidence_references=evidence,
                suggestion_clues=["由内网 Agent adapter 基于相同契约补充改进建议"],
                warnings=warnings,
            )
        if case.order_state == "comparable" and case.hit_reason == "before_object":
            return AttributionExecutorResponse(
                conclusion="non_target",
                confidence=0.9,
                summary=f"Badcase 早于对象引入：{headline}",  # noqa: RUF001
                reasoning="确定性执行器桩仅依据可比较的触发坐标判定该对象不是归因目标。",
                evidence_references=evidence,
                warnings=warnings,
            )
        if (
            case.order_state == "comparable"
            and case.hit_reason == "after_object"
            and case.bad_case_type == "discovery"
        ):
            return AttributionExecutorResponse(
                conclusion="attributed",
                category="error",
                confidence=0.6,
                summary=f"对象引入后发现：{headline}",  # noqa: RUF001
                reasoning="确定性执行器桩根据 after_object 且 discovery 的坐标组合归为 error。",
                evidence_references=evidence,
                warnings=warnings,
            )
        return AttributionExecutorResponse(
            conclusion="inconclusive",
            confidence=0.0,
            summary=f"归因证据不足：{headline}",  # noqa: RUF001
            reasoning="确定性执行器桩无法从当前顺序和最小证据判断归属。",
            evidence_references=evidence,
            warnings=[*warnings, "ATTRIBUTION_EVIDENCE_INSUFFICIENT"],
        )


_EXECUTORS: dict[str, AttributionExecutor] = {
    AGENT_SKILL_STUB_ENGINE: AgentSkillStubExecutor(),
}


def resolve_attribution_executor(key: str) -> AttributionExecutor:
    """Resolve one registered executor or fail before a report is written."""
    try:
        return _EXECUTORS[key]
    except KeyError as exc:
        raise ValueError(f"unknown attribution executor: {key}") from exc


__all__ = [
    "AGENT_SKILL_STUB_ENGINE",
    "EXECUTOR_INPUT_VERSION",
    "EXECUTOR_OUTPUT_VERSION",
    "AgentSkillStubExecutor",
    "AttributionExecutor",
    "AttributionExecutorBadCase",
    "AttributionExecutorContext",
    "AttributionExecutorRequest",
    "AttributionExecutorResponse",
    "AttributionExecutorSkill",
    "AttributionExecutorTarget",
    "resolve_attribution_executor",
]
