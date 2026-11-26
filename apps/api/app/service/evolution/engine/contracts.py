"""Dependencies and immutable values used by evolution engines."""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from app.db.models.evolution import (
    ClusterWrite,
    EvolutionFinalRecord,
    EvolutionRunRecord,
    ProbeClusterRecord,
)
from app.db.models.jobs import JobRunRecord
from app.service.evolution.events import EvolutionRunEventService


class ConfigError(RuntimeError):
    """Raised when an engine selection or stage capability is invalid."""


class EvalGatewayConfigError(ConfigError):
    """Raised when an evaluation gateway configuration is invalid or incomplete."""


EvolutionBlockedStage = Literal["patch", "push", "eval", "attribution"]


class RunBlocked(RuntimeError):
    """A retryable evolution failure that must leave the run blocked."""

    def __init__(
        self,
        message: str,
        *,
        stage: EvolutionBlockedStage,
        error_stage: str | None = None,
        next_retry_at: datetime | None = None,
        retry_attempts: int = 0,
        retryable: bool = True,
        detail: str | None = None,
    ) -> None:
        """Carry the safe reason, detail, and retry facts across the job boundary."""
        super().__init__(message)
        self.stage = stage
        self.error_stage = error_stage or stage
        self.next_retry_at = next_retry_at
        self.retry_attempts = retry_attempts
        self.retryable = retryable
        self.detail = detail


class ProbeReader(Protocol):
    """Read probes needed by a future prepare stage."""

    async def list_matching(
        self,
        query: Mapping[str, Any],
    ) -> Sequence[object]:
        """Return probes matching the frozen run query."""


class EvolutionRepositoryProtocol(Protocol):
    """Persistence operations used by engine orchestration."""

    async def advance_unit(
        self,
        run_id: str,
        *,
        expected: int,
        target: int,
        cluster_count: int,
    ) -> EvolutionRunRecord:
        """Advance one run cursor."""

    async def replace_clusters(
        self,
        run_id: str,
        clusters: Sequence[ClusterWrite],
    ) -> tuple[ProbeClusterRecord, ...]:
        """Replace one run's cluster snapshot."""

    async def insert_rounds(self, rounds: Sequence[Mapping[str, Any]]) -> None:
        """Insert pending iteration rounds."""

    async def write_final(self, values: Mapping[str, Any]) -> EvolutionFinalRecord:
        """Write the final evaluation row."""


type FrozenScalar = str | int | float | bool | None
type FrozenValue = FrozenScalar | tuple[FrozenValue, ...] | Mapping[str, FrozenValue]


def freeze_json(value: object) -> FrozenValue:
    """Deep-copy JSON-like values into immutable containers."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_json(item) for key, item in value.items()},
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"unsupported eval config value: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class EvalGatewayConfig(Mapping[str, FrozenValue]):
    """Immutable creation-time configuration passed to an evaluation gateway."""

    _values: Mapping[str, FrozenValue]

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> EvalGatewayConfig:
        """Freeze a run's JSON configuration snapshot."""
        frozen = MappingProxyType(
            {str(key): freeze_json(value) for key, value in values.items()},
        )
        return cls(frozen)

    def __getitem__(self, key: str) -> FrozenValue:
        """Return one frozen configuration value."""
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate configuration keys in insertion order."""
        return iter(self._values)

    def __len__(self) -> int:
        """Return the number of configuration keys."""
        return len(self._values)


class EvalGateway(Protocol):
    """External evaluation seam consumed by later iteration stages."""

    @property
    def config(self) -> EvalGatewayConfig:
        """Expose the frozen gateway configuration."""

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        """Submit one immutable candidate for external evaluation."""

    async def get_status(self, eval_id: str) -> EvalStatus:
        """Return the external evaluation's current lifecycle state."""

    async def get_result(self, eval_id: str) -> EvalMeasurement:
        """Return the measured metrics; the service layer applies the gate."""


EvalStatusValue = Literal["queued", "running", "completed", "failed", "timeout"]
EvalVerdict = Literal["accept", "reject"]
EvalDirection = Literal["higher_is_better", "lower_is_better"]
EvalPurpose = Literal[
    "candidate",
    "validation_baseline",
    "test_baseline",
    "test_final",
]

