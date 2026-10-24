"""Request correlation middleware."""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a stable request ID to logs and failure responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Set request context before routing and echo its ID."""
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
