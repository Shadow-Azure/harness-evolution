"""Fail-closed authentication boundary for the pre-identity scaffold."""

from http import HTTPStatus

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.errors import ErrorCode, error_response

_PUBLIC_API_PATHS = {"/api/health"}
_DOC_PATHS = {
    "/api/docs",
    "/api/openapi.json",
}


class AuthBoundaryMiddleware(BaseHTTPMiddleware):
    """Require future authentication for every non-public API route."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject unauthenticated business API requests before routing."""
        path = request.url.path
        docs_enabled = request.app.state.settings.docs_enabled
        public_paths = _PUBLIC_API_PATHS | (_DOC_PATHS if docs_enabled else set())
        is_business_path = path.startswith("/api/") and path not in _DOC_PATHS
        if is_business_path and path not in public_paths:
            return error_response(
                status_code=HTTPStatus.UNAUTHORIZED,
                code=ErrorCode.AUTH_REQUIRED,
                message="authentication is required",
            )
        return await call_next(request)