EVAL_BASELINE_KINDS = ("validation_baseline", "test_baseline")
EVAL_PURPOSES: tuple[EvalPurpose, ...] = (
    "candidate",
    "validation_baseline",
    "test_baseline",
    "test_final",
)


@dataclass(frozen=True, slots=True)
class EvalTarget:
    """One repository asset submitted to the evaluation platform."""

    object_type: str
    object_name: str
    sub_dir: str


@dataclass(frozen=True, slots=True)
class EvalRequest:
    """Stable internal request passed to every evaluation implementation."""

    run_id: str
    evolution_round_id: str
    repo_url: str
    ref: str
    commit: str
    target_type: str
    target_name: str
    target_version: str
    cluster_id: str
    idempotency_key: str
    purpose: EvalPurpose = "candidate"
    project_id: str = ""
    sub_dir: str = ""
    attempt: int = 1
    round_seq: int = 0
    parent_commit: str = ""
    targets: tuple[EvalTarget, ...] = ()


@dataclass(frozen=True, slots=True)
class EvalSubmission:
    """External evaluation identifier and non-fatal platform warnings."""

    eval_id: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvalStatus:
    """One external evaluation status and optional safe message."""

    status: EvalStatusValue
    message: str | None = None


@dataclass(frozen=True, slots=True)
class EvalMeasurement:
    """One external evaluation's measured primary metric and raw items.

    Baseline evaluations, per-round candidate evaluations and the held-out
    test-set final all return this shape; comparing the candidate with the
    active baseline is a service-layer decision, never the platform's verdict.
    """

    candidate_score: float
    primary_metric_key: str
    direction: EvalDirection
    metrics: tuple[Mapping[str, FrozenValue], ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed scores before they can become persisted JSON."""
        _strict_score(self.candidate_score)
        _EvalDirection.validate(self.direction)

    def to_payload(self) -> dict[str, Any]:
        """Serialize the measurement into the round's stable JSON representation."""
        return {
            "candidateScore": self.candidate_score,
            "primaryMetricKey": self.primary_metric_key,
            "direction": self.direction,
            "metrics": [_thaw_json(metric) for metric in self.metrics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> EvalMeasurement:
        """Read a persisted measurement and reject malformed external data."""
        candidate = payload.get("candidateScore")
        metric_key = payload.get("primaryMetricKey")
        direction = payload.get("direction", "higher_is_better")
        metrics = payload.get("metrics", ())
        candidate_score = _strict_score(candidate, persisted=True)
        if not isinstance(metric_key, str) or not metric_key.strip():
            raise ValueError("persisted primary metric key is invalid")
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise ValueError("persisted metric direction is invalid")
        if not isinstance(metrics, (list, tuple)):
            raise ValueError("persisted evaluation metrics are invalid")
        if any(not isinstance(metric, Mapping) for metric in metrics):
            raise ValueError("persisted evaluation metrics must contain objects")
        frozen_metrics: list[Mapping[str, FrozenValue]] = []
        for metric in metrics:
            frozen_metrics.append(
                cast(Mapping[str, FrozenValue], freeze_json(metric)),
            )
        return cls(
            candidate_score=candidate_score,
            primary_metric_key=metric_key.strip(),
            direction=cast(EvalDirection, direction),
            metrics=tuple(frozen_metrics),
        )


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Gated result consumed by apply, final evaluation and the API projection."""

    current_score: float
    candidate_score: float
    external_verdict: EvalVerdict
    metrics: tuple[Mapping[str, FrozenValue], ...] = ()
    direction: EvalDirection = "higher_is_better"
    primary_metric_key: str = ""

    def __post_init__(self) -> None:
        """Reject malformed scores before they can become persisted JSON."""
        _strict_score(self.current_score)
        _strict_score(self.candidate_score)
        _EvalDirection.validate(self.direction)

    def to_payload(self) -> dict[str, Any]:
        """Serialize the result into the round's stable JSON representation."""
        return {
            "currentScore": self.current_score,
            "candidateScore": self.candidate_score,
            "externalVerdict": self.external_verdict,
            "direction": self.direction,
            "primaryMetricKey": self.primary_metric_key,
            "metrics": [_thaw_json(metric) for metric in self.metrics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> EvalResult:
        """Read a persisted result and reject malformed external data."""
        current = payload.get("currentScore")
        candidate = payload.get("candidateScore")
        verdict = payload.get("externalVerdict")
        direction = payload.get("direction", "higher_is_better")
        primary_metric_key = payload.get("primaryMetricKey", "")
        metrics = payload.get("metrics", ())
        current_score = _strict_score(current, persisted=True)
        candidate_score = _strict_score(candidate, persisted=True)
        if verdict not in {"accept", "reject"}:
            raise ValueError("persisted external verdict is invalid")
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise ValueError("persisted metric direction is invalid")
        if not isinstance(metrics, (list, tuple)):
            raise ValueError("persisted evaluation metrics are invalid")
        if any(not isinstance(metric, Mapping) for metric in metrics):
            raise ValueError("persisted evaluation metrics must contain objects")
        frozen_metrics: list[Mapping[str, FrozenValue]] = []
        for metric in metrics:
            frozen_metrics.append(
                cast(Mapping[str, FrozenValue], freeze_json(metric)),
            )
        return cls(
            current_score=current_score,
            candidate_score=candidate_score,
            external_verdict=verdict,
            metrics=tuple(frozen_metrics),
            direction=cast(EvalDirection, direction),
            primary_metric_key=(
                primary_metric_key.strip() if isinstance(primary_metric_key, str) else ""
            ),
        )


class _EvalDirection:
    """Validate one metric direction without a pydantic dependency."""

    @staticmethod
    def validate(direction: object) -> None:
        """Reject an unsupported comparison direction."""
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise ValueError("evaluation metric direction is invalid")


type GatewayFactory = Callable[[EvalGatewayConfig], EvalGateway]
type StageHandler = Callable[[JobRunRecord], Awaitable[None]]
type ClusterPrepare = Callable[
    [EvolutionRunRecord, Mapping[str, Any]],
    Awaitable[None],
]


def default_gateway_factory(config: EvalGatewayConfig) -> EvalGateway:
    """Build the deterministic gateway used by the V1 evolution loop."""
    from app.third_party_api.eval_gateway.fake import FakeEvalGateway

    return FakeEvalGateway(config=config)


if TYPE_CHECKING:
    from app.third_party_api.eval_gateway.fake import FakeEvalGateway  # noqa: F401


def __getattr__(name: str) -> object:
    """Keep the historical FakeEvalGateway re-export without an import cycle."""
    if name in {"FakeEvalGateway", "DefaultEvalGateway"}:
        from app.third_party_api.eval_gateway.fake import FakeEvalGateway

        if name == "DefaultEvalGateway":
            return FakeEvalGateway
        return FakeEvalGateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _thaw_json(value: FrozenValue) -> Any:
    """Convert immutable frozen config values back to JSON-compatible data."""
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _strict_score(value: object, *, persisted: bool = False) -> float:
    """Validate one score from construction, a gateway result, or persisted JSON."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        source = "persisted evaluation scores" if persisted else "evaluation scores"
        raise ValueError(f"{source} must be numeric")
    if not math.isfinite(value):
        source = "persisted evaluation scores" if persisted else "evaluation scores"
        raise ValueError(f"{source} must be finite")
    return float(value)


@dataclass(frozen=True, slots=True)
class EngineDeps:
    """External collaborators injected into one engine instance."""

    reads: ProbeReader
    writes: EvolutionRepositoryProtocol
    prepare_cluster_only: ClusterPrepare | None = None
    full_stages: Mapping[str, StageHandler] = field(
        default_factory=lambda: MappingProxyType({}),
    )
    gateway_factory: GatewayFactory = default_gateway_factory
    events: EvolutionRunEventService | None = None

    def __post_init__(self) -> None:
        """Freeze the stage-handler mapping so later caller mutation cannot drift."""
        object.__setattr__(
            self,
            "full_stages",
            MappingProxyType(dict(self.full_stages)),
        )
