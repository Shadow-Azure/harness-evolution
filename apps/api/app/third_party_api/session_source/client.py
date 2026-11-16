"""HTTP client for one report's session-information envelope and adapter dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from app.errors import AppError, ErrorCode
from app.third_party_api.session_query.trajectory import (
    DuplicateJsonKeyError,
    TrajectoryFormatError,
    canonicalize_ndjson,
)
from app.third_party_api.session_source.base import (
    SessionInfo,
    SessionSourceEnvelope,
)
from app.third_party_api.session_source.factory import SessionSourceFactory

logger = logging.getLogger(__name__)

MAX_ENVELOPE_BYTES = 96 * 1024 * 1024
SUPPORTED_SCHEMA_VERSION = 1


class SessionSourceFetcher(Protocol):
    """Fetch one session envelope through a report-supplied URL template."""

    async def fetch(
        self,
        *,
        session_url_template: str,
        session_id: str,
        expected_parent_id: str | None,
        declared_runtime: str | None = None,
    ) -> SessionInfo:
        """Return one validated runtime-agnostic session projection."""


class HttpSessionSourceClient:
    """Call one envelope URL with bounded retries and a process-serial lock."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind the shared HTTP client and the process-wide fetch lock."""
        self._client = client
        self._max_retries = max(0, min(max_retries, 5))
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep or asyncio.sleep
        self._lock = asyncio.Lock()

    async def fetch(
        self,
        *,
        session_url_template: str,
        session_id: str,
        expected_parent_id: str | None,
        declared_runtime: str | None = None,
    ) -> SessionInfo:
        """Fetch, strictly validate, and project one session envelope."""
        url = self._render_url(session_url_template, session_id)
        async with self._lock:
            response = await self._request(url)
        envelope = self._parse_envelope(response.content)
        self._validate_identity(
            envelope,
            session_id=session_id,
            expected_parent_id=expected_parent_id,
        )
        try:
            trajectory = canonicalize_ndjson(envelope.trajectory.content)
        except TrajectoryFormatError as exc:
            raise self._invalid_response(exc.message) from exc
        if envelope.trajectory.line_count != trajectory.line_count:
            raise self._invalid_response(
                "trajectory lineCount did not match the canonical content",
            )
        if declared_runtime is not None and declared_runtime != envelope.runtime:
            logger.info(
                "session source runtime declaration does not match the envelope",
                extra={
                    "declared_runtime": declared_runtime,
                    "envelope_runtime": envelope.runtime,
                },
            )
        adapter = SessionSourceFactory.create(envelope.runtime)
        try:
            return adapter.project(envelope, trajectory)
        except ValidationError as exc:
            raise self._invalid_response(
                "agentMeta did not match the runtime schema",
            ) from exc

    def _render_url(self, template: str, session_id: str) -> str:
        """Render one session URL and reject a malformed stored template."""
        if template.count("{sessionId}") != 1 or len(template) > 2048:
            raise self._invalid_response("sessionUrlTemplate is invalid")
        parsed = urlsplit(template.replace("{sessionId}", quote(session_id, safe="")))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise self._invalid_response("sessionUrlTemplate is invalid")
        return template.replace("{sessionId}", quote(session_id, safe=""))

    def _parse_envelope(self, body: bytes) -> SessionSourceEnvelope:
        """Decode the strict envelope and check its independent schema contract."""
        if len(body) > MAX_ENVELOPE_BYTES:
            raise self._invalid_response("session source response exceeded the size limit")
        try:
            payload: Any = json.loads(
                body,
                object_pairs_hook=_reject_duplicate_keys,
            )
        except (json.JSONDecodeError, UnicodeDecodeError, DuplicateJsonKeyError) as exc:
            raise self._invalid_response("session source response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise self._invalid_response("session source response was not an object")
        try:
            envelope = SessionSourceEnvelope.model_validate(payload)
        except ValidationError as exc:
            raise self._invalid_response(
                "session source response did not match the contract",
            ) from exc
        if envelope.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.SESSION_SOURCE_VERSION_INCOMPATIBLE,
                message="session source schema version is incompatible",
            )
        return envelope

    @staticmethod
    def _validate_identity(
        envelope: SessionSourceEnvelope,
        *,
        session_id: str,
        expected_parent_id: str | None,
    ) -> None:
        """Reject echo and traversal-parent mismatches before adapter dispatch."""
        if envelope.session_id != session_id:
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.SESSION_SOURCE_SESSION_MISMATCH,
                message="session source returned a different session id",
            )
        if expected_parent_id is None:
            if envelope.agent_kind != "main" or envelope.parent_session_id is not None:
                raise HttpSessionSourceClient._invalid_response(
                    "root envelope was not a main agent",
                )
            return
        if envelope.agent_kind != "subagent" or envelope.parent_session_id != expected_parent_id:
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.SESSION_SOURCE_SESSION_MISMATCH,
                message="session source returned an inconsistent parent session id",
            )

    async def _request(self, url: str) -> httpx.Response:
        """GET one absolute URL with bounded retryable-failure handling."""
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(url, follow_redirects=False)
            except httpx.TimeoutException:
                if attempt >= self._max_retries:
                    raise self._timeout() from None
                await self._sleep(self._delay(attempt))
                continue
            except httpx.TransportError:
                if attempt >= self._max_retries:
                    raise self._request_failed() from None
                await self._sleep(self._delay(attempt))
                continue

            if response.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
                raise AppError(
                    status_code=HTTPStatus.BAD_GATEWAY,
                    code=ErrorCode.SESSION_SOURCE_UNAUTHORIZED,
                    message="session source rejected the report URL",
                )
            retryable = response.status_code == HTTPStatus.TOO_MANY_REQUESTS or (
                500 <= response.status_code <= 599
            )
            if retryable and attempt < self._max_retries:
                await self._sleep(self._delay(attempt))
                continue
            if response.status_code >= 400:
                raise self._request_failed()
            return response
        raise self._request_failed()

    def _delay(self, attempt: int) -> float:
        return float(self._backoff_seconds * (2**attempt))

    @staticmethod
    def _timeout() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.SESSION_SOURCE_TIMEOUT,
            message="session source timed out",
        )

    @staticmethod
    def _request_failed() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.SESSION_SOURCE_REQUEST_FAILED,
            message="session source request failed",
        )

    @staticmethod
    def _invalid_response(message: str) -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.SESSION_SOURCE_INVALID_RESPONSE,
            message=message,
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous envelope objects instead of silently overwriting keys."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError
        result[key] = value
    return result
