"""Shared stubs for the bad-case sync-source tests.

Real tests override only the template hooks they exercise; the remaining
abstract methods fail loudly so an accidental call is visible.
"""

from __future__ import annotations

from typing import ClassVar, Self

from app.config import Settings
from app.third_party_api.bad_case_query.models import BadCasePage
from app.third_party_api.bad_case_sync_source import BaseBadCaseSyncSource
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import SessionSourceEnvelope


class StubBadCaseSyncSource(BaseBadCaseSyncSource):
    """Abstract-method filler for tests that override the template they need."""

    provider: ClassVar[str] = "stub"

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Fail when a test did not provide catalog paging."""
        raise NotImplementedError

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Fail when a test did not provide a trajectory."""
        raise NotImplementedError

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Fail when a test did not provide child ids."""
        raise NotImplementedError

    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Fail when a test did not provide an envelope."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release nothing by default."""
        return None

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Test doubles are constructed directly, never from environment."""
        raise NotImplementedError
