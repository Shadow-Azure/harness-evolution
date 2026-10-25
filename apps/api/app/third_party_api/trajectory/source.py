"""Protocol implemented by trajectory-query sources."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.third_party_api.trajectory.models import (
    FetchManyResult,
    TrajectoryPackage,
    TrajectoryWindowItem,
)


class TrajectorySource(Protocol):
    """Read-only source used by the acquisition pull job."""

    async def fetch(self, session_id: str) -> TrajectoryPackage:
        """Fetch and validate one root trajectory package."""

    async def list_window(
        self,
        *,
        from_date: date,
        to_date: date,
        problem_only: bool,
        cursor: str | None,
    ) -> tuple[TrajectoryWindowItem, ...]:
        """Enumerate every session summary in the date window."""

    async def fetch_many(self, session_ids: list[str]) -> FetchManyResult:
        """Fetch packages while isolating per-session failures."""

    async def close(self) -> None:
        """Release owned HTTP resources."""
