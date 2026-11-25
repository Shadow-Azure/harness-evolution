"""Evolution execution engine contracts and registration."""

from app.service.evolution.engine.base import EvolutionEngine
from app.service.evolution.engine.cluster_only import ClusterOnlyEngine
from app.service.evolution.engine.contracts import (
    ConfigError,
    EngineDeps,
    EvalGateway,
    EvalGatewayConfig,
    EvalMeasurement,
    EvalRequest,
    EvalResult,
    EvalStatus,
    EvalSubmission,
    EvolutionBlockedStage,
    RunBlocked,
)
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.engine.full import FullEvolutionEngine
from app.third_party_api.eval_gateway.fake import FakeEvalGateway

__all__ = [
    "ClusterOnlyEngine",
    "ConfigError",
    "EngineDeps",
    "EngineFactory",
    "EvalGateway",
    "EvalGatewayConfig",
    "EvalMeasurement",
    "EvalRequest",
    "EvalResult",
    "EvalStatus",
    "EvalSubmission",
    "EvolutionBlockedStage",
    "EvolutionEngine",
    "FakeEvalGateway",
    "FullEvolutionEngine",
    "RunBlocked",
]
