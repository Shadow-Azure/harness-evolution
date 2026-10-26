"""Dependencies and immutable values used by evolution engines."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from app.db.models.evolution import (
    ClusterWrite,
    EvolutionFinalRecord,
    EvolutionRunRecord,
    ProbeClusterRecord,
)
from app.db.models.jobs import JobRunRecord


class ConfigError(RuntimeError):
    """Raised when an engine selection or stage capability is invalid."""


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


@dataclass(frozen=True, slots=True)
class DefaultEvalGateway:
    """Inert gateway carrying configuration until the real integration lands."""

    config: EvalGatewayConfig


type GatewayFactory = Callable[[EvalGatewayConfig], EvalGateway]
type StageHandler = Callable[[JobRunRecord], Awaitable[None]]
type ClusterPrepare = Callable[
    [EvolutionRunRecord, Mapping[str, Any]],
    Awaitable[None],
]


def default_gateway_factory(config: EvalGatewayConfig) -> EvalGateway:
    """Build the inert gateway used before real evaluation configuration exists."""
    return DefaultEvalGateway(config=config)


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

    def __post_init__(self) -> None:
        """Freeze the stage-handler mapping so later caller mutation cannot drift."""
        object.__setattr__(
            self,
            "full_stages",
            MappingProxyType(dict(self.full_stages)),
        )
