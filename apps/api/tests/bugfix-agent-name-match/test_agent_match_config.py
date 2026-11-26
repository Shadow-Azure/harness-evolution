"""The opt-in agent name-match switch reads the documented environment name."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import DatabaseDialect, Settings

SIGNING_KEY = "agent-name-match-test-signing-secret-with-sufficient-length"


def _settings(**values: Any) -> Settings:
    """Build offline settings without borrowing a deployment's environment file."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr(SIGNING_KEY),
        **values,
    )


def test_agent_name_match_defaults_to_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unconfigured deployment keeps body-hash matching."""
    monkeypatch.delenv("HE_AGENT_MATCH_BY_NAME", raising=False)

    assert _settings().agent_match_by_name is False


def test_agent_name_match_reads_the_he_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only ``HE_AGENT_MATCH_BY_NAME`` turns the exception on."""
    monkeypatch.setenv("HE_AGENT_MATCH_BY_NAME", "true")
    assert _settings().agent_match_by_name is True

    monkeypatch.setenv("HE_AGENT_MATCH_BY_NAME", "false")
    assert _settings().agent_match_by_name is False


def test_agent_name_match_rejects_a_non_boolean_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid boolean fails startup validation instead of silently defaulting."""
    monkeypatch.setenv("HE_AGENT_MATCH_BY_NAME", "sometimes")

    with pytest.raises(ValidationError):
        _settings()
