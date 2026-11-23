"""Deployment-selected agent invocation and model settings."""

from abc import ABC, abstractmethod
from importlib import import_module
from pathlib import Path
from typing import Any, ClassVar, cast


class ModelBackend(ABC):
    """Resolve an administrator's model selection for an agent."""

    @abstractmethod
    def resolve(self, model: str) -> str: ...


class NativeModel(ModelBackend):
    def resolve(self, model: str) -> str:
        if not model.strip() or model.startswith("-"):
            raise ValueError("invalid attribution model")
        return model


class AgentBackend(ABC):
    """Invoke a CLI or SDK on a single private working directory."""

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


class AgentFactory:
    providers: ClassVar[dict[str, type[AgentBackend]]] = {}

    @classmethod
    def create(cls, provider: str) -> AgentBackend:
        from app.third_party_api.attribution.claude_backend import ClaudeBackend

        providers: dict[str, type[AgentBackend]] = {"claude": ClaudeBackend, **cls.providers}
        return _provider(provider, providers, AgentBackend)
