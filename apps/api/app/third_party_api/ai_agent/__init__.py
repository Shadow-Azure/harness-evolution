"""Outbound AI Agent seam: contracts, factory, deterministic fake, and submission."""

from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.claude_code import (
    AsyncioClaudeCliRunner,
    ClaudeCliResult,
    ClaudeCliRunner,
    ClaudeCodeProvider,
)
from app.third_party_api.ai_agent.contracts import (
    AgentCallTrace,
    AgentProviderError,
    AgentUsage,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
)
from app.third_party_api.ai_agent.edits import (
    EDIT_BUDGET,
    MAX_CONTENT_LINES,
    EditApplication,
    EditOp,
    EditPlan,
    EditPlanError,
    EditStatus,
    apply_edit_plan,
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
    "EDIT_BUDGET",
    "MAX_CONTENT_LINES",
    "RESULT_FILENAME",
    "SCHEMA_FILENAME",
    "SUBMISSION_TOOLS",
    "AIAgentProvider",
    "AgentCallTrace",
    "AgentProviderError",
    "AgentUsage",
    "AnalysisRequest",
    "AnalysisResult",
    "AsyncioClaudeCliRunner",
    "ClaudeCliResult",
    "ClaudeCliRunner",
    "ClaudeCodeProvider",
    "EditApplication",
    "EditOp",
    "EditPlan",
    "EditPlanError",
    "EditRequest",
    "EditResult",
    "EditStatus",
    "FakeAIAgentProvider",
    "ProviderHealth",
    "StructuredSubmission",
    "SubmissionOutcome",
    "SubmissionPrep",
    "apply_edit_plan",
    "build_agent_provider",
    "register_provider",
    "registered_provider_ids",
]
