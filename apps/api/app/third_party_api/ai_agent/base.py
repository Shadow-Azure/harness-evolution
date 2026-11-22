"""Parent contract for outbound AI Agent providers.

Subclasses own one backend each (``fake`` now, ``claude-code`` in a later
issue). They answer the same three capability questions, so business services
never import a vendor module or branch on a backend name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Final

from app.third_party_api.ai_agent.contracts import (
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
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
        """Produce and apply an edit plan for one workspace."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Return a sanitized health snapshot for startup assembly."""


__all__ = [
    "ANALYZE_TIMEOUT_SECONDS",
    "EDIT_TIMEOUT_SECONDS",
    "PERMISSION_MODE",
    "AIAgentProvider",
]
