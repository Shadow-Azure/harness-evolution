"""Cross-suite API test configuration."""

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def test_signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a deterministic secret unless it overrides Settings directly."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("HE_JWT_SECRET", "api-test-signing-secret")
