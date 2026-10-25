"""HTTP implementation of the upstream trajectory-query client contract."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import date
from http import HTTPStatus
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from app.errors import AppError, ErrorCode
from app.third_party_api.trajectory.models import (
    FetchManyResult,
    TrajectoryPackage,
    TrajectoryWindow,
    TrajectoryWindowItem,
    UpstreamItemIssue,
)

_VERSION_PATTERN = re.compile(r"^(?P<major>[1-9][0-9]*)\.(?P<minor>[0-9]+)$")
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class HttpTrajectorySource:
    """Call the versioned trajectory query API with bounded retries."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_retries: int = 3,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        max_pages: int = 100,
    ) -> None:
        """Bind one lifespan-owned HTTP client and deterministic retry policy."""
        self._client = client
        self._max_retries = max(0, min(max_retries, 3))
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep or asyncio.sleep
        self._max_pages = max(1, max_pages)

    async def fetch(self, session_id: str) -> TrajectoryPackage:
        """Fetch and strictly validate one root trajectory package."""
        payload = await self._get_json(f"trajectories/{quote(session_id, safe='')}")
        package = self._validate(TrajectoryPackage, payload, "package")
        if package.session_id != session_id:
            raise self._invalid_response("upstream package sessionId did not match request")
        return package

    async def list_window(
        self,
        *,
        from_date: date,
        to_date: date,
        problem_only: bool,
        cursor: str | None,
    ) -> tuple[TrajectoryWindowItem, ...]:
        """Follow non-empty cursors and reject repeats/page overflow."""
        if to_date < from_date:
            raise AppError(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code=ErrorCode.VALIDATION_INVALID,
                message="window end must not precede start",
            )
        items: list[TrajectoryWindowItem] = []
        seen: set[str] = set()
        next_cursor = cursor
        for _page in range(self._max_pages):
            params: dict[str, str] = {
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "problemOnly": str(problem_only).lower(),
            }
            if next_cursor:
                params["cursor"] = next_cursor
            payload = await self._get_json("trajectories", params=params)
            page = self._validate(TrajectoryWindow, payload, "window")
            items.extend(page.items)
            if not page.next_cursor:
                return tuple(items)
            if page.next_cursor in seen:
                raise self._invalid_response("upstream cursor repeated")
            seen.add(page.next_cursor)
            next_cursor = page.next_cursor
        raise AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.UPSTREAM_REQUEST_FAILED,
            message="upstream pagination limit was exceeded",
        )

    async def fetch_many(self, session_ids: list[str]) -> FetchManyResult:
        """Fetch packages in order while turning each failure into a safe issue."""
        packages: list[TrajectoryPackage] = []
        issues: list[UpstreamItemIssue] = []
        for session_id in session_ids:
            try:
                packages.append(await self.fetch(session_id))
            except (AppError, ValidationError) as exc:
                if (
                    isinstance(exc, AppError)
                    and exc.code is ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE
                ):
                    raise
                code = exc.code.value if isinstance(exc, AppError) else "UPSTREAM_INVALID_RESPONSE"
                issues.append(
                    UpstreamItemIssue(
                        session_id=session_id,
                        code=code,
                        message="Upstream session could not be imported",
                    ),
                )
            except httpx.HTTPError:
                issues.append(
                    UpstreamItemIssue(
                        session_id=session_id,
                        code=ErrorCode.UPSTREAM_INVALID_RESPONSE.value,
                        message="Upstream session could not be imported",
                    ),
                )
        return FetchManyResult(packages=tuple(packages), issues=tuple(issues))

    async def close(self) -> None:
        """Close the client when this source owns the application's HTTP session."""
        await self._client.aclose()

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(
                    path,
                    params=params,
                    headers={"Accept-Encoding": "gzip"},
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    raise self._request_failed() from exc
                await self._sleep(self._delay(attempt))
                continue
            retryable = response.status_code == 429 or 500 <= response.status_code <= 599
            if retryable and attempt < self._max_retries:
                await self._sleep(self._delay(attempt))
                continue
            if response.status_code >= 400:
                if retryable:
                    raise self._request_failed()
                raise AppError(
                    status_code=HTTPStatus.BAD_GATEWAY,
                    code=ErrorCode.UPSTREAM_REQUEST_FAILED,
                    message=f"upstream returned HTTP {response.status_code}",
                    details={"status": response.status_code},
                )
            self._validate_version(response.headers.get("X-Trajectory-Api-Version"))
            try:
                text = response.text
                return json.loads(
                    text,
                    object_pairs_hook=self._reject_duplicate_keys,
                )
            except (httpx.DecodingError, ValueError, DuplicateJsonKeyError) as exc:
                raise self._invalid_response("upstream returned invalid JSON") from exc
        raise self._request_failed()

    def _validate_version(self, value: str | None) -> None:
        match = _VERSION_PATTERN.fullmatch(value or "")
        if match is None or match.group("major") != "1":
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE,
                message="upstream trajectory API version is incompatible",
            )

    @staticmethod
    def _validate(model: type[_ModelT], payload: Any, label: str) -> _ModelT:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.UPSTREAM_INVALID_RESPONSE,
                message=f"upstream {label} does not match the contract",
            ) from exc

    @staticmethod
    def _request_failed() -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.UPSTREAM_REQUEST_FAILED,
            message="upstream trajectory request failed",
        )

    @staticmethod
    def _invalid_response(message: str) -> AppError:
        return AppError(
            status_code=HTTPStatus.BAD_GATEWAY,
            code=ErrorCode.UPSTREAM_INVALID_RESPONSE,
            message=message,
        )

    def _delay(self, attempt: int) -> float:
        return float(self._backoff_seconds * (2**attempt))

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DuplicateJsonKeyError
            result[key] = value
        return result


class DuplicateJsonKeyError(ValueError):
    """Reject ambiguous JSON objects returned by the upstream."""
