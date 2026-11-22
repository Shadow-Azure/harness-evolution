"""Settings-driven registry for AI Agent provider implementations.

``AI_AGENT_PROVIDER`` selects one registered subclass; the business layer only
calls :func:`build_agent_provider`. Adding a backend is one subclass plus one
registry entry, never a branch in a service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import (
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
)
from app.third_party_api.ai_agent.fake import FakeAIAgentProvider

if TYPE_CHECKING:
    from app.config import Settings


class _PendingClaudeCodeProvider(AIAgentProvider):
    """Startup-safe placeholder until the real CLI subclass arrives.

    The default ``claude-code`` selection must assemble without a real backend
    so a zero-config deployment still starts. Health is reported unhealthy and
    the capability calls fail loudly rather than silently degrading behavior.
    """

    provider_id: ClassVar[str] = "claude-code"

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Fail loudly until the real subclass replaces this placeholder."""
        raise NotImplementedError(
            "claude-code provider is not implemented yet; see bugfix-17",
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Fail loudly until the real subclass replaces this placeholder."""
        raise NotImplementedError(
            "claude-code provider is not implemented yet; see bugfix-17",
        )

    async def health_check(self) -> ProviderHealth:
        """Report that the reserved backend has no implementation yet."""
        return ProviderHealth(
            provider_id=self.provider_id,
            healthy=False,
            detail="claude-code provider is not implemented yet; see bugfix-17",
            latency_ms=0,
        )


_REGISTRY: dict[str, type[AIAgentProvider]] = {
    FakeAIAgentProvider.provider_id: FakeAIAgentProvider,
    _PendingClaudeCodeProvider.provider_id: _PendingClaudeCodeProvider,
}
"""Registered implementations; the keys are the legal ``AI_AGENT_PROVIDER`` values."""


def registered_provider_ids() -> frozenset[str]:
    """Return the immutable set of legal provider identifiers."""
    return frozenset(_REGISTRY)


def register_provider(
    provider_id: str,
    implementation: type[AIAgentProvider],
) -> None:
    """Add one backend without touching any business service.

    ``provider_id`` must match the implementation's declared ``provider_id`` so
    the settings value, registry key, and result field cannot drift apart.
    """
    normalized = provider_id.strip().lower()
    if not normalized:
        raise ValueError("AI agent provider id must not be empty")
    if not issubclass(implementation, AIAgentProvider):
        raise TypeError("AI agent provider implementation must be an AIAgentProvider")
    declared = getattr(implementation, "provider_id", "")
    if declared != normalized:
        raise ValueError(
            f"AI agent provider {implementation.__name__} declares {declared!r}, "
            f"not {normalized!r}",
        )
    _REGISTRY[normalized] = implementation


def build_agent_provider(settings: Settings) -> AIAgentProvider:
    """Instantiate the provider selected by ``settings.ai_agent_provider``."""
    provider_id = settings.ai_agent_provider.strip().lower()
    implementation = _REGISTRY.get(provider_id)
    if implementation is None:
        choices = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown AI agent provider: {provider_id!r}; expected one of: {choices}",
        )
    return implementation(settings)


__all__ = [
    "build_agent_provider",
    "register_provider",
    "registered_provider_ids",
]
