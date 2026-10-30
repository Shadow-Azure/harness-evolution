"""Environment settings and stable codes for the bad-case catalog sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import DatabaseDialect, Settings
from app.errors import ErrorCode


def _settings(**overrides: Any) -> Settings:
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=Path("."),
        jwt_secret=SecretStr("catalog-sync-test-secret"),
        **overrides,
    )


def test_catalog_sync_defaults() -> None:
    """New settings default to the documented catalog-sync bounds."""
    settings = _settings()
    assert settings.bad_case_catalog_sync_interval_seconds == 300
    assert settings.bad_case_catalog_sync_page_size == 200
    assert settings.bad_case_catalog_sync_time_budget_seconds == 300
    assert settings.bad_case_catalog_sync_max_pages == 100
    assert settings.bad_case_query_timeout_seconds == 30
    assert settings.bad_case_query_retry_attempts == 2
    assert settings.bad_case_query_retry_backoff_seconds == 0.25
    assert settings.bad_case_query_configured is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"bad_case_catalog_sync_page_size": 0},
        {"bad_case_catalog_sync_page_size": 201},
        {"bad_case_catalog_sync_max_pages": 0},
        {"bad_case_catalog_sync_interval_seconds": -1},
    ],
)
def test_catalog_sync_bounds_reject_invalid_values(overrides: dict[str, object]) -> None:
    """Out-of-range page size, page count, and interval fail validation."""
    with pytest.raises(ValidationError):
        _settings(**overrides)


def test_bad_case_query_configured_requires_base_url_and_token() -> None:
    """Both endpoint and service token are required to enable the client."""
    assert (
        _settings(
            bad_case_query_base_url="http://query.test",
            bad_case_query_token=SecretStr("token"),
        ).bad_case_query_configured
        is True
    )
    assert _settings(bad_case_query_base_url="http://query.test").bad_case_query_configured is False


def test_bad_case_query_base_url_rejects_credentials_and_query() -> None:
    """The endpoint validator mirrors the existing upstream URL rules."""
    with pytest.raises(ValidationError):
        _settings(bad_case_query_base_url="http://user:pass@query.test")
    with pytest.raises(ValidationError):
        _settings(bad_case_query_base_url="ftp://query.test")


def test_catalog_sync_error_codes_are_stable() -> None:
    """The durable state and client failures expose stable machine codes."""
    assert ErrorCode.BAD_CASE_QUERY_UNAVAILABLE.value == "BAD_CASE_QUERY_UNAVAILABLE"
    assert ErrorCode.BAD_CASE_QUERY_UNAUTHORIZED.value == "BAD_CASE_QUERY_UNAUTHORIZED"
    assert ErrorCode.BAD_CASE_QUERY_INVALID_RESPONSE.value == "BAD_CASE_QUERY_INVALID_RESPONSE"
    assert ErrorCode.BAD_CASE_QUERY_TIMEOUT.value == "BAD_CASE_QUERY_TIMEOUT"
    assert ErrorCode.BAD_CASE_QUERY_REQUEST_FAILED.value == "BAD_CASE_QUERY_REQUEST_FAILED"
    assert ErrorCode.BAD_CASE_CATALOG_SYNC_FAILED.value == "BAD_CASE_CATALOG_SYNC_FAILED"
    assert ErrorCode.BAD_CASE_CATALOG_SYNC_INTERRUPTED.value == "BAD_CASE_CATALOG_SYNC_INTERRUPTED"
