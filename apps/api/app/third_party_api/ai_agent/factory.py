"""Settings-driven registry for AI Agent provider implementations.

``AI_AGENT_PROVIDER`` selects one registered subclass; the business layer only
calls :func:`build_agent_provider`. Adding a backend is one subclass plus one
registry entry, never a branch in a service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.claude_code import ClaudeCodeProvider
from app.third_party_api.ai_agent.fake import FakeAIAgentProvider

if TYPE_CHECKING:
    from app.config import Settings


_REGISTRY: dict[str, type[AIAgentProvider]] = {
    FakeAIAgentProvider.provider_id: FakeAIAgentProvider,
    ClaudeCodeProvider.provider_id: ClaudeCodeProvider,
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


def build_agent_provider(settings: Settings, *, provider_id: str | None = None) -> AIAgentProvider:
    """Build the deployment provider, or the explicit provider pinned for replay.

    Assembly goes through ``from_settings`` so a backend with its own
    configuration namespace resolves its entries at one construction point.
    """
    provider_id = (
        (provider_id if provider_id is not None else settings.ai_agent_provider).strip().lower()
    )
    implementation = _REGISTRY.get(provider_id)
    if implementation is None:
        choices = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown AI agent provider: {provider_id!r}; expected one of: {choices}",
        )
    return implementation.from_settings(settings)


__all__ = [
    "build_agent_provider",
    "register_provider",
    "registered_provider_ids",
]
