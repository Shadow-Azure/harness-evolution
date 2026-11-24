"""Routing guards: frozen provider, missing source, and endpoint validation."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.service.acquisition.bad_case_sync import BadCaseRootSyncService
from app.third_party_api.bad_case_query.models import BadCasePage
from app.third_party_api.bad_case_sync_source import (
    BadCaseSyncSourceFactory,
    BaseBadCaseSyncSource,
    ClaudeUpstreamBadCaseSyncSource,
)
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import (
    SessionSourceEnvelope,
    SessionSourceSnapshot,
)


def _settings(**overrides: object) -> Settings:
    """Build settings that never read a repository .env file."""
    return Settings(jwt_secret=SecretStr("routing-guards-signing-secret"), **overrides)  # type: ignore[arg-type]


def _endpoints() -> dict[str, object]:
    """Return the two endpoint credential pairs the switch requires."""
    return {
        "session_query_base_url": "http://session.test",
        "session_query_token": SecretStr("session-token"),
        "bad_case_query_base_url": "http://catalog.test",
        "bad_case_query_token": SecretStr("catalog-token"),
    }


class _StubSource(BaseBadCaseSyncSource):
    """Minimal source whose only interesting fact is its provider id."""

    provider: ClassVar[str] = "stub-upstream"

    @classmethod
    def from_settings(cls, settings: Settings) -> _StubSource:
        raise NotImplementedError("the stub is constructed directly")

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        raise NotImplementedError("the stub never reads catalog pages")

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        raise NotImplementedError("the stub never reads trajectories")

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        raise NotImplementedError("the stub never reads children")

    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        raise NotImplementedError("the stub never synthesizes envelopes")

    async def close(self) -> None:
        return None


def _service(source: BaseBadCaseSyncSource | None) -> BadCaseRootSyncService:
    """Build a service shell; routing never touches the database."""
    return BadCaseRootSyncService(
        database=object(),  # type: ignore[arg-type]
        repository=object(),  # type: ignore[arg-type]
        source=source,
    )


def test_frozen_provider_must_match_the_assembled_source() -> None:
    """A snapshot naming another provider fails instead of re-routing the root."""
    service = _service(_StubSource())
    snapshot = SessionSourceSnapshot(kind="global", provider="claude-upstream")

    with pytest.raises(AppError) as error:
        service._fetcher_for(snapshot)

    assert error.value.code is ErrorCode.SESSION_SOURCE_INVALID_RESPONSE
    assert "not assembled" in error.value.message


def test_frozen_provider_matching_the_assembly_routes_through_the_source() -> None:
    """The same provider routes normally and keeps the source as the fetcher."""
    service = _service(_StubSource())
    snapshot = SessionSourceSnapshot(kind="global", provider="stub-upstream")

    fetcher = service._fetcher_for(snapshot)

    assert fetcher.source is not None
    assert fetcher.source.provider == "stub-upstream"


def test_bare_global_snapshot_routes_to_the_assembled_source() -> None:
    """A legacy snapshot without a provider keeps using whatever is assembled."""
    service = _service(_StubSource())

    fetcher = service._fetcher_for(SessionSourceSnapshot(kind="global"))

    assert fetcher.source is not None


def test_missing_global_source_parks_with_the_unavailable_error() -> None:
    """An off global line leaves the root claimable but unreadable."""
    service = _service(None)

    with pytest.raises(AppError) as error:
        service._fetcher_for(SessionSourceSnapshot(kind="global"))

    assert error.value.status_code == 503
    assert error.value.code is ErrorCode.SESSION_QUERY_UNAVAILABLE


def test_provider_without_endpoint_credentials_fails_at_startup() -> None:
    """The switch alone is not enough: a missing endpoint pair is a config error."""
    settings = _settings(bad_case_sync_provider="claude-upstream")

    with pytest.raises(ValueError) as error:
        BadCaseSyncSourceFactory.create("claude-upstream", settings)

    message = str(error.value)
    assert "HE_BAD_CASE_SYNC_PROVIDER=claude-upstream requires" in message
    assert "HE_SESSION_QUERY_BASE_URL/HE_SESSION_QUERY_TOKEN" in message
    assert "HE_BAD_CASE_QUERY_BASE_URL/HE_BAD_CASE_QUERY_TOKEN" in message


def test_provider_with_partial_credentials_names_the_missing_pair() -> None:
    """Only the missing side is named, so the operator fixes one line."""
    endpoints = _endpoints()
    endpoints.pop("bad_case_query_token")
    settings = _settings(bad_case_sync_provider="claude-upstream", **endpoints)

    with pytest.raises(ValueError) as error:
        BadCaseSyncSourceFactory.create("claude-upstream", settings)

    message = str(error.value)
    assert "HE_BAD_CASE_QUERY_BASE_URL/HE_BAD_CASE_QUERY_TOKEN" in message
    assert "HE_SESSION_QUERY_BASE_URL" not in message


def test_provider_with_both_pairs_builds_the_claude_source() -> None:
    """A complete configuration reaches the registered subclass."""
    settings = _settings(bad_case_sync_provider="claude-upstream", **_endpoints())
    source = BadCaseSyncSourceFactory.from_settings(settings)

    assert isinstance(source, ClaudeUpstreamBadCaseSyncSource)
