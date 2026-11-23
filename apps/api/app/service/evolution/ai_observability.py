"""One normalized shape for every ``ai_agent_call`` run event.

The cluster path and the agent-edit patch path produce the same observability
fields, so cost, latency, degradation, feedback retries, and submission parse
provenance can be aggregated from the event stream alone (07 §5.5.3 layer 5).
The module owns only serialization: providers report normalized results, and
callers decide the event stage and message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.third_party_api.ai_agent.contracts import (
    AgentCallTrace,
    AgentProviderError,
    EditResult,
)

AgentCallOutcome = Literal["ok", "degraded", "error"]
"""Terminal classification of one bounded AI call."""


@dataclass(frozen=True, slots=True)
class AiAgentCall:
    """Normalized observability fields for exactly one outbound AI call."""

    task: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    outcome: AgentCallOutcome
    session_id: str | None = None
    trace: AgentCallTrace = field(default_factory=AgentCallTrace)

    @classmethod
    def from_edit(cls, task: str, result: EditResult) -> AiAgentCall:
        """Build the record for an agent-edit call that produced a plan."""
        return cls(
            task=task,
            provider=result.provider_id,
            model=result.usage.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_usd=result.usage.cost_usd,
            latency_ms=result.latency_ms,
            outcome="ok",
            session_id=result.session_id,
            trace=result.trace,
        )

    @classmethod
    def failed(cls, task: str, error: AgentProviderError) -> AiAgentCall:
        """Build the error record for a provider call that raised."""
        return cls(
            task=task,
            provider=error.provider_id,
            model="unknown",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=0,
            outcome="error",
            trace=error.trace,
        )

    def payload(self) -> dict[str, Any]:
        """Return the stable event payload shared by every AI-call site.

        ``totalTokens`` is the total of both directions; the split stays for
        cost accounting. The key deliberately avoids ``tokens`` because the
        event sanitizer treats any key starting with ``token`` as a credential.
        The submission counters let a query derive the parse failure rate
        (``submissionParseFailures`` over ``attempts``) and the repair rate
        (``submissionRepaired``) without raw model output.
        """
        return {
            "task": self.task,
            "provider": self.provider,
            "model": self.model,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.input_tokens + self.output_tokens,
            "costUsd": self.cost_usd,
            "latencyMs": self.latency_ms,
            "outcome": self.outcome,
            "sessionId": self.session_id,
            "attempts": self.trace.attempts,
            "feedbackRetries": self.trace.feedback_retries,
            "submissionParsedBy": self.trace.parsed_by,
            "submissionRepaired": self.trace.repaired,
            "submissionParseFailures": self.trace.submission_parse_failures,
            "submissionValidationFailures": self.trace.submission_validation_failures,
        }


__all__ = ["AgentCallOutcome", "AiAgentCall"]
