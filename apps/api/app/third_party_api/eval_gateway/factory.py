"""Registry-driven evaluation gateway selection.

Switching platforms only registers another subclass; the composition root and
every business service keep calling the parent interface.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from app.service.evolution.engine.contracts import (
    EvalGateway,
    EvalGatewayConfig,
    EvalGatewayConfigError,
)
from app.third_party_api.eval_gateway.ai_eval_platform import AiEvalPlatformGateway
from app.third_party_api.eval_gateway.base import BaseEvalGateway
from app.third_party_api.eval_gateway.fake import FakeEvalGateway

if TYPE_CHECKING:
    from app.config import Settings

_BUILTIN_GATEWAYS: tuple[type[BaseEvalGateway], ...] = (
    FakeEvalGateway,
    AiEvalPlatformGateway,
)
EVAL_GATEWAY_MODES: tuple[str, ...] = tuple(gateway.provider for gateway in _BUILTIN_GATEWAYS)
_DEFAULT_API_KEY_REF = "HE_EVAL_API_KEY"


class EvalGatewayFactory:
    """Create one gateway subclass from the run snapshot and environment."""

    def __init__(
        self,
        *,
        default_mode: str,
        environment: Mapping[str, str] | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        client: Any = None,
    ) -> None:
        """Bind composition-root defaults and the per-run override path."""
        self._default_mode = default_mode
        self._environment = environment
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._registry: dict[str, type[BaseEvalGateway]] = {}
        for gateway_type in _BUILTIN_GATEWAYS:
            self.register(gateway_type.provider, gateway_type)

    def register(
        self,
        provider: str,
        gateway_type: type[BaseEvalGateway],
    ) -> None:
        """Register one provider name; a platform adds only this call."""
        name = provider.strip()
        if not name:
            raise ValueError("evaluation gateway provider must not be blank")
        if name in self._registry:
            raise ValueError(f"evaluation gateway provider already registered: {name}")
        self._registry[name] = gateway_type

    def registered(self) -> tuple[str, ...]:
        """Return the provider names that can be selected by config."""
        return tuple(self._registry)

    def create(
        self,
        config: EvalGatewayConfig,
        *,
        env: Mapping[str, str] | None = None,
    ) -> EvalGateway:
        """Resolve one gateway from the run snapshot with env fallback."""
        if env is not None:
            environment = env
        elif self._environment is not None:
            environment = self._environment
        else:
            environment = os.environ
        configured = config.get("mode")
        mode = (
            configured.strip()
            if isinstance(configured, str) and configured.strip()
            else self._default_mode
        )
        gateway_type = self._registry.get(mode)
        if gateway_type is None:
            choices = ", ".join(self._registry)
            raise EvalGatewayConfigError(
                f"unknown evaluation gateway mode: {mode} (registered: {choices})",
            )
        if gateway_type is FakeEvalGateway:
            return FakeEvalGateway(config=config)
        return self._network_gateway(gateway_type, config, environment)

    def _network_gateway(
        self,
        gateway_type: type[BaseEvalGateway],
        config: EvalGatewayConfig,
        environment: Mapping[str, str],
    ) -> BaseEvalGateway:
        """Build an HTTP gateway after validating endpoint and credentials."""
        configured_url = config.get("baseUrl")
        base_url = (
            configured_url
            if isinstance(configured_url, str) and configured_url.strip()
            else self._base_url
        )
        if not base_url:
            raise EvalGatewayConfigError(
                "evaluation gateway requires a baseUrl (run eval config or HE_EVAL_BASE_URL)",
            )
        parsed = urlsplit(str(base_url))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise EvalGatewayConfigError(
                "evaluation gateway baseUrl must be an explicit HTTP(S) URL "
                "without credentials, query or fragment",
            )
        merged = dict(config)
        merged["baseUrl"] = base_url.rstrip("/")
        auth_header = _resolve_auth_header(
            config,
            environment=environment,
            env_api_key=self._api_key,
        )
        return gateway_type(
            config=EvalGatewayConfig.from_mapping(merged),
            client=self._client,
            auth_header=auth_header,
            timeout_seconds=self._timeout_seconds,
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


def build_eval_gateway_factory(
    settings: Settings,
    *,
    fallback_mode: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> Callable[..., EvalGateway]:
    """Bind one settings snapshot into a per-run gateway constructor."""
    factory = EvalGatewayFactory(
        default_mode=fallback_mode or settings.eval_mode,
        environment=environment,
        base_url=settings.eval_base_url,
        api_key=(
            settings.eval_api_key.get_secret_value() if settings.eval_api_key is not None else None
        ),
        timeout_seconds=30.0,
    )
    return factory.create


__all__ = [
    "EVAL_GATEWAY_MODES",
    "EvalGatewayFactory",
    "build_eval_gateway_factory",
]
