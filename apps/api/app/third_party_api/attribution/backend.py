"""Deployment-selected agent invocation and model settings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import AgentProviderError, ProviderHealth

if TYPE_CHECKING:
    from app.third_party_api.ai_agent.contracts import (
        AnalysisRequest,
        AnalysisResult,
        EditRequest,
        EditResult,
        SkillRunRequest,
    )


class ModelBackend(ABC):
    """Resolve an administrator's model selection for an agent."""

    @abstractmethod
    def resolve(self, model: str) -> str: ...


class NativeModel(ModelBackend):
    def resolve(self, model: str) -> str:
        if not model.strip() or model.startswith("-"):
            raise ValueError("invalid attribution model")
        return model


class AgentBackend(AIAgentProvider):
    """Compatibility for installed module:Class Skill plugins with the old execute method."""

    provider_id = "legacy-skill"

    def skill_model_identity(self, model: str | None) -> dict[str, str]:
        if model is None:
            raise ValueError("legacy Skill plugin requires a pinned model")
        return self.model_identity(model)

    async def run_skill(self, request: SkillRunRequest, *, diagnostics: dict[str, Any]) -> int:
        if request.model is None:
            raise ValueError("legacy Skill plugin requires a pinned model")
        try:
            return await self.execute(
                request.directory, request.prompt, request.model, request.timeout_seconds
            )
        finally:
            try:
                diagnostics.update(self.execution_details(request.directory))
            except Exception as exc:
                diagnostics["diagnosticError"] = type(exc).__name__

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        raise AgentProviderError(
            "Skill-only provider", provider_id=self.provider_id, retryable=False
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        raise AgentProviderError(
            "Skill-only provider", provider_id=self.provider_id, retryable=False
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, healthy=False, detail="No health probe")

    def model_identity(self, model: str) -> dict[str, str]:
        """Return non-secret facts that must remain stable between launch and execution."""
        return {"model": model}

    def execution_details(self, directory: Path) -> dict[str, Any]:
        """Collect agent-specific public diagnostics before the working directory is removed."""
        return {}

    @abstractmethod
    async def execute(self, directory: Path, prompt: str, model: str, timeout_seconds: int) -> int:
        """Return token usage after successful completion."""


def _provider[T](name: str, builtin: dict[str, type[T]], base: type) -> T:
    implementation = builtin.get(name)
    if implementation is None:
        module, separator, classname = name.partition(":")
        if not separator:
            raise ValueError(f"unknown attribution provider: {name}")
        candidate = getattr(import_module(module), classname)
        if not isinstance(candidate, type) or not issubclass(candidate, base):
            raise ValueError(f"incompatible attribution provider: {name}")
        implementation = cast(type[T], candidate)
    return implementation()


class ModelFactory:
    providers: ClassVar[dict[str, type[ModelBackend]]] = {"agent-native": NativeModel}

    @classmethod
    def create(cls, provider: str) -> ModelBackend:
        return _provider(provider, cls.providers, ModelBackend)


def legacy_skill_provider(path: str) -> AgentBackend:
    """Instantiate an installed legacy plugin once per attempt, preserving its frozen identity."""
    return _provider(path, {}, AgentBackend)
