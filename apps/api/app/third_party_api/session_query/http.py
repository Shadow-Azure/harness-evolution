"""HTTP implementation of the bad-case session-query client contract."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.errors import AppError, ErrorCode
from app.third_party_api.session_query.models import (
    SessionChildren,
    SessionTrajectory,
)
from app.third_party_api.session_query.trajectory import (
    TrajectoryFormatError,
    canonicalize_body,
)


class HttpSessionQuerySource:
    """Call the two session-query endpoints with bounded retries and a serial trajectory lock."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind one client and one process-wide trajectory-call lock."""
        self._client = client
        self._max_retries = max(0, min(max_retries, 5))
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep or asyncio.sleep
        self._trajectory_lock = asyncio.Lock()

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        """Return direct child session ids; an empty array means no children."""
        response = await self._request(
            f"sessions/{quote(session_id, safe='')}/children",
            accept="application/json",
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise self._invalid_response("children response was not JSON") from exc
        try:
            return tuple(SessionChildren.model_validate(payload).root)
        except ValidationError as exc:
            raise self._invalid_response("children response did not match the contract") from exc

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        """Return one canonical NDJSON trajectory; calls never overlap."""
        async with self._trajectory_lock:
            response = await self._request(
                f"sessions/{quote(session_id, safe='')}/trajectory",
                accept="application/x-ndjson",
            )
            return self._parse_trajectory(response.content)

    async def close(self) -> None:
        """Close the client when this source owns the application's HTTP session."""
        await self._client.aclose()

    async def _request(self, path: str, *, accept: str) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(path, headers={"Accept": accept})
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
                    code=ErrorCode.SESSION_QUERY_UNAUTHORIZED,
                    message="session query service rejected the service token",
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

    @staticmethod
    def _parse_trajectory(body: bytes) -> SessionTrajectory:
        try:
            return canonicalize_body(body)
        except TrajectoryFormatError as exc:
            if exc.empty:
                raise AppError(
                    status_code=HTTPStatus.BAD_GATEWAY,
                    code=ErrorCode.TRAJECTORY_EMPTY,
                    message=exc.message,
                ) from exc
            raise HttpSessionQuerySource._invalid_response(exc.message) from exc

    def _delay(self, attempt: int) -> float:
        return float(self._backoff_seconds * (2**attempt))

    @staticmethod
    def _timeout() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.SESSION_QUERY_TIMEOUT,
            message="session query service timed out",
        )

    @staticmethod
    def _request_failed() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.SESSION_QUERY_REQUEST_FAILED,
            message="session query request failed",
        )

    @staticmethod
    def _invalid_response(message: str) -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.SESSION_QUERY_INVALID_RESPONSE,
            message=message,
        )
