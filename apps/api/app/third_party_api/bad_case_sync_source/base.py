"""Parent contract and shared templates for every bad-case sync source.

The service layer depends only on this type. A source answers two questions:
one validated catalog page, and one runtime-agnostic session projection for a
root or agent. Upstream-specific endpoints, credentials, retries, and envelope
synthesis live in subclasses; traversal, leases, and persistence stay in the
sync service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Self

from app.third_party_api.bad_case_query.models import BadCasePage
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import (
    SessionInfo,
    SessionSourceEnvelope,
    SessionSourceSnapshot,
)
from app.third_party_api.session_source.factory import SessionSourceFactory

if TYPE_CHECKING:
    from app.config import Settings


class BaseBadCaseSyncSource(ABC):
    """Trigger both upstream reads from one replaceable provider implementation."""

    provider: ClassVar[str]

    async def fetch_bad_case_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Return one validated catalog page with ids greater than ``after_id``."""
        return await self.fetch_page(after_id=after_id, offset=offset, limit=limit)

    @abstractmethod
    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Return one validated catalog page from the provider endpoint."""

    async def fetch_session(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        snapshot: SessionSourceSnapshot,
    ) -> SessionInfo:
        """Return one runtime-agnostic session projection for root traversal.

        Subclasses fetch the raw trajectory and child ids, then synthesize the
        same envelope shape the report path already accepts. Projection reuses
        the registered session-source adapter, so runtime metadata handling is
        not duplicated here.
        """
        trajectory = await self.fetch_trajectory(session_id)
        children = await self.list_children(session_id)
        envelope = self.build_envelope(
            session_id=session_id,
            expected_parent_id=expected_parent_id,
            children=children,
            trajectory=trajectory,
        )
        return SessionSourceFactory.create(envelope.runtime).project(
            envelope,
            trajectory,
        )

    @abstractmethod
    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Return one agent's canonical NDJSON trajectory."""

    @abstractmethod
    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Return the direct child session ids of one agent session."""

    @abstractmethod
    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Synthesize the runtime-typed envelope the adapter projects."""

    @abstractmethod
    async def close(self) -> None:
        """Release every resource this source owns."""

    @classmethod
    @abstractmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build the provider from deployment settings."""


__all__ = ["BaseBadCaseSyncSource"]
