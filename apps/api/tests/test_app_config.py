"""Brand configuration defaults and the public app-config endpoint."""

from typing import Any, cast

import httpx
import pytest

from app.config import (
    DEFAULT_BRAND_NAME,
    DEFAULT_BRAND_SUBTITLE,
    DatabaseDialect,
    Settings,
)
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_brand_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep host brand overrides out of the deterministic settings cases."""
    monkeypatch.delenv("HE_BRAND_NAME", raising=False)
    monkeypatch.delenv("HE_BRAND_SUBTITLE", raising=False)


def settings_with(**values: Any) -> Settings:
    """Build settings with the offline SQLite defaults used by API tests."""
    return Settings(db_dialect=DatabaseDialect.SQLITE, **values)


def test_brand_defaults_apply_when_unset() -> None:
    """An unconfigured deployment keeps the shipped brand copy."""
    settings = settings_with()

    assert settings.brand_name == DEFAULT_BRAND_NAME
    assert settings.brand_subtitle == DEFAULT_BRAND_SUBTITLE
    assert settings.brand_name == "Harness Evolution"
    assert settings.brand_subtitle == "轨迹诊断与自进化"


def test_blank_brand_values_fall_back_to_defaults() -> None:
    """Empty strings and whitespace-only overrides never produce an empty brand."""
    empty = settings_with(brand_name="", brand_subtitle="")
    blank = settings_with(brand_name="   ", brand_subtitle="\t\n  ")
    missing = settings_with(brand_name=cast(Any, None), brand_subtitle=cast(Any, None))

    for settings in (empty, blank, missing):
        assert settings.brand_name == DEFAULT_BRAND_NAME
        assert settings.brand_subtitle == DEFAULT_BRAND_SUBTITLE


def test_only_one_configured_brand_field_keeps_the_other_default() -> None:
    """The two overrides are independent."""
    settings = settings_with(brand_name="Acme Diagnostics")

    assert settings.brand_name == "Acme Diagnostics"
    assert settings.brand_subtitle == DEFAULT_BRAND_SUBTITLE


def test_configured_brand_values_are_trimmed() -> None:
    """Surrounding whitespace is stripped instead of rendered."""
    settings = settings_with(
        brand_name="  Acme Diagnostics  ",
        brand_subtitle="\tAcme Self-Evolution\n",
    )

    assert settings.brand_name == "Acme Diagnostics"
    assert settings.brand_subtitle == "Acme Self-Evolution"


def test_brand_reads_the_he_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment overrides arrive through the documented HE_ names."""
    monkeypatch.setenv("HE_BRAND_NAME", " Acme Diagnostics ")
    monkeypatch.setenv("HE_BRAND_SUBTITLE", "Acme Self-Evolution")

    settings = settings_with()

    assert settings.brand_name == "Acme Diagnostics"
    assert settings.brand_subtitle == "Acme Self-Evolution"


async def test_app_config_is_public_and_returns_settings_values() -> None:
    """The endpoint is readable without a token and mirrors the settings."""
    app = create_app(
        settings_with(
            brand_name="Acme Diagnostics",
            brand_subtitle="Acme Self-Evolution",
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/app-config")

    assert response.status_code == 200
    assert response.json() == {
        "brand": {
            "name": "Acme Diagnostics",
            "subtitle": "Acme Self-Evolution",
        },
    }
    assert app.state.settings.brand_name == "Acme Diagnostics"
    assert app.state.settings.brand_subtitle == "Acme Self-Evolution"
