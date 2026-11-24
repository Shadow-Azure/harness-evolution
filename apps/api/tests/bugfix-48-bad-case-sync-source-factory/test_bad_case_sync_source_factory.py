"""Factory switch semantics for the bad-case sync source."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.third_party_api.bad_case_sync_source import (
    BadCaseSyncSourceFactory,
    ClaudeUpstreamBadCaseSyncSource,
)

FACTORY_LOGGER = "app.third_party_api.bad_case_sync_source.factory"


def _settings(**overrides: Any) -> Settings:
    """Build minimal settings without reading a repository .env file."""
    return Settings(
        jwt_secret=SecretStr("bad-case-sync-source-test-secret"),
        **overrides,
    )


def _configured_endpoints() -> dict[str, Any]:
    """Return the retired endpoint credentials a pre-upgrade deployment carries."""
    return {
        "session_query_base_url": "http://session.test",
        "session_query_token": SecretStr("session-token"),
        "bad_case_query_base_url": "http://catalog.test",
        "bad_case_query_token": SecretStr("catalog-token"),
    }


def test_claude_upstream_is_registered_by_importing_the_package() -> None:
    """Package import is the only registration step a deployment needs."""
    assert "claude-upstream" in BadCaseSyncSourceFactory.registered_keys()


def test_unset_provider_keeps_the_global_line_off() -> None:
    """No provider means no source, even when the legacy endpoints exist."""
    assert BadCaseSyncSourceFactory.from_settings(_settings()) is None
    assert BadCaseSyncSourceFactory.from_settings(_settings(**_configured_endpoints())) is None


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_provider_is_normalized_to_unset(blank: str) -> None:
    """A template-expanded empty value behaves exactly like an unset value."""
    settings = _settings(bad_case_sync_provider=blank)

    assert settings.bad_case_sync_provider is None
    assert BadCaseSyncSourceFactory.provider_key(settings) is None
    assert BadCaseSyncSourceFactory.from_settings(settings) is None


def test_provider_key_normalizes_case_and_padding() -> None:
    """The switch is case-insensitive so a hand-edited .env still resolves."""
    settings = _settings(bad_case_sync_provider="  Claude-Upstream ")

    assert settings.bad_case_sync_provider == "claude-upstream"
    assert BadCaseSyncSourceFactory.provider_key(settings) == "claude-upstream"


def test_unknown_provider_fails_with_the_allowed_values() -> None:
    """An unknown provider is a startup failure, never a silent fallback."""
    settings = _settings(bad_case_sync_provider="other-upstream")

    with pytest.raises(ValueError) as error:
        BadCaseSyncSourceFactory.from_settings(settings)

    message = str(error.value)
    assert message == (
        "unknown bad-case sync provider: 'other-upstream'; expected one of: claude-upstream"
    )


def test_register_returns_the_class_and_rejects_a_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A duplicate provider identity fails registration instead of overwriting."""
    monkeypatch.setattr(BadCaseSyncSourceFactory, "_registry", {})

    class FakeSource(ClaudeUpstreamBadCaseSyncSource):
        provider = "fake-upstream"

    assert BadCaseSyncSourceFactory.register(FakeSource) is FakeSource
    assert BadCaseSyncSourceFactory.registered_keys() == ("fake-upstream",)

    with pytest.raises(ValueError, match="duplicate bad-case sync provider: fake-upstream"):
        BadCaseSyncSourceFactory.register(FakeSource)

    assert BadCaseSyncSourceFactory.registered_keys() == ("fake-upstream",)


def test_register_rejects_an_empty_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty provider key cannot be selected from configuration."""
    monkeypatch.setattr(BadCaseSyncSourceFactory, "_registry", {})

    class EmptyProviderSource(ClaudeUpstreamBadCaseSyncSource):
        provider = ""

    with pytest.raises(ValueError, match="provider must not be empty"):
        BadCaseSyncSourceFactory.register(EmptyProviderSource)


def test_legacy_endpoints_without_a_provider_warn_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The upgrade warning names the switch instead of guessing an intent."""
    settings = _settings(**_configured_endpoints())

    with caplog.at_level(logging.WARNING, logger=FACTORY_LOGGER):
        assert BadCaseSyncSourceFactory.from_settings(settings) is None

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "HE_BAD_CASE_SYNC_PROVIDER" in warnings[0].getMessage()
    assert getattr(warnings[0], "event", None) == "bad_case_sync.provider_unset"


def test_unset_provider_without_legacy_endpoints_is_quiet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A fresh deployment with no endpoint credentials gets no warning."""
    with caplog.at_level(logging.WARNING, logger=FACTORY_LOGGER):
        assert BadCaseSyncSourceFactory.from_settings(_settings()) is None

    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


@pytest.mark.asyncio
async def test_create_builds_the_named_source() -> None:
    """The explicit create seam resolves the same subclass as the settings seam."""
    source = BadCaseSyncSourceFactory.create(
        "claude-upstream",
        _settings(**_configured_endpoints()),
    )
    try:
        assert isinstance(source, ClaudeUpstreamBadCaseSyncSource)
        assert source.provider == "claude-upstream"
    finally:
        await source.close()
