"""HTTP implementation of the bad-case catalog query contract."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from http import HTTPStatus

import httpx
from pydantic import ValidationError

from app.errors import AppError, ErrorCode
from app.third_party_api.bad_case_query.models import BadCasePage


class HttpBadCaseCatalogSource:
    """Call the paginated catalog endpoint with bounded retries and one lock."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind one HTTP client and one process-wide request lock."""
        self._client = client
        self._max_retries = max(0, min(max_retries, 5))
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep or asyncio.sleep
        self._lock = asyncio.Lock()

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        """Return one validated page; calls never overlap in this process."""
        async with self._lock:
            response = await self._request(after_id, offset, limit)
            return self._parse(
                response,
                after_id=after_id,
                offset=offset,
                limit=limit,
            )

    async def close(self) -> None:
        """Close the client when this source owns the application's HTTP session."""
        await self._client.aclose()

    async def _request(
        self,
        after_id: int,
        offset: int,
        limit: int,
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(
                    "bad-cases",
                    params={
                        "bad_case_id": after_id,
                        "offset": offset,
                        "limit": limit,
                    },
                    headers={"Accept": "application/json"},
                )
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
                    code=ErrorCode.BAD_CASE_QUERY_UNAUTHORIZED,
                    message="bad-case query service rejected the service token",
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
    def _parse(
        response: httpx.Response,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        try:
            payload = response.json()
        except ValueError as exc:
            raise HttpBadCaseCatalogSource._invalid(
                "page response was not JSON",
            ) from exc
        try:
            page = BadCasePage.model_validate(payload)
        except ValidationError as exc:
            raise HttpBadCaseCatalogSource._invalid(
                "page response did not match the contract",
            ) from exc
        if page.offset != offset or page.limit != limit:
            raise HttpBadCaseCatalogSource._invalid(
                "page response did not echo the requested offset and limit",
            )
        if any(item.bad_case_id <= after_id for item in page.items):
            raise HttpBadCaseCatalogSource._invalid(
                "page returned an id at or below the cursor",
            )
        return page

    def _delay(self, attempt: int) -> float:
        return float(self._backoff_seconds * (2**attempt))

    @staticmethod
    def _timeout() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.BAD_CASE_QUERY_TIMEOUT,
            message="bad-case query service timed out",
        )

    @staticmethod
    def _request_failed() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.BAD_CASE_QUERY_REQUEST_FAILED,
            message="bad-case query request failed",
        )

    @staticmethod
    def _invalid(message: str) -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.BAD_CASE_QUERY_INVALID_RESPONSE,
            message=message,
        )
