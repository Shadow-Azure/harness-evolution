"""Factory selection, normalization, and fail-fast registration."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.third_party_api.bad_case_sync_source import (
    BadCaseSyncSourceFactory,
    BaseBadCaseSyncSource,
)
from tests.bad_case_sync_fakes import StubBadCaseSyncSource


def _settings(**overrides: Any) -> Settings:
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=Path("."),
        jwt_secret=SecretStr("factory-test-secret"),
        **cast(Any, overrides),
    )


@pytest.fixture(autouse=True)
def _isolate_registry() -> Iterator[None]:
    saved = dict(BadCaseSyncSourceFactory._registry)
    try:
        yield
    finally:
        BadCaseSyncSourceFactory._registry.clear()
        BadCaseSyncSourceFactory._registry.update(saved)


def test_unset_provider_disables_the_global_line(caplog: pytest.LogCaptureFixture) -> None:
    """Legacy endpoint credentials alone never enable the source line."""
    settings = _settings(
        session_query_base_url="http://session.test",
        session_query_token=SecretStr("token"),
    )
    with caplog.at_level(logging.WARNING):
        source = BadCaseSyncSourceFactory.from_settings(settings)

    assert source is None
    assert any("HE_BAD_CASE_SYNC_PROVIDER" in record.message for record in caplog.records)


def test_unknown_provider_fails_startup() -> None:
    """An unrecognized provider is a composition error, never a silent disable."""
    with pytest.raises(ValueError, match="HE_BAD_CASE_SYNC_PROVIDER"):
        BadCaseSyncSourceFactory.from_settings(_settings(bad_case_sync_provider="unknown"))


def test_duplicate_registration_is_rejected() -> None:
    """Two implementations cannot claim the same provider key."""

    class DuplicateSource(StubBadCaseSyncSource):
        provider = "duplicate-test"

    BadCaseSyncSourceFactory.register(DuplicateSource)

    with pytest.raises(RuntimeError, match="duplicate bad-case sync source provider"):
        BadCaseSyncSourceFactory.register(DuplicateSource)


def test_provider_key_is_normalized() -> None:
    """Whitespace and case do not leak into the registry key."""
    assert (
        BadCaseSyncSourceFactory.provider_key(
            _settings(bad_case_sync_provider="  CLAUDE-Upstream  "),
        )
        == "claude-upstream"
    )
    assert BadCaseSyncSourceFactory.provider_key(_settings()) is None
    assert BadCaseSyncSourceFactory.provider_key(_settings(bad_case_sync_provider="  ")) is None


def test_registered_returns_a_copy() -> None:
    """Diagnostics cannot mutate the live registry."""
    registered = BadCaseSyncSourceFactory.registered()
    assert "claude-upstream" in registered
    assert registered is not BadCaseSyncSourceFactory._registry
    assert isinstance(registered["claude-upstream"], type)
    assert issubclass(registered["claude-upstream"], BaseBadCaseSyncSource)
