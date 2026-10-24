"""Application errors and the shared API error envelope."""

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    """Stable machine-readable error codes."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL = "INTERNAL"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_INVALID = "VALIDATION_INVALID"


class ErrorBody(BaseModel):
    """Error payload shared by browser and API clients."""

    model_config = ConfigDict(extra="forbid")

    code: str
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
        code: str,
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
    code: str,
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
            code = ErrorCode.INTERNAL
            message = "request failed"
            details = {"path": request.url.path, "status": http_error.status_code}
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
            details={"errors": jsonable_encoder(validation_error.errors())},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return error_response(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL,
            message="internal server error",
            details={"requestId": request_id},
            headers={"X-Request-Id": request_id},
        )
