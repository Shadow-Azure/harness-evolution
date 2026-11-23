"""Parent contract for outbound AI Agent providers.

Subclasses own one backend each (``fake`` and the real ``claude-code`` CLI).
Skill-capable providers also execute a frozen Skill in an isolated workspace.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Final

from app.third_party_api.ai_agent.contracts import (
    AgentProviderError,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
    SkillRunRequest,
)

if TYPE_CHECKING:
    from app.config import Settings

ANALYZE_TIMEOUT_SECONDS: Final = 300
"""Upper bound for one analysis call; a code constant, not a deployment knob."""

EDIT_TIMEOUT_SECONDS: Final = 1_800
"""Upper bound for one workspace edit call; a code constant, not a deployment knob."""

PERMISSION_MODE: Final = "dontAsk"
"""Headless permission mode shared by CLI backends; never grants file edits."""


class AIAgentProvider(ABC):
    """Unified outbound AI interface; the parent defines contracts only."""

    provider_id: ClassVar[str]

    def __init__(self, settings: Settings | None = None) -> None:
        """Keep the deployment settings available without re-reading the env."""
        self._settings = settings

    @property
    def settings(self) -> Settings | None:
        """Return the settings bound by the factory, when one was supplied."""
        return self._settings

    @abstractmethod
    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Return structured analysis that validates against the caller's model."""

    @abstractmethod
    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Return the structured EditPlan the caller applies deterministically."""

    @property
    def supports_skills(self) -> bool:
        """Whether the deployed provider implements the optional Skill entry point."""
        return type(self).run_skill is not AIAgentProvider.run_skill

    def require_skill_support(self) -> None:
        """Fail at assembly if an enabled deployment cannot execute a Skill."""
        if not self.supports_skills:
            raise AgentProviderError(
                "provider does not support Skill execution",
                provider_id=self.provider_id,
                retryable=False,
            )

    def default_skill_model(self) -> str | None:
        """Return the shared model selector, or defer selection to the provider itself."""
        return None

    def skill_model_identity(self, model: str | None) -> dict[str, str]:
        """Public settings that pin an executable Skill to its model for replay."""
        return {"model": model} if model is not None else {"selection": "provider-default"}

    async def run_skill(self, request: SkillRunRequest, *, diagnostics: dict[str, Any]) -> int:
        """Return token use; put sanitized attempt details in diagnostics even on failure."""
        raise AgentProviderError(
            "provider does not support Skill execution",
            provider_id=self.provider_id,
            retryable=False,
        )

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Return a sanitized health snapshot for startup assembly."""


__all__ = [
    "ANALYZE_TIMEOUT_SECONDS",
    "EDIT_TIMEOUT_SECONDS",
    "PERMISSION_MODE",
    "AIAgentProvider",
]
