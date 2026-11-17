"""Mode-driven evaluation gateway selection for the composition root.

The frozen run snapshot wins; global ``HE_EVAL_*`` settings fill the gaps.
Future evaluation platforms only add a subclass plus configuration — business
code stays untouched.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from app.service.evolution.engine.contracts import (
    EvalGateway,
    EvalGatewayConfig,
    EvalGatewayConfigError,
    FakeEvalGateway,
)
from app.third_party_api.eval_gateway.http import HttpEvalGateway

if TYPE_CHECKING:
    from app.config import Settings

EVAL_GATEWAY_MODES = ("fake", "http")
_DEFAULT_API_KEY_REF = "HE_EVAL_API_KEY"


def build_eval_gateway_factory(
    settings: Settings,
    *,
    fallback_mode: str | None = None,
) -> Callable[..., EvalGateway]:
    """Bind one settings snapshot into a per-run gateway constructor."""
    default_mode = fallback_mode or settings.eval_mode
    env_base_url = settings.eval_base_url
    env_api_key = (
        settings.eval_api_key.get_secret_value() if settings.eval_api_key is not None else None
    )

    def factory(
        config: EvalGatewayConfig,
        *,
        env: Mapping[str, str] | None = None,
    ) -> EvalGateway:
        """Resolve one gateway from the run snapshot with env fallback."""
        environment = os.environ if env is None else env
        configured = config.get("mode")
        mode = configured if isinstance(configured, str) and configured else default_mode
        if mode == "fake":
            return FakeEvalGateway(config=config)
        if mode != "http":
            raise EvalGatewayConfigError(
                f"unknown evaluation gateway mode: {mode}",
            )
        return _http_gateway(
            config,
            environment=environment,
            env_base_url=env_base_url,
            env_api_key=env_api_key,
        )

    return factory


def _http_gateway(
    config: EvalGatewayConfig,
    *,
    environment: Mapping[str, str],
    env_base_url: str | None,
    env_api_key: str | None,
) -> HttpEvalGateway:
    """Build the HTTP gateway after validating its endpoint and credentials."""
    configured_url = config.get("baseUrl")
    base_url = (
        configured_url
        if isinstance(configured_url, str) and configured_url.strip()
        else env_base_url
    )
    if not base_url:
        raise EvalGatewayConfigError(
            "evaluation gateway mode http requires a baseUrl (run eval config or HE_EVAL_BASE_URL)",
        )
    auth_header = _resolve_auth_header(
        config,
        environment=environment,
        env_api_key=env_api_key,
    )
    merged = dict(config)
    merged["baseUrl"] = base_url.rstrip("/")
    return HttpEvalGateway(
        config=EvalGatewayConfig.from_mapping(merged),
        auth_header=auth_header,
    )


def _resolve_auth_header(
    config: EvalGatewayConfig,
    *,
    environment: Mapping[str, str],
    env_api_key: str | None,
) -> Mapping[str, str] | None:
    """Resolve the bearer header from an indirect env reference first.

    ``apiKeyRef`` stores the environment variable name, never the secret; the
    process-level ``HE_EVAL_API_KEY`` value is the fallback for deployments
    that only inject the secret itself.
    """
    ref = config.get("apiKeyRef")
    if isinstance(ref, str) and ref.strip():
        name = ref.strip()
        value = environment.get(name, "").strip()
        if not value:
            raise EvalGatewayConfigError(
                f"evaluation gateway apiKeyRef points to unset env var: {name}",
            )
        return {"Authorization": f"Bearer {value}"}
    if env_api_key and env_api_key.strip():
        return {"Authorization": f"Bearer {env_api_key.strip()}"}
    return None


__all__ = ["EVAL_GATEWAY_MODES", "build_eval_gateway_factory"]
