"""Value objects shared by every AI Agent provider implementation.

The seam has two capability faces: :meth:`AIAgentProvider.analyze` performs a
side-effect-free structured analysis, and
:meth:`AIAgentProvider.edit_workspace` returns an edit result for one
workspace. Results carry the same normalized observability fields (usage,
session id, latency, retryable) so callers never branch on a vendor. Provider
failures are folded into :class:`AgentProviderError`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.third_party_api.ai_agent.edits import EditPlan


def _require_non_empty(value: str, name: str) -> None:
    """Reject a blank identifier before it reaches logs or a provider."""
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_non_negative(value: int, name: str) -> None:
    """Reject negative counters that would corrupt normalized usage fields."""
    if value < 0:
        raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True, slots=True)
class AgentUsage:
    """Normalized model usage attached to one analysis or edit result.

    The field names mirror what a CLI backend reports: a model identifier,
    input/output token counts, and the reported cost. ``tokens`` is the total
    the design calls ``tokens``; the split is kept because CLI backends report
    it and cost accounting usually needs both directions.
    """

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        """Reject blank models and negative counters."""
        _require_non_empty(self.model, "AgentUsage.model")
        _require_non_negative(self.input_tokens, "AgentUsage.input_tokens")
        _require_non_negative(self.output_tokens, "AgentUsage.output_tokens")
        if not math.isfinite(self.cost_usd) or self.cost_usd < 0:
            raise ValueError("AgentUsage.cost_usd must be a non-negative finite number")

    @property
    def tokens(self) -> int:
        """Return the total token count across both directions."""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """One structured analysis request.

    ``task`` is the capability key (for example ``cluster.review``), ``prompt``
    is the caller-built prompt, and ``output_model`` is the caller's Pydantic
    model. Pydantic is the repository's schema source of truth; a provider must
    return output that validates against that model.
    """

    task: str
    prompt: str
    output_model: type[BaseModel]

    def __post_init__(self) -> None:
        """Keep the task key and schema usable before a provider is called."""
        _require_non_empty(self.task, "AnalysisRequest.task")
        _require_non_empty(self.prompt, "AnalysisRequest.prompt")
        if not issubclass(self.output_model, BaseModel):
            raise TypeError("AnalysisRequest.output_model must be a Pydantic model")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Normalized structured analysis output and its observability fields."""

    output: Mapping[str, Any]
    provider_id: str
    usage: AgentUsage = field(default_factory=lambda: AgentUsage(model="unknown"))
    session_id: str | None = None
    latency_ms: int = 0
    retryable: bool = False

    def __post_init__(self) -> None:
        """Reject a blank provider and negative latency."""
        _require_non_empty(self.provider_id, "AnalysisResult.provider_id")
        _require_non_negative(self.latency_ms, "AnalysisResult.latency_ms")


@dataclass(frozen=True, slots=True)
class EditRequest:
    """One workspace edit request.

    ``workspace`` is the prepared git workspace the provider may inspect.
    ``allowed_paths`` bounds the files the caller will accept in the resulting
    diff; an empty tuple means the caller has not narrowed the scope yet.
    """

    workspace: Path
    prompt: str
    allowed_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Keep the workspace absolute enough to be unambiguous."""
        if not self.workspace.is_absolute():
            raise ValueError("EditRequest.workspace must be an absolute path")
        _require_non_empty(self.prompt, "EditRequest.prompt")


@dataclass(frozen=True, slots=True)
class EditResult:
    """Normalized outcome of one workspace edit.

    ``changed_files`` holds workspace-relative paths and ``unified_diff`` is the
    git diff the provider observed; git remains the single source of truth.
    ``plan`` is the structured EditPlan the backend returned, kept for the
    deterministic applier and for the auditable candidate intent.
    """

    summary: str
    provider_id: str
    changed_files: tuple[str, ...] = ()
    unified_diff: str = ""
    usage: AgentUsage = field(default_factory=lambda: AgentUsage(model="unknown"))
    session_id: str | None = None
    latency_ms: int = 0
    retryable: bool = False
    plan: EditPlan | None = None

    def __post_init__(self) -> None:
        """Reject blank identifiers, negative latency, and a drifting summary."""
        _require_non_empty(self.summary, "EditResult.summary")
        _require_non_empty(self.provider_id, "EditResult.provider_id")
        _require_non_negative(self.latency_ms, "EditResult.latency_ms")
        if self.plan is not None and self.summary != self.plan.summary:
            raise ValueError("EditResult.summary must equal plan.summary")


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Sanitized health snapshot returned by a provider's startup probe."""

    provider_id: str
    healthy: bool
    detail: str | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        """Reject a blank provider and negative latency."""
        _require_non_empty(self.provider_id, "ProviderHealth.provider_id")
        if self.latency_ms is not None:
            _require_non_negative(self.latency_ms, "ProviderHealth.latency_ms")


class AgentProviderError(RuntimeError):
    """A sanitized provider failure safe to persist or display.

    ``message`` must not contain prompts, tokens, or raw model output; use
    ``detail`` for a bounded diagnostic. ``retryable`` says whether the caller
    may retry the same request without changing its inputs.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        provider_id: str,
        detail: str | None = None,
    ) -> None:
        """Store the normalized failure fields alongside the runtime message."""
        _require_non_empty(message, "AgentProviderError.message")
        _require_non_empty(provider_id, "AgentProviderError.provider_id")
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.provider_id = provider_id
        self.detail = detail


__all__ = [
    "AgentProviderError",
    "AgentUsage",
    "AnalysisRequest",
    "AnalysisResult",
    "EditRequest",
    "EditResult",
    "ProviderHealth",
]
