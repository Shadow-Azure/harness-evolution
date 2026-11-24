"""Parent for every bad-case sync source: two template methods, subclasses implement.

The parent owns *when* an upstream call happens and *what* shape comes back
(:class:`BadCasePage` and :class:`SessionInfo`, both already runtime-agnostic).
A subclass owns *how* one upstream is reached: endpoints, authentication,
retries, and the envelope synthesis that lets the existing session-source
adapters project one session. Services depend on this type only, so a new
upstream is one subclass plus one factory registration.
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
    """Parent for every bad-case sync source; template methods trigger, subclasses implement."""

    provider: ClassVar[str]

    @classmethod
    @abstractmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build one source from deployment settings, owning every client it creates."""

    async def fetch_bad_case_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Template: one validated catalog page with ids greater than ``after_id``."""
        return await self.fetch_page(after_id=after_id, offset=offset, limit=limit)

    @abstractmethod
    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Return one validated catalog page read from this upstream."""

    async def fetch_session(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        snapshot: SessionSourceSnapshot,
    ) -> SessionInfo:
        """Template: one runtime-agnostic session projection for root sync.

        The two endpoint reads and the envelope synthesis stay in the subclass;
        the projection then reuses the existing ``SessionSourceFactory`` chain, so
        a sync source never re-implements runtime metadata handling. ``snapshot``
        carries the frozen per-root source choice and exists so this signature
        matches the report path's fetcher; the source itself is already bound to
        one provider at assembly time.
        """
        trajectory = await self.fetch_trajectory(session_id)
        children = await self.list_children(session_id)
        envelope = self.build_envelope(
            session_id=session_id,
            expected_parent_id=expected_parent_id,
            children=children,
            trajectory=trajectory,
        )
        return SessionSourceFactory.create(envelope.runtime).project(envelope, trajectory)

    @abstractmethod
    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Return one canonical NDJSON trajectory for ``session_id``."""

    @abstractmethod
    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Return the direct child session ids triggered by ``session_id``."""

    @abstractmethod
    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Synthesize the envelope the registered runtime adapter can project."""

    @abstractmethod
    async def close(self) -> None:
        """Release every upstream resource this source owns."""


__all__ = ["BaseBadCaseSyncSource"]
