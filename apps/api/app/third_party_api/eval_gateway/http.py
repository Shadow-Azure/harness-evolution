"""HTTP implementation of the evaluation gateway seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalRequest,
    EvalResult,
    EvalStatus,
    EvalSubmission,
)
from app.third_party_api.eval_gateway.mapper import EvalMapper, HttpEvalError

_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class HttpEvalGateway:
    """Call the external evaluation platform over HTTP with bounded timeouts.

    Configuration comes from the run's frozen snapshot; credentials are passed
    in as ready-to-use headers resolved indirectly from the environment by the
    gateway factory — this class never sees raw secret values in its config.
    """

    config: EvalGatewayConfig
    client: httpx.AsyncClient | None = None
    auth_header: Mapping[str, str] | None = None
    timeout_seconds: float = _TIMEOUT_SECONDS

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        """Submit one candidate and return the external evaluation id."""
        payload = await self._request_json(
            "POST",
            "/evals",
            json_body=EvalMapper.submit_payload(request),
            context="submission",
        )
        return EvalMapper.parse_submission(payload)

    async def get_status(self, eval_id: str) -> EvalStatus:
        """Return the external evaluation's current lifecycle state."""
        payload = await self._request_json(
            "GET",
            f"/evals/{quote(eval_id, safe='')}",
            context="status",
        )
        return EvalMapper.parse_status(payload)

    async def get_result(self, eval_id: str) -> EvalResult:
        """Return normalized scores and the external verdict."""
        payload = await self._request_json(
            "GET",
            f"/evals/{quote(eval_id, safe='')}/result",
            context="result",
        )
        return EvalMapper.parse_result(payload)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        context: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform one sanitized request/response cycle against the platform."""
        base_url = str(self.config.get("baseUrl") or "")
        url = f"{base_url.rstrip('/')}{path}"
        if self.client is not None:
            return await self._send(self.client, method, url, context, json_body)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await self._send(client, method, url, context, json_body)

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        context: str,
        json_body: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Send one request and fold every failure into HttpEvalError."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.auth_header:
            headers.update(self.auth_header)
        try:
            response = await client.request(
                method,
                url,
                json=dict(json_body) if json_body is not None else None,
                headers=headers,
            )
        except httpx.HTTPError:
            raise HttpEvalError(
                f"evaluation platform {context} request failed",
            ) from None
        if response.status_code >= 400:
            raise HttpEvalError(
                f"evaluation platform rejected the {context} request "
                f"with HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError:
            raise HttpEvalError(
                f"evaluation platform {context} response was not JSON",
            ) from None
        if not isinstance(payload, dict):
            raise HttpEvalError(
                f"evaluation platform {context} response was not an object",
            )
        return payload


__all__ = ["HttpEvalError", "HttpEvalGateway"]
