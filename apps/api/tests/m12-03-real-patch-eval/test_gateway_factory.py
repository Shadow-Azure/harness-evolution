"""Mode-driven evaluation gateway selection with env fallback."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.service.evolution.engine.contracts import (
    ConfigError,
    EvalGatewayConfig,
    EvalGatewayConfigError,
    FakeEvalGateway,
)
from app.service.evolution.gateway_factory import build_eval_gateway_factory
from app.third_party_api.eval_gateway.http import HttpEvalGateway


def _settings(**overrides: Any) -> Settings:
    """Build one settings snapshot with eval defaults overridable."""
    values: dict[str, Any] = {"jwt_secret": SecretStr("m12-03-gateway-secret")}
    values.update(overrides)
    return Settings(**values)


def test_factory_defaults_to_the_fake_gateway() -> None:
    """Without any mode configuration the deterministic gateway stays default."""
    factory = build_eval_gateway_factory(_settings())

    gateway = factory(EvalGatewayConfig.from_mapping({}))

    assert isinstance(gateway, FakeEvalGateway)


def test_factory_selects_http_from_run_snapshot() -> None:
    """The frozen run snapshot mode wins over the process-wide default."""
    factory = build_eval_gateway_factory(_settings())

    gateway = factory(
        EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": "http://127.0.0.1:9"}),
    )

    assert type(gateway).__name__ == "HttpEvalGateway"


def test_factory_falls_back_to_env_mode_and_base_url() -> None:
    """Global HE_EVAL_* settings opt runs in without per-run config."""
    factory = build_eval_gateway_factory(
        _settings(eval_mode="http", eval_base_url="http://127.0.0.1:9/"),
    )

    gateway = factory(EvalGatewayConfig.from_mapping({}))

    assert type(gateway).__name__ == "HttpEvalGateway"
    assert isinstance(gateway, HttpEvalGateway)
    assert gateway.config["baseUrl"] == "http://127.0.0.1:9"


def test_http_mode_without_base_url_fails_explicitly() -> None:
    """Missing baseUrl is a configuration error, never a silent fake fallback."""
    factory = build_eval_gateway_factory(_settings(eval_mode="http"))

    with pytest.raises(EvalGatewayConfigError, match="HE_EVAL_BASE_URL"):
        factory(EvalGatewayConfig.from_mapping({"mode": "http"}))


def test_run_snapshot_base_url_overrides_env() -> None:
    """The run snapshot baseUrl wins over the global env value."""
    factory = build_eval_gateway_factory(
        _settings(eval_mode="http", eval_base_url="http://env.invalid"),
    )

    gateway = factory(
        EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": "http://run.invalid"}),
    )

    assert gateway.config["baseUrl"] == "http://run.invalid"


def test_api_key_ref_is_an_indirect_env_reference() -> None:
    """apiKeyRef names an env var; the secret itself never enters the config."""
    factory = build_eval_gateway_factory(_settings())

    gateway = factory(
        EvalGatewayConfig.from_mapping(
            {
                "mode": "http",
                "baseUrl": "http://127.0.0.1:9",
                "apiKeyRef": "HE_EVAL_API_KEY",
            },
        ),
        env={"HE_EVAL_API_KEY": "stub-secret"},
    )

    assert isinstance(gateway, HttpEvalGateway)
    assert gateway.auth_header == {"Authorization": "Bearer stub-secret"}


def test_missing_api_key_env_fails_explicitly() -> None:
    """A dangling apiKeyRef is a configuration error, not an anonymous call."""
    factory = build_eval_gateway_factory(_settings())

    with pytest.raises(EvalGatewayConfigError, match="HE_EVAL_API_KEY"):
        factory(
            EvalGatewayConfig.from_mapping(
                {
                    "mode": "http",
                    "baseUrl": "http://127.0.0.1:9",
                    "apiKeyRef": "HE_EVAL_API_KEY",
                },
            ),
            env={},
        )


def test_settings_api_key_is_used_without_api_key_ref() -> None:
    """HE_EVAL_API_KEY works alone for deployments that only inject the secret."""
    factory = build_eval_gateway_factory(_settings(eval_api_key=SecretStr("env-secret")))

    gateway = factory(
        EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": "http://127.0.0.1:9"}),
    )

    assert isinstance(gateway, HttpEvalGateway)
    assert gateway.auth_header == {"Authorization": "Bearer env-secret"}


def test_unknown_mode_fails_explicitly() -> None:
    """Unknown gateway modes fail loudly instead of silently degrading."""
    factory = build_eval_gateway_factory(_settings())

    with pytest.raises(ConfigError, match="mode"):
        factory(EvalGatewayConfig.from_mapping({"mode": "grpc"}))
    with pytest.raises(ConfigError, match="mode"):
        build_eval_gateway_factory(_settings(), fallback_mode="grpc")(
            EvalGatewayConfig.from_mapping({}),
        )


def test_settings_reject_unknown_eval_mode() -> None:
    """The env-backed default mode only accepts registered gateways."""
    with pytest.raises(Exception):
        Settings(jwt_secret=SecretStr("m12-03-gateway-secret"), eval_mode="grpc")


def test_extra_config_keys_do_not_change_the_fake_gateway() -> None:
    """Snapshot keys added for http selection keep the fake behavior intact."""
    factory = build_eval_gateway_factory(_settings())

    gateway = factory(
        EvalGatewayConfig.from_mapping(
            {"mode": "fake", "baseUrl": "http://ignored.invalid", "currentScore": 70.0},
        ),
    )

    assert isinstance(gateway, FakeEvalGateway)
