"""Cross-suite API test configuration."""

import pytest


@pytest.fixture(autouse=True)
def test_signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a deterministic secret unless it overrides Settings directly."""
    monkeypatch.setenv("HE_JWT_SECRET", "api-test-signing-secret")
