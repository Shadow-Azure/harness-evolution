"""Fail-closed bearer authentication boundary."""

from http import HTTPStatus

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.errors import AppError, ErrorCode, error_response
from app.service.identity.principals import principal_from_claims

_PUBLIC_API_PATHS = {"/api/health", "/api/auth/login", "/api/auth/refresh", "/api/events"}
_DOC_PATHS = {"/api/docs", "/api/openapi.json"}
_MCP_ALLOWED_PATHS = {
    "/api/auth/change-password",
    "/api/auth/logout",
    "/api/auth/me",
}
_ADMIN_API_PATHS = {"/api/users", "/api/acquisition/sync", "/api/acquisition/pull"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Verify every bearer token and enforce forced-password-change routing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject unauthenticated, expired, and password-change-blocked requests."""
        path = request.url.path
        settings = request.app.state.settings
        public_paths = _PUBLIC_API_PATHS | (_DOC_PATHS if settings.docs_enabled else set())
        if path in public_paths or (path.startswith("/api/") and path in _DOC_PATHS):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            return self._unauthorized()
        try:
            claims = request.app.state.identity.tokens.decode_access_token(token)
            principal = principal_from_claims(claims)
        except AppError as exc:
            return await self._token_error(request, exc)

        if principal.must_change_password and path not in _MCP_ALLOWED_PATHS:
            return error_response(
                status_code=HTTPStatus.FORBIDDEN,
                code=ErrorCode.MUST_CHANGE_PASSWORD,
                message="password change is required",
            )
        is_admin_path = any(
            path == admin_path or path.startswith(f"{admin_path}/")
            for admin_path in _ADMIN_API_PATHS
        )
        if principal.role != "admin" and is_admin_path:
            return error_response(
                status_code=HTTPStatus.FORBIDDEN,
                code=ErrorCode.FORBIDDEN,
                message="administrator role is required",
            )
        request.state.principal = principal
        return await call_next(request)

    async def _token_error(self, request: Request, error: AppError) -> Response:
        """Distinguish expired tokens from all other malformed credentials."""
        if error.code == ErrorCode.AUTH_EXPIRED:
            return error_response(
                status_code=HTTPStatus.UNAUTHORIZED,
                code=ErrorCode.AUTH_EXPIRED,
                message="access token has expired",
            )
        return self._unauthorized()

    @staticmethod
    def _unauthorized() -> Response:
        """Return the stable missing-or-invalid bearer credential response."""
        return error_response(
            status_code=HTTPStatus.UNAUTHORIZED,
            code=ErrorCode.AUTH_REQUIRED,
            message="authentication is required",
        )
