"""Application errors and the shared API error envelope."""

import logging
from collections.abc import Mapping, Sequence
from enum import StrEnum
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """Stable machine-readable error codes."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID = "AUTH_INVALID"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_PROVIDER_NOT_CONFIGURED = "AUTH_PROVIDER_NOT_CONFIGURED"
    AUTH_STATE_INVALID = "AUTH_STATE_INVALID"
    AUTH_PROVIDER_ERROR = "AUTH_PROVIDER_ERROR"
    AUTH_NO_MAPPING = "AUTH_NO_MAPPING"
    TICKET_INVALID = "TICKET_INVALID"
    TICKET_EXPIRED = "TICKET_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    MUST_CHANGE_PASSWORD = "PASSWORD_CHANGE_REQUIRED"
    USERNAME_CONFLICT = "USERNAME_CONFLICT"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    BAD_CASE_NOT_FOUND = "BAD_CASE_NOT_FOUND"
    BAD_CASE_SESSION_PENDING = "BAD_CASE_SESSION_PENDING"
    BAD_CASE_SESSION_UNAVAILABLE = "BAD_CASE_SESSION_UNAVAILABLE"
    BAD_CASE_SESSION_MISMATCH = "BAD_CASE_SESSION_MISMATCH"
    ATTRIBUTION_NOT_FOUND = "ATTRIBUTION_NOT_FOUND"
    ATTRIBUTION_SKILL_NOT_FOUND = "ATTRIBUTION_SKILL_NOT_FOUND"
    ATTRIBUTION_SKILL_EXISTS = "ATTRIBUTION_SKILL_EXISTS"
    ATTRIBUTION_SKILL_INVALID = "ATTRIBUTION_SKILL_INVALID"
    ATTRIBUTION_SKILL_PACKAGE_NOT_FOUND = "ATTRIBUTION_SKILL_PACKAGE_NOT_FOUND"
    ATTRIBUTION_SKILL_PACKAGE_EXISTS = "ATTRIBUTION_SKILL_PACKAGE_EXISTS"
    ATTRIBUTION_SKILL_PACKAGE_INVALID = "ATTRIBUTION_SKILL_PACKAGE_INVALID"
    ATTRIBUTION_SKILL_PACKAGE_TOO_LARGE = "ATTRIBUTION_SKILL_PACKAGE_TOO_LARGE"
    ATTRIBUTION_QUALITY_GATE_FAILED = "ATTRIBUTION_QUALITY_GATE_FAILED"
    ATTRIBUTION_ENGINE_UNAVAILABLE = "ATTRIBUTION_ENGINE_UNAVAILABLE"
    PROBE_NOT_FOUND = "PROBE_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    STEP_NOT_READY = "STEP_NOT_READY"
    RUN_BUSY = "RUN_BUSY"
    RUN_CONTROL_CONFLICT = "RUN_CONTROL_CONFLICT"
    RUN_NOT_RETRYABLE = "RUN_NOT_RETRYABLE"
    REPO_INVALID = "REPO_INVALID"
    PROJECT_ID_INVALID = "PROJECT_ID_INVALID"
    PRIMARY_METRIC_KEY_INVALID = "PRIMARY_METRIC_KEY_INVALID"
    ENGINE_INVALID = "ENGINE_INVALID"
    TARGET_EXISTS = "TARGET_EXISTS"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_IN_USE = "TARGET_IN_USE"
    TARGET_NOT_CONFIGURED = "TARGET_NOT_CONFIGURED"
    TARGET_CONTENT_UNRESOLVED = "TARGET_CONTENT_UNRESOLVED"
    NO_PROBES_MATCHED = "NO_PROBES_MATCHED"
    POLICY_INVALID = "POLICY_INVALID"
    NO_ASSOCIATED_SESSIONS = "NO_ASSOCIATED_SESSIONS"
    NO_POTENTIAL_MATCHED = "NO_POTENTIAL_MATCHED"
    INTERNAL = "INTERNAL"
    EXTERNAL_SCHEMA_DRIFT = "EXTERNAL_SCHEMA_DRIFT"
    EXTERNAL_READ_FORBIDDEN = "EXTERNAL_READ_FORBIDDEN"
    EXTERNAL_READ_FAILED = "EXTERNAL_READ_FAILED"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_INVALID = "VALIDATION_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_NOT_AVAILABLE = "UPSTREAM_NOT_AVAILABLE"
    UPSTREAM_VERSION_INCOMPATIBLE = "UPSTREAM_VERSION_INCOMPATIBLE"
    UPSTREAM_INVALID_RESPONSE = "UPSTREAM_INVALID_RESPONSE"
    UPSTREAM_REQUEST_FAILED = "UPSTREAM_REQUEST_FAILED"
    SESSION_QUERY_UNAVAILABLE = "SESSION_QUERY_UNAVAILABLE"
    SESSION_QUERY_UNAUTHORIZED = "SESSION_QUERY_UNAUTHORIZED"
    SESSION_QUERY_VERSION_INCOMPATIBLE = "SESSION_QUERY_VERSION_INCOMPATIBLE"
    SESSION_QUERY_INVALID_RESPONSE = "SESSION_QUERY_INVALID_RESPONSE"
    SESSION_QUERY_TIMEOUT = "SESSION_QUERY_TIMEOUT"
    SESSION_QUERY_REQUEST_FAILED = "SESSION_QUERY_REQUEST_FAILED"
    SESSION_SOURCE_UNAUTHORIZED = "SESSION_SOURCE_UNAUTHORIZED"
    SESSION_SOURCE_INVALID_RESPONSE = "SESSION_SOURCE_INVALID_RESPONSE"
    SESSION_SOURCE_TIMEOUT = "SESSION_SOURCE_TIMEOUT"
    SESSION_SOURCE_REQUEST_FAILED = "SESSION_SOURCE_REQUEST_FAILED"
    SESSION_SOURCE_VERSION_INCOMPATIBLE = "SESSION_SOURCE_VERSION_INCOMPATIBLE"
    SESSION_SOURCE_SESSION_MISMATCH = "SESSION_SOURCE_SESSION_MISMATCH"
    TRAVERSAL_LIMIT_EXCEEDED = "TRAVERSAL_LIMIT_EXCEEDED"
    TRAJECTORY_EMPTY = "TRAJECTORY_EMPTY"
    BAD_CASE_SYNC_FAILED = "BAD_CASE_SYNC_FAILED"
    BAD_CASE_SYNC_TIME_BUDGET = "BAD_CASE_SYNC_TIME_BUDGET"
    BAD_CASE_QUERY_UNAVAILABLE = "BAD_CASE_QUERY_UNAVAILABLE"
    BAD_CASE_QUERY_UNAUTHORIZED = "BAD_CASE_QUERY_UNAUTHORIZED"
    BAD_CASE_QUERY_INVALID_RESPONSE = "BAD_CASE_QUERY_INVALID_RESPONSE"
    BAD_CASE_QUERY_TIMEOUT = "BAD_CASE_QUERY_TIMEOUT"
    BAD_CASE_QUERY_REQUEST_FAILED = "BAD_CASE_QUERY_REQUEST_FAILED"
    BAD_CASE_CATALOG_SYNC_FAILED = "BAD_CASE_CATALOG_SYNC_FAILED"
    BAD_CASE_CATALOG_SYNC_INTERRUPTED = "BAD_CASE_CATALOG_SYNC_INTERRUPTED"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    WORKSPACE_FORBIDDEN = "WORKSPACE_FORBIDDEN"
    WORKSPACE_EXISTS = "WORKSPACE_EXISTS"
    MEMBER_EXISTS = "MEMBER_EXISTS"
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    ROLE_INVALID = "ROLE_INVALID"
    ROLE_LOCKED = "ROLE_LOCKED"
    QUOTA_INVALID = "QUOTA_INVALID"
    CREDENTIAL_NOT_FOUND = "CREDENTIAL_NOT_FOUND"
    CREDENTIAL_INVALID = "CREDENTIAL_INVALID"
    CREDENTIAL_LIMIT = "CREDENTIAL_LIMIT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    BAD_CASE_ID_CONFLICT = "BAD_CASE_ID_CONFLICT"
    WINDOW_INVALID = "WINDOW_INVALID"
    GRAIN_INVALID = "GRAIN_INVALID"
    OBJECT_FILTER_TOO_LARGE = "OBJECT_FILTER_TOO_LARGE"
    KNOWLEDGE_ROOTS_INVALID = "KNOWLEDGE_ROOTS_INVALID"


class ErrorBody(BaseModel):
    """Error payload shared by browser and API clients."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    """Top-level failure response."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class AppError(Exception):
    """Expected business failure translated by the API boundary."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        status_code: int = HTTPStatus.BAD_REQUEST,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create an application error."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = dict(details or {})


def error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Create a JSON response with the common error envelope."""
    payload = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=dict(details or {})),
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=dict(headers or {}),
    )


