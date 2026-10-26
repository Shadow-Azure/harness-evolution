"""Fail-fast registry for evolution engine implementations."""

from typing import ClassVar

from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.engine.base import EvolutionEngine
from app.service.evolution.engine.cluster_only import ClusterOnlyEngine
from app.service.evolution.engine.contracts import ConfigError, EngineDeps
from app.service.evolution.engine.full import FullEvolutionEngine


class EngineFactory:
    """Resolve one run to exactly one explicitly registered engine."""

    _REGISTRY: ClassVar[dict[str, type[EvolutionEngine]]] = {
        "full": FullEvolutionEngine,
        "cluster_only": ClusterOnlyEngine,
    }

    @classmethod
    def for_run(
        cls,
        run: EvolutionRunRecord,
        deps: EngineDeps,
    ) -> EvolutionEngine:
        """Instantiate the engine snapshot recorded on the run."""
        engine_type = cls._REGISTRY.get(run.engine_key)
        if engine_type is None:
            raise ConfigError(f"unknown engine_key: {run.engine_key}")
        return engine_type(run, deps)
