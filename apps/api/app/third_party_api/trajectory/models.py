"""Strict client-side models for the upstream trajectory-query contract."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class TrajectoryApiModel(BaseModel):
    """Camel-case upstream payload with unknown fields rejected."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        frozen=True,
    )


class TrajectoryMetadata(TrajectoryApiModel):
    """Optional session metadata returned with or beside a trajectory package."""

    project: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=64)
    started_at: datetime
    ended_at: datetime
    problem_flag: bool = False
    problem_tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_interval(self) -> TrajectoryMetadata:
        """Require timezone-aware ordered timestamps."""
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        if self.ended_at < self.started_at:
            raise ValueError("endedAt must not precede startedAt")
        return self


class TrajectoryTranscript(TrajectoryApiModel):
    """One raw JSONL transcript belonging to a root session."""

    kind: Literal["main", "subagent"]
    agent_id: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    agent_type: str | None = Field(default=None, max_length=64)
    parent_tool_use_id: str | None = Field(default=None, max_length=128)
    lines: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> TrajectoryTranscript:
        """Keep main identity implicit and require child identity."""
        if self.kind == "main" and self.agent_id is not None:
            raise ValueError("main transcript agentId must be null")
        if self.kind == "subagent" and not self.agent_id:
            raise ValueError("subagent transcript agentId must be non-empty")
        if any(any(character in line for character in ("\x00", "\r", "\n")) for line in self.lines):
            raise ValueError("transcript lines must contain exactly one physical line")
        return self


class TrajectoryPackage(TrajectoryApiModel):
    """One root session plus every raw agent transcript."""

    session_id: str = Field(
        min_length=1,
        max_length=36,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    metadata: TrajectoryMetadata | None = None
    transcripts: tuple[TrajectoryTranscript, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_transcript_set(self) -> TrajectoryPackage:
        """Require exactly one main transcript and unique child identities."""
        mains = [item for item in self.transcripts if item.kind == "main"]
        if len(mains) != 1:
            raise ValueError("package must contain exactly one main transcript")
        children = [item.agent_id for item in self.transcripts if item.kind == "subagent"]
        if len(children) != len(set(children)):
            raise ValueError("duplicate subagent transcript identity")
        if self.session_id in children:
            raise ValueError("subagent agentId must differ from sessionId")
        return self


class TrajectoryWindowItem(TrajectoryApiModel):
    """One session summary returned by cursor enumeration."""

    session_id: str = Field(
        min_length=1,
        max_length=36,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    started_at: datetime
    model: str | None = Field(default=None, max_length=64)
    problem_flag: bool = False

    @model_validator(mode="after")
    def validate_timestamp(self) -> TrajectoryWindowItem:
        """Reject a missing timezone before the value enters API/DB code."""
        if self.started_at.tzinfo is None:
            raise ValueError("startedAt must include a timezone")
        return self


class TrajectoryWindow(TrajectoryApiModel):
    """One page of session summaries and its opaque continuation cursor."""

    items: tuple[TrajectoryWindowItem, ...]
    next_cursor: str | None = Field(default=None, max_length=2_048)


class UpstreamItemIssue(TrajectoryApiModel):
    """Sanitized per-session failure retained without upstream response text."""

    session_id: str | None
    code: str
    message: str


class FetchManyResult(TrajectoryApiModel):
    """Successful packages and isolated failures in requested order."""

    packages: tuple[TrajectoryPackage, ...]
    issues: tuple[UpstreamItemIssue, ...]