def _log_internal_error(request: Request, exc: Exception) -> str:
    """Log an internal failure with correlation fields and return its request ID."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "unhandled request error",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return request_id


def _safe_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep actionable validation fields while dropping submitted input and context."""
    allowed = ("type", "loc", "msg")
    return [
        {field: jsonable_encoder(error[field]) for field in allowed if field in error}
        for error in errors
    ]


def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that keep every failure on the shared envelope."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
        error = cast(AppError, exc)
        return error_response(
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            details=error.details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
        http_error = cast(StarletteHTTPException, exc)
        details: dict[str, Any]
        if http_error.status_code == HTTPStatus.NOT_FOUND:
            code = ErrorCode.NOT_FOUND
            message = "route not found"
            details = {"path": request.url.path}
        elif http_error.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
            code = ErrorCode.METHOD_NOT_ALLOWED
            message = "method not allowed"
            details = {"method": request.method, "path": request.url.path}
        else:
            request_id = _log_internal_error(request, http_error)
            return error_response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code=ErrorCode.INTERNAL,
                message="internal server error",
                details={"requestId": request_id},
                headers={"X-Request-Id": request_id},
            )
        return error_response(
            status_code=http_error.status_code,
            code=code,
            message=message,
            details=details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        validation_error = cast(RequestValidationError, exc)
        return error_response(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=ErrorCode.VALIDATION_INVALID,
            message="request validation failed",
            details={"errors": _safe_validation_errors(validation_error.errors())},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = _log_internal_error(request, exc)
        return error_response(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL,
            message="internal server error",
            details={"requestId": request_id},
            headers={"X-Request-Id": request_id},
        )
