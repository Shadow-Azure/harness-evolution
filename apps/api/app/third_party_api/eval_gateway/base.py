"""Shared transport and error boundary for external evaluation gateways."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

import httpx

from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalGatewayConfigError,
    EvalMeasurement,
    EvalRequest,
    EvalStatus,
    EvalSubmission,
)

_DEFAULT_TIMEOUT_SECONDS = 30.0


class EvalGatewayError(RuntimeError):
    """A sanitized evaluation-platform failure raised to the polling loop.

    ``retryable`` marks observation-side or platform-side transience (network
    timeouts, dropped connections, HTTP 429/5xx) so the polling loop can defer
    the next poll instead of judging the evaluation itself failed. Payload and
    4xx contract errors stay final. ``platform_code`` keeps the platform's error
    code for blocked(stage=eval) diagnostics without retaining the raw body.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        platform_code: str | None = None,
    ) -> None:
        """Store the safe message, retryability and optional platform code."""
        super().__init__(message)
        self.retryable = retryable
        self.platform_code = platform_code


class BaseEvalGateway(ABC):
    """Parent for every evaluation platform implementation.

    Subclasses only translate their protocol into the stable internal models.
    HTTP transport, authentication headers, timeouts and the error boundary
    live here so a new platform cannot silently skip them.
    """

    provider: ClassVar[str] = ""

    def __init__(
        self,
        config: EvalGatewayConfig,
        *,
        client: httpx.AsyncClient | None = None,
        auth_header: Mapping[str, str] | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Bind the immutable run snapshot and resolved transport options."""
        self._config = config
        self._client = client
        self._auth_header = dict(auth_header or {})
        self._timeout_seconds = timeout_seconds

    @property
    def config(self) -> EvalGatewayConfig:
        """Expose the frozen gateway configuration."""
        return self._config

    @abstractmethod
    async def submit(self, request: EvalRequest) -> EvalSubmission:
        """Submit one evaluation request and return its platform identifier."""

    @abstractmethod
    async def get_status(self, eval_id: str) -> EvalStatus:
        """Return the platform evaluation's current lifecycle state."""

    @abstractmethod
    async def get_result(self, eval_id: str) -> EvalMeasurement:
        """Return measurements; the service layer compares them with a baseline."""

    def config_text(self, key: str, *, required: bool = False) -> str:
        """Read one non-empty string from the frozen run snapshot."""
        value = self._config.get(key)
        text = value.strip() if isinstance(value, str) else ""
        if required and not text:
            raise EvalGatewayConfigError(
                f"{self.provider} gateway requires eval config {key}",
            )
        return text

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        context: str,
        json_body: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        """Perform one sanitized request/response cycle against the platform."""
        base_url = self.config_text("baseUrl", required=True).rstrip("/")
        url = f"{base_url}{path}"
        headers: dict[str, str] = {"Accept": "application/json"}
        headers.update(self._auth_header)
        if extra_headers:
            headers.update(extra_headers)
        if self._client is not None:
            return await self._send(
                self._client,
                method,
                url,
                context,
                headers,
                json_body,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await self._send(client, method, url, context, headers, json_body)

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        context: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        """Send one request and fold every failure into EvalGatewayError."""
        try:
            response = await client.request(
                method,
                url,
                json=dict(json_body) if json_body is not None else None,
                headers=dict(headers),
            )
        except httpx.HTTPError:
            raise EvalGatewayError(
                f"evaluation platform {context} request failed",
                retryable=True,
            ) from None
        if response.status_code >= 400:
            platform_code, message = _error_envelope(response)
            retryable = response.status_code >= 500 or response.status_code == 429
            detail = f": {message}" if message else ""
            code_text = f" [{platform_code}]" if platform_code else ""
            raise EvalGatewayError(
                f"evaluation platform rejected the {context} request "
                f"with HTTP {response.status_code}{code_text}{detail}",
                retryable=retryable,
                platform_code=platform_code,
            )
        try:
            payload = response.json()
        except ValueError:
            raise EvalGatewayError(
                f"evaluation platform {context} response was not JSON",
            ) from None
        if not isinstance(payload, dict):
            raise EvalGatewayError(
                f"evaluation platform {context} response was not an object",
            )
        return payload


def _error_envelope(response: httpx.Response) -> tuple[str | None, str | None]:
    """Read the platform's ``{"error": {code, message}}`` envelope safely."""
    try:
        payload = response.json()
    except ValueError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None, None
    code = error.get("code")
    message = error.get("message")
    return (
        code.strip() if isinstance(code, str) and code.strip() else None,
        message.strip() if isinstance(message, str) and message.strip() else None,
    )


__all__ = ["BaseEvalGateway", "EvalGatewayError"]
