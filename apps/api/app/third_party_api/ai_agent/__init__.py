"""Outbound AI Agent seam: contracts, factory, and deterministic fake."""

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
from app.third_party_api.ai_agent.factory import (
    build_agent_provider,
    register_provider,
    registered_provider_ids,
)
from app.third_party_api.ai_agent.fake import FakeAIAgentProvider

__all__ = [
    "AIAgentProvider",
    "AgentProviderError",
    "AgentUsage",
    "AnalysisRequest",
    "AnalysisResult",
    "EditRequest",
    "EditResult",
    "FakeAIAgentProvider",
    "ProviderHealth",
    "build_agent_provider",
    "register_provider",
    "registered_provider_ids",
]
