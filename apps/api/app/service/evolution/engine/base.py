"""Shared evolution engine lifecycle and stage dispatch."""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.db.models.evolution import EvolutionRunRecord
from app.db.models.jobs import JobRunRecord
from app.service.evolution.engine.contracts import (
    ConfigError,
    EngineDeps,
    EvalGateway,
    EvalGatewayConfig,
)


class EvolutionEngine(ABC):
    """Own stage capability checks and gateway construction for one engine."""

    KIND_TO_METHOD: ClassVar[dict[str, str]] = {
        "evolution_prepare": "prepare",
    }

    def __init__(self, run: EvolutionRunRecord, deps: EngineDeps) -> None:
        """Bind one persisted run to its injected collaborators."""
        self.run = run
        self.deps = deps

    @abstractmethod
    def stages(self) -> tuple[str, ...]:
        """Return the exact job kinds this engine supports."""

    async def handle(self, job: JobRunRecord) -> None:
        """Dispatch a supported stage and reject every undeclared capability."""
        if job.kind not in self.stages():
            raise ConfigError(
                f"{type(self).__name__} does not support stage {job.kind}",
            )
        method_name = self.KIND_TO_METHOD.get(job.kind)
        if method_name is None:
            raise ConfigError(
                f"{type(self).__name__} declares stage {job.kind} without a method",
            )
        method = getattr(self, method_name, None)
        if not callable(method):
            raise ConfigError(
                f"{type(self).__name__} is missing method {method_name}",
            )
        await method(job)

    def gateway(self) -> EvalGateway:
        """Build a gateway from the immutable run configuration snapshot."""
        config = EvalGatewayConfig.from_mapping(self.run.eval_config)
        return self.deps.gateway_factory(config)
