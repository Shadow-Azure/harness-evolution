"""Outbound AI Agent seam: contracts, factory, deterministic fake, and submission."""

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
from app.third_party_api.ai_agent.submission import (
    RESULT_FILENAME,
    SCHEMA_FILENAME,
    SUBMISSION_TOOLS,
    StructuredSubmission,
    SubmissionOutcome,
    SubmissionPrep,
)

__all__ = [
    "RESULT_FILENAME",
    "SCHEMA_FILENAME",
    "SUBMISSION_TOOLS",
    "AIAgentProvider",
    "AgentProviderError",
    "AgentUsage",
    "AnalysisRequest",
    "AnalysisResult",
    "EditRequest",
    "EditResult",
    "FakeAIAgentProvider",
    "ProviderHealth",
    "StructuredSubmission",
    "SubmissionOutcome",
    "SubmissionPrep",
    "build_agent_provider",
    "register_provider",
    "registered_provider_ids",
]
