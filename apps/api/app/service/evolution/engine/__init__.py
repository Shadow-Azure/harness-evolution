"""Evolution execution engine contracts and registration."""

from app.service.evolution.engine.base import EvolutionEngine
from app.service.evolution.engine.cluster_only import ClusterOnlyEngine
from app.service.evolution.engine.contracts import (
    ConfigError,
    EngineDeps,
    EvalGateway,
    EvalGatewayConfig,
)
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.engine.full import FullEvolutionEngine

__all__ = [
    "ClusterOnlyEngine",
    "ConfigError",
    "EngineDeps",
    "EngineFactory",
    "EvalGateway",
    "EvalGatewayConfig",
    "EvolutionEngine",
    "FullEvolutionEngine",
]
