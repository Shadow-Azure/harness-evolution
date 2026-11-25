"""Registry-driven evaluation gateway selection with env fallback."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalGatewayConfigError,
)
from app.service.evolution.gateway_factory import build_eval_gateway_factory
from app.third_party_api.eval_gateway.ai_eval_platform import (
    AiEvalPlatformGateway,
)
from app.third_party_api.eval_gateway.factory import EVAL_GATEWAY_MODES
from app.third_party_api.eval_gateway.fake import FakeEvalGateway


def _settings(**overrides: Any) -> Settings:
    """Build one settings snapshot with eval defaults overridable."""
    values: dict[str, Any] = {"jwt_secret": SecretStr("m12-03-gateway-secret")}
    values.update(overrides)
    return Settings(**values)


def test_registry_lists_the_builtin_providers() -> None:
    """The registry is the single source for legal HE_EVAL_MODE values."""
    assert EVAL_GATEWAY_MODES == ("fake", "ai-eval-platform")


def test_unknown_env_mode_fails_startup_validation() -> None:
    """An unknown HE_EVAL_MODE fails settings construction, not a later call."""
    with pytest.raises(ValidationError, match="HE_EVAL_MODE"):
        _settings(eval_mode="http")


def test_factory_defaults_to_the_fake_gateway() -> None:
    """Without any mode configuration the deterministic gateway stays default."""
    factory = build_eval_gateway_factory(_settings())

    gateway = factory(EvalGatewayConfig.from_mapping({}))

    assert isinstance(gateway, FakeEvalGateway)


def test_factory_selects_the_registered_platform_from_the_run_snapshot() -> None:
    """The frozen run snapshot mode wins over the process-wide default."""
    factory = build_eval_gateway_factory(_settings())

    gateway = factory(
        EvalGatewayConfig.from_mapping(
            {"mode": "ai-eval-platform", "baseUrl": "http://127.0.0.1:9"},
        ),
    )

    assert isinstance(gateway, AiEvalPlatformGateway)


def test_factory_falls_back_to_env_mode_and_base_url() -> None:
    """Global HE_EVAL_* settings opt runs in without per-run config."""
    factory = build_eval_gateway_factory(
        _settings(
            eval_mode="ai-eval-platform",
            eval_base_url="http://127.0.0.1:9/",
        ),
    )

    gateway = factory(EvalGatewayConfig.from_mapping({}))

    assert isinstance(gateway, AiEvalPlatformGateway)
    assert gateway.config["baseUrl"] == "http://127.0.0.1:9"


def test_platform_mode_without_base_url_fails_explicitly() -> None:
    """Missing baseUrl is a configuration error, never a silent fake fallback."""
    factory = build_eval_gateway_factory(_settings(eval_mode="ai-eval-platform"))

    with pytest.raises(EvalGatewayConfigError, match="baseUrl"):
        factory(EvalGatewayConfig.from_mapping({"mode": "ai-eval-platform"}))


def test_run_snapshot_base_url_overrides_env() -> None:
    """The run snapshot baseUrl wins over the global env value."""
    factory = build_eval_gateway_factory(
        _settings(
            eval_mode="ai-eval-platform",
            eval_base_url="http://env.invalid",
        ),
    )

    gateway = factory(
        EvalGatewayConfig.from_mapping(
            {"mode": "ai-eval-platform", "baseUrl": "http://run.invalid"},
        ),
    )

    assert gateway.config["baseUrl"] == "http://run.invalid"


def test_platform_base_url_rejects_embedded_credentials() -> None:
    """A baseUrl with credentials or a query is a configuration error."""
    factory = build_eval_gateway_factory(_settings(eval_mode="ai-eval-platform"))

    with pytest.raises(EvalGatewayConfigError, match="without credentials"):
        factory(
            EvalGatewayConfig.from_mapping(
                {
                    "mode": "ai-eval-platform",
                    "baseUrl": "https://user:secret@platform.invalid/api?x=1",
                },
            ),
        )


def test_api_key_ref_resolves_from_the_environment() -> None:
    """The snapshot carries the env var name; the factory resolves its value."""
    factory = build_eval_gateway_factory(_settings(eval_mode="ai-eval-platform"))

    gateway = factory(
        EvalGatewayConfig.from_mapping(
            {
                "mode": "ai-eval-platform",
                "baseUrl": "http://run.invalid",
                "apiKeyRef": "HE_EVAL_API_KEY",
            },
        ),
        env={"HE_EVAL_API_KEY": "stub-token"},
    )

    assert gateway._auth_header == {"Authorization": "Bearer stub-token"}  # type: ignore[attr-defined]


def test_dangling_api_key_ref_fails_explicitly() -> None:
    """A snapshot pointing at an unset variable blocks instead of unauth calls."""
    factory = build_eval_gateway_factory(_settings(eval_mode="ai-eval-platform"))

    with pytest.raises(EvalGatewayConfigError, match="apiKeyRef"):
        factory(
            EvalGatewayConfig.from_mapping(
                {
                    "mode": "ai-eval-platform",
                    "baseUrl": "http://run.invalid",
                    "apiKeyRef": "MISSING_EVAL_KEY",
                },
            ),
            env={},
        )
