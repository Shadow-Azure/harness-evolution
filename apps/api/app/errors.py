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
    TICKET_INVALID = "TICKET_INVALID"
    TICKET_EXPIRED = "TICKET_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    MUST_CHANGE_PASSWORD = "PASSWORD_CHANGE_REQUIRED"
    USERNAME_CONFLICT = "USERNAME_CONFLICT"
    INTERNAL = "INTERNAL"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_INVALID = "VALIDATION_INVALID"
    RATE_LIMITED = "RATE_LIMITED"


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
