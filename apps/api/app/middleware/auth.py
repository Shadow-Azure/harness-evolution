"""Fail-closed bearer authentication boundary."""

import re
from http import HTTPStatus

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.errors import AppError, ErrorCode, error_response
from app.service.identity.principals import principal_from_claims

_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/callback",
    "/api/events",
}
_DOC_PATHS = {"/api/docs", "/api/openapi.json"}
_MCP_ALLOWED_PATHS = {
    "/api/auth/change-password",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/auth/session",
}
_ADMIN_EXACT_ROUTES = {("POST", "/api/workspaces")}
_ADMIN_ROUTE_RULES = (
    (frozenset({"GET", "POST"}), "/api/users"),
    (frozenset({"POST"}), "/api/acquisition/sync"),
    (frozenset({"POST"}), "/api/acquisition/pull"),
    (frozenset({"POST", "PUT", "DELETE"}), "/api/evolution/targets"),
)
_CREDENTIAL_INGEST_ROUTE = re.compile(r"^/api/workspaces/[^/]+/bad-cases$")
"""The only route that authenticates with a workspace ingest credential."""


def _requires_admin(method: str, path: str) -> bool:
    """Return whether this method/path pair requires the administrator role."""
    if (method, path) in _ADMIN_EXACT_ROUTES:
        return True
    return any(
        method in methods and (path == prefix or path.startswith(f"{prefix}/"))
        for methods, prefix in _ADMIN_ROUTE_RULES
    )


def _is_credential_route(method: str, path: str) -> bool:
    """Return whether this method/path pair resolves its own credential.

    Exactly one POST route is exempt from access-token decoding. The match is
    anchored, so trailing slashes, extra segments, and other methods stay on the
    JWT path and a leaked workspace credential cannot authenticate anywhere else.
    """
    return method == "POST" and _CREDENTIAL_INGEST_ROUTE.match(path) is not None


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
        if _is_credential_route(request.method, path):
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
        if principal.role != "admin" and _requires_admin(request.method, path):
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
