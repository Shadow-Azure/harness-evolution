"""Deterministic in-process provider used by unit tests and CI.

The fake never touches the network, the filesystem, or a real model. It returns
fixed structures per task key (overridable per instance) and validates them
against the caller's Pydantic model before returning, which keeps business tests
honest about their schemas without a real backend.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ValidationError

from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import (
    AgentProviderError,
    AgentUsage,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
)
from app.third_party_api.ai_agent.edits import EditPlan

if TYPE_CHECKING:
    from app.config import Settings

_DEFAULT_ANALYSIS_OUTPUTS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "cluster.review": {"clusters": []},
        "cluster.score": {
            "scores": [{"cluster": "C1", "confidence": 0.5, "evidence_refs": []}],
        },
        "severity.score": {
            "severities": [
                {
                    "cluster": "C1",
                    "overall": 5.0,
                    "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
                },
            ],
        },
    },
)
"""Fixed default output per known task key; callers may override any of them."""

_MAX_DETAIL_CHARS = 2_000


def _validation_detail(exc: ValidationError) -> str:
    """Render field locations and messages without echoing the raw output."""
    parts = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    detail = "; ".join(parts) or str(exc)
    return detail[:_MAX_DETAIL_CHARS]


class FakeAIAgentProvider(AIAgentProvider):
    """Deterministic provider that needs no external service or credentials."""

    provider_id = "fake"

    capabilities: ClassVar[frozenset[str]] = frozenset({"analyze", "edit"})
    """Minimal explicit protocol sample: no ``skill``, so attribution stays cache-only."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        outputs: Mapping[str, Mapping[str, Any]] | None = None,
        edit_plan: Mapping[str, Any] | None = None,
        session_id: str = "fake-session",
        latency_ms: int = 0,
    ) -> None:
        """Bind optional per-task outputs, an edit plan, and fixed observability values."""
        super().__init__(settings)
        if latency_ms < 0:
            raise ValueError("fake latency_ms must not be negative")
        if not session_id.strip():
            raise ValueError("fake session_id must not be empty")
        self._outputs = {task: deepcopy(dict(output)) for task, output in (outputs or {}).items()}
        self._edit_plan = deepcopy(dict(edit_plan)) if edit_plan is not None else None
        self._session_id = session_id
        self._latency_ms = latency_ms

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Return one deterministic structure validated by the caller's model."""
        raw: Mapping[str, Any] | None = self._outputs.get(request.task)
        if raw is None:
            raw = _DEFAULT_ANALYSIS_OUTPUTS.get(request.task)
        if raw is None:
            raw = {"task": request.task}
        try:
            validated = request.output_model.model_validate(deepcopy(raw))
        except ValidationError as exc:
            raise AgentProviderError(
                "fake analysis output failed the caller schema",
                retryable=False,
                provider_id=self.provider_id,
                detail=_validation_detail(exc),
            ) from exc
        return AnalysisResult(
            output=validated.model_dump(mode="json"),
            provider_id=self.provider_id,
            usage=AgentUsage(model=self.provider_id),
            session_id=self._session_id,
            latency_ms=self._latency_ms,
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Return a fixed plan (or no change) without touching the workspace."""
        if self._edit_plan is None:
            return EditResult(
                summary="fake edit: no changes",
                provider_id=self.provider_id,
                changed_files=(),
                unified_diff="",
                usage=AgentUsage(model=self.provider_id),
                session_id=self._session_id,
                latency_ms=self._latency_ms,
            )
        plan = EditPlan.model_validate(deepcopy(self._edit_plan))
        return EditResult(
            summary=plan.summary,
            provider_id=self.provider_id,
            usage=AgentUsage(model=self.provider_id),
            session_id=self._session_id,
            latency_ms=self._latency_ms,
            plan=plan,
        )

    async def health_check(self) -> ProviderHealth:
        """Report a healthy deterministic backend that needs no credentials."""
        return ProviderHealth(
            provider_id=self.provider_id,
            healthy=True,
            detail="deterministic fake provider",
            latency_ms=self._latency_ms,
            auth="ok",
        )


__all__ = ["FakeAIAgentProvider"]
