"""HTTP implementation of the upstream trajectory-query client contract."""

from __future__ import annotations

import asyncio
import json
import logging
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

logger = logging.getLogger(__name__)

_VERSION_PATTERN = re.compile(r"^(?P<major>[1-9][0-9]*)\.(?P<minor>[0-9]+)$")
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class HttpTrajectorySource:
    """Call the versioned trajectory query API with bounded retries."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        supported_major: int = 1,
        max_retries: int = 3,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        max_pages: int = 100,
    ) -> None:
        """Bind one lifespan-owned HTTP client and deterministic retry policy."""
        if supported_major != 1:
            raise ValueError("only upstream trajectory API major version 1 is supported")
        self._client = client
        self._supported_major = supported_major
        self._max_retries = max(0, min(max_retries, 3))
        self._backoff_seconds = max(0.0, backoff_seconds)
        self._sleep = sleep or asyncio.sleep
        self._max_pages = max(1, max_pages)
        self._observed_version: str | None = None

    async def fetch(self, session_id: str) -> TrajectoryPackage:
        """Fetch and strictly validate one root trajectory package."""
        payload = await self._get_json(
            f"trajectories/{quote(session_id, safe='')}",
            label="package",
        )
        package = self._validate(TrajectoryPackage, payload, "package")
        if package.session_id != session_id:
            self._log_contract_drift(
                label="package",
                reason="session_mismatch",
                error_count=1,
            )
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
            payload = await self._get_json("trajectories", params=params, label="window")
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
                    UpstreamItemIssue.model_validate(
                        {
                            "sessionId": session_id,
                            "code": code,
                            "message": "Upstream session could not be imported",
                        },
                    ),
                )
            except httpx.HTTPError:
                issues.append(
                    UpstreamItemIssue.model_validate(
                        {
                            "sessionId": session_id,
                            "code": ErrorCode.UPSTREAM_INVALID_RESPONSE.value,
                            "message": "Upstream session could not be imported",
                        },
                    ),
                )
        result = FetchManyResult(packages=tuple(packages), issues=tuple(issues))
        logger.info(
            "upstream trajectory batch health",
            extra={
                "event": "upstream.health",
                "status": "degraded" if issues else "ok",
                "sessions_requested": len(session_ids),
                "sessions_fetched": len(packages),
                "sessions_isolated": len(issues),
            },
        )
        return result

    async def close(self) -> None:
        """Close the client when this source owns the application's HTTP session."""
        await self._client.aclose()

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        label: str,
    ) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(
                    path,
                    params=params,
                    headers={"Accept-Encoding": "gzip"},
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "transport"
                if attempt >= self._max_retries:
                    self._log_request_failure(label=label, reason=reason, attempts=attempt + 1)
                    raise self._request_failed() from exc
                self._log_retry(label=label, reason=reason, attempt=attempt + 1)
                await self._sleep(self._delay(attempt))
                continue
            retryable = response.status_code == 429 or 500 <= response.status_code <= 599
            if retryable and attempt < self._max_retries:
                self._log_retry(
                    label=label,
                    reason="http_status",
                    attempt=attempt + 1,
                    status_code=response.status_code,
                )
                await self._sleep(self._delay(attempt))
                continue
            if response.status_code >= 400:
                self._log_request_failure(
                    label=label,
                    reason="retry_exhausted" if retryable else "http_status",
                    attempts=attempt + 1,
                    status_code=response.status_code,
                )
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
                self._log_contract_drift(label=label, reason="invalid_json", error_count=1)
                raise self._invalid_response("upstream returned invalid JSON") from exc
        raise self._request_failed()

    def _validate_version(self, value: str | None) -> None:
        match = _VERSION_PATTERN.fullmatch(value or "")
        if match is None or int(match.group("major")) != self._supported_major:
            observed_major = int(match.group("major")) if match is not None else None
            reason = (
                "missing"
                if not value
                else "incompatible"
                if observed_major is not None
                else "unparseable"
            )
            logger.warning(
                "upstream trajectory API version drift",
                extra={
                    "event": "upstream.version_drift",
                    "reason": reason,
                    "expected_major": self._supported_major,
                    "observed_major": observed_major,
                },
            )
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.UPSTREAM_VERSION_INCOMPATIBLE,
                message="upstream trajectory API version is incompatible",
            )
        if self._observed_version is None:
            logger.info(
                "upstream trajectory API version observed",
                extra={"event": "upstream.version_observed", "api_version": value},
            )
        elif value != self._observed_version:
            logger.warning(
                "upstream trajectory API version drifted between responses",
                extra={
                    "event": "upstream.version_drift",
                    "reason": "version_changed",
                    "previous_version": self._observed_version,
                    "current_version": value,
                },
            )
        self._observed_version = value

    @staticmethod
    def _validate(model: type[_ModelT], payload: Any, label: str) -> _ModelT:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            HttpTrajectorySource._log_contract_drift(
                label=label,
                reason="schema_mismatch",
                error_count=len(exc.errors()),
            )
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.UPSTREAM_INVALID_RESPONSE,
                message=f"upstream {label} does not match the contract",
            ) from exc

    @staticmethod
    def _log_retry(
        *,
        label: str,
        reason: str,
        attempt: int,
        status_code: int | None = None,
    ) -> None:
        logger.info(
            "retrying upstream trajectory request",
            extra={
                "event": "upstream.request_retry",
                "model": label,
                "reason": reason,
                "attempt": attempt,
                "status_code": status_code,
            },
        )

    @staticmethod
    def _log_request_failure(
        *,
        label: str,
        reason: str,
        attempts: int,
        status_code: int | None = None,
    ) -> None:
        logger.warning(
            "upstream trajectory request failed",
            extra={
                "event": "upstream.request_failed",
                "model": label,
                "reason": reason,
                "attempts": attempts,
                "status_code": status_code,
            },
        )

    @staticmethod
    def _log_contract_drift(*, label: str, reason: str, error_count: int) -> None:
        logger.warning(
            "upstream trajectory contract drift",
            extra={
                "event": "upstream.contract_drift",
                "model": label,
                "reason": reason,
                "error_count": error_count,
            },
        )

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
