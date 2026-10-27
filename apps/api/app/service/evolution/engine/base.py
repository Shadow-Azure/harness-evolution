"""Shared evolution engine lifecycle and stage dispatch."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.db.models.evolution import EvolutionRunRecord
from app.db.models.jobs import JobRunRecord
from app.service.evolution.engine.contracts import (
    ConfigError,
    EngineDeps,
    EvalGateway,
    EvalGatewayConfig,
)
from app.service.evolution.events import (
    EvolutionRunEvent,
    EvolutionRunEventLevel,
    EvolutionRunEventStage,
    EvolutionRunEventType,
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

    async def record_event(
        self,
        event_type: EvolutionRunEventType,
        *,
        level: EvolutionRunEventLevel,
        stage: EvolutionRunEventStage,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: dict[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> EvolutionRunEvent:
        """Record one phase event through the shared sanitized service boundary."""
        if self.deps.events is None:
            raise ConfigError("evolution event recorder is not configured")
        return await self.deps.events.record(
            self.run.id,
            event_type,
            level=level,
            stage=stage,
            message=message,
            step_index=step_index,
            cluster_id=cluster_id,
            round_id=round_id,
            job_id=job_id,
            payload=payload,
            error=error,
        )
