"""Cross-suite API test configuration."""

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_api_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an offline provider and a deterministic signing secret by default."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("AI_AGENT_PROVIDER", "fake")
    monkeypatch.setenv("HE_JWT_SECRET", "api-test-signing-secret")
