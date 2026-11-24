"""Claude-upstream implementation of the bad-case sync source.

This is the only file in the module that knows ``httpx``: base URLs, Bearer
tokens, timeouts, retries, backoff, and the two process-wide request locks stay
behind :class:`ClaudeUpstreamBadCaseSyncSource`. Everything above it sees only
``BadCasePage`` and ``SessionInfo``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

import httpx

from app.third_party_api.bad_case_query.http import HttpBadCaseCatalogSource
from app.third_party_api.bad_case_query.models import BadCasePage
from app.third_party_api.bad_case_sync_source.base import BaseBadCaseSyncSource
from app.third_party_api.bad_case_sync_source.factory import BadCaseSyncSourceFactory
from app.third_party_api.session_query.http import HttpSessionQuerySource
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import SessionSourceEnvelope

if TYPE_CHECKING:
    from app.config import Settings

SCHEMA_VERSION = 1
"""Envelope schema version this source synthesizes; matches the report client."""


class ClaudeUpstreamEnvelopeFactory:
    """Pure synthesis of the envelope the Claude Code adapter can project.

    No HTTP call and no runtime state: the two upstream endpoints plus the
    traversal parent fully determine the value, which keeps the projection
    equivalent to the report path's envelope for the same session.
    """

    @staticmethod
    def build(
        *,
        runtime_key: str,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Return one validated envelope for main and subagent sessions alike."""
        return SessionSourceEnvelope.model_validate(
            {
                "schemaVersion": SCHEMA_VERSION,
                "sessionId": session_id,
                "runtime": runtime_key,
                "runtimeVersion": None,
                "agentKind": "main" if expected_parent_id is None else "subagent",
                "parentSessionId": expected_parent_id,
                "childSessionIds": list(children),
                "agentMeta": {},
                "trajectory": {
                    "format": "ndjson",
                    "lineCount": trajectory.line_count,
                    "content": trajectory.content,
                },
                "updatedAt": None,
            },
        )


@BadCaseSyncSourceFactory.register
class ClaudeUpstreamBadCaseSyncSource(BaseBadCaseSyncSource):
    """Claude upstream catalog and session query behind the parent template."""

    provider = "claude-upstream"
    runtime_key: ClassVar[str] = "claude-code"
    _envelope: ClassVar[type[ClaudeUpstreamEnvelopeFactory]] = ClaudeUpstreamEnvelopeFactory

    def __init__(
        self,
        catalog: HttpBadCaseCatalogSource,
        session: HttpSessionQuerySource,
    ) -> None:
        """Bind the two upstream clients this source owns and later closes."""
        self._catalog = catalog
        self._session = session

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build both clients and both sources from the deployment settings.

        Client parameters mirror the previous composition-root blocks exactly:
        one base URL, one Bearer token, one timeout, and no redirect following
        per endpoint, with the retry budget read from the same settings.
        """
        session_token = settings.session_query_token
        if session_token is None:
            raise RuntimeError("session query configuration lost its token")
        catalog_token = settings.bad_case_query_token
        if catalog_token is None:
            raise RuntimeError("bad-case query configuration lost its token")
        session_client = httpx.AsyncClient(
            base_url=settings.session_query_base_url or "",
            headers={"Authorization": f"Bearer {session_token.get_secret_value()}"},
            timeout=settings.session_query_timeout_seconds,
            follow_redirects=False,
        )
        catalog_client = httpx.AsyncClient(
            base_url=settings.bad_case_query_base_url or "",
            headers={"Authorization": f"Bearer {catalog_token.get_secret_value()}"},
            timeout=settings.bad_case_query_timeout_seconds,
            follow_redirects=False,
        )
        return cls(
            HttpBadCaseCatalogSource(
                catalog_client,
                max_retries=settings.bad_case_query_retry_attempts,
                backoff_seconds=settings.bad_case_query_retry_backoff_seconds,
            ),
            HttpSessionQuerySource(
                session_client,
                max_retries=settings.session_query_retry_attempts,
                backoff_seconds=settings.session_query_retry_backoff_seconds,
            ),
        )

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Delegate one catalog page to the upstream query client."""
        return await self._catalog.fetch_page(after_id=after_id, offset=offset, limit=limit)

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Delegate one canonical trajectory read to the upstream client."""
        return await self._session.fetch_trajectory(session_id)

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Delegate one direct-children read to the upstream client."""
        return await self._session.list_children(session_id)

    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Synthesize the Claude envelope through the pure envelope factory."""
        return self._envelope.build(
            runtime_key=self.runtime_key,
            session_id=session_id,
            expected_parent_id=expected_parent_id,
            children=children,
            trajectory=trajectory,
        )

    async def close(self) -> None:
        """Close both owned clients, even when the first close fails."""
        try:
            await self._catalog.close()
        finally:
            await self._session.close()


__all__ = [
    "ClaudeUpstreamBadCaseSyncSource",
    "ClaudeUpstreamEnvelopeFactory",
]
