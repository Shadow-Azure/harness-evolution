"""Runtime-typed upstream session-source contract and adapter template."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.third_party_api.session_query.models import SessionTrajectory

RUNTIME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,31}$"
SessionSourceId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]


class SessionTrajectoryEnvelope(BaseModel):
    """One runtime-typed trajectory payload inside the envelope."""

    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")

    format: Literal["ndjson"]
    line_count: int = Field(ge=0)
    content: str


class SessionSourceEnvelope(BaseModel):
    """One strict session-information envelope returned by the report's URL."""

    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")

    schema_version: int = Field(ge=1)
    session_id: SessionSourceId
    runtime: str = Field(pattern=RUNTIME_PATTERN)
    runtime_version: str | None = Field(default=None, max_length=64)
    agent_kind: Literal["main", "subagent"]
    parent_session_id: SessionSourceId | None = None
    child_session_ids: list[SessionSourceId] = Field(default_factory=list)
    agent_meta: dict[str, Any] | None = None
    trajectory: SessionTrajectoryEnvelope
    updated_at: datetime | None = None


class SessionSourceSnapshot(BaseModel):
    """The frozen per-root source choice persisted before traversal starts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["report", "global"]
    runtime: str | None = Field(default=None, pattern=RUNTIME_PATTERN)
    session_url_template: str | None = Field(default=None, max_length=2048)
    # Only the global line names the source that fetched the root: the provider
    # is frozen at first claim so a later `.env` change cannot re-route a root.
    provider: str | None = Field(default=None, pattern=RUNTIME_PATTERN)

    @model_validator(mode="after")
    def _require_report_template(self) -> SessionSourceSnapshot:
        """Require a template exactly for report sources and nowhere else."""
        if self.kind == "report" and not self.session_url_template:
            raise ValueError("report source snapshot requires sessionUrlTemplate")
        if self.kind == "report" and self.provider is not None:
            raise ValueError("report source snapshot cannot carry a provider")
        if self.kind == "global" and (
            self.runtime is not None or self.session_url_template is not None
        ):
            raise ValueError("global source snapshot cannot carry report fields")
        return self


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """One runtime-agnostic session projection consumed by root sync."""

    runtime_key: str
    agent_kind: Literal["main", "subagent"]
    parent_agent_id: str | None
    child_session_ids: tuple[str, ...]
    agent_meta: Mapping[str, object] | None
    trajectory: SessionTrajectory
    runtime_version: str | None = None


class BaseSessionSourceAdapter(ABC):
    """Project one envelope onto SessionInfo; subclasses own runtime metadata only."""

    runtime_key: ClassVar[str]

    def project(
        self,
        envelope: SessionSourceEnvelope,
        trajectory: SessionTrajectory,
    ) -> SessionInfo:
        """Validate the runtime-specific metadata slice and build SessionInfo."""
        facts = self.parse_agent_meta(envelope.agent_meta or {})
        agent_meta: dict[str, object] | None
        if envelope.agent_kind == "subagent":
            merged = dict(facts)
            if envelope.parent_session_id is not None:
                merged["parentAgentId"] = envelope.parent_session_id
            agent_meta = merged
        else:
            agent_meta = dict(facts) or None
        return SessionInfo(
            runtime_key=self.runtime_key,
            agent_kind=envelope.agent_kind,
            parent_agent_id=envelope.parent_session_id,
            child_session_ids=tuple(envelope.child_session_ids),
            agent_meta=agent_meta,
            trajectory=trajectory,
            runtime_version=envelope.runtime_version,
        )

    @abstractmethod
    def parse_agent_meta(self, meta: Mapping[str, object]) -> Mapping[str, object]:
        """Interpret the runtime-owned ``agentMeta`` key-value area strictly."""
