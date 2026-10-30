"""Strict models and protocol for the bad-case session-query service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Protocol

from pydantic import Field, RootModel

SessionId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]


class SessionChildren(RootModel[list[SessionId]]):
    """Bare array of directly triggered subagent session ids."""


@dataclass(frozen=True, slots=True)
class SessionTrajectory:
    """Canonical NDJSON trajectory text and its object count."""

    content: str
    line_count: int


class SessionQuerySource(Protocol):
    """Read-only source used by the bad-case root sync service."""

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Return direct child session ids for one agent session."""

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Return one agent's canonical NDJSON trajectory."""

    async def close(self) -> None:
        """Release owned HTTP resources."""
