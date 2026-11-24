"""Claude upstream implementation of the bad-case sync source.

This subclass owns every upstream difference: the two HTTP clients, Bearer
headers, timeouts, retry counts, backoff, the catalog and session endpoints,
and the synthesis of the session-source envelope for the existing Claude Code
adapter. The service layer sees only ``BadCasePage`` and ``SessionInfo``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

import httpx

from app.third_party_api.bad_case_query.http import HttpBadCaseCatalogSource
from app.third_party_api.bad_case_query.models import BadCasePage
from app.third_party_api.bad_case_sync_source.base import BaseBadCaseSyncSource
from app.third_party_api.bad_case_sync_source.factory import (
    PROVIDER_ENV,
    BadCaseSyncSourceFactory,
)
from app.third_party_api.session_query.http import HttpSessionQuerySource
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import SessionSourceEnvelope

if TYPE_CHECKING:
    from app.config import Settings

CLAUDE_RUNTIME_KEY = "claude-code"


class ClaudeUpstreamEnvelopeFactory:
    """Synthesize the runtime-typed envelope from the two endpoint reads."""

    runtime_key = CLAUDE_RUNTIME_KEY

    def build(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Return one strict envelope whose runtime matches the adapter."""
        return SessionSourceEnvelope.model_validate(
            {
                "schemaVersion": 1,
                "sessionId": session_id,
                "runtime": self.runtime_key,
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
    """Read the Claude upstream catalog and session-query endpoints."""

    provider = "claude-upstream"
    runtime_key = CLAUDE_RUNTIME_KEY

    def __init__(
        self,
        *,
        catalog: HttpBadCaseCatalogSource,
        session: HttpSessionQuerySource,
        envelope: ClaudeUpstreamEnvelopeFactory | None = None,
    ) -> None:
        """Bind the two HTTP-backed readers and the envelope synthesizer."""
        self._catalog = catalog
        self._session = session
        self._envelope = envelope or ClaudeUpstreamEnvelopeFactory()

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build both clients from the documented endpoint settings."""
        if not settings.session_query_configured or not settings.bad_case_query_configured:
            raise ValueError(
                f"{PROVIDER_ENV}=claude-upstream requires both "
                "HE_SESSION_QUERY_* and HE_BAD_CASE_QUERY_* to be configured",
            )
        session_token = settings.session_query_token
        catalog_token = settings.bad_case_query_token
        if session_token is None or catalog_token is None:
            raise RuntimeError("bad-case sync configuration lost a service token")
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
            catalog=HttpBadCaseCatalogSource(
                catalog_client,
                max_retries=settings.bad_case_query_retry_attempts,
                backoff_seconds=settings.bad_case_query_retry_backoff_seconds,
            ),
            session=HttpSessionQuerySource(
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
        """Delegate catalog paging to the paginated HTTP reader."""
        return await self._catalog.fetch_page(
            after_id=after_id,
            offset=offset,
            limit=limit,
        )

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Delegate trajectory reads to the session-query reader."""
        return await self._session.fetch_trajectory(session_id)

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Delegate child lookup to the session-query reader."""
        return await self._session.list_children(session_id)

    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        """Synthesize the envelope consumed by the Claude Code adapter."""
        return self._envelope.build(
            session_id=session_id,
            expected_parent_id=expected_parent_id,
            children=children,
            trajectory=trajectory,
        )

    async def close(self) -> None:
        """Close both owned HTTP clients through their readers."""
        await self._catalog.close()
        await self._session.close()


__all__ = [
    "CLAUDE_RUNTIME_KEY",
    "ClaudeUpstreamBadCaseSyncSource",
    "ClaudeUpstreamEnvelopeFactory",
]
