"""Lightweight per-IP rate limiting for password login."""

import asyncio
from collections import defaultdict, deque
from collections.abc import Callable
from math import ceil
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.errors import ErrorCode, error_response


class LoginRateLimiter:
    """Keep a bounded sliding window of login attempts for each client key."""

    def __init__(
        self,
        *,
        limit: int = 10,
        window_seconds: int = 60,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Create an empty limiter with an injectable monotonic clock."""
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def retry_after(self, key: str) -> int:
        """Record one attempt and return zero or the seconds until a slot opens."""
        async with self._lock:
            now = self._clock()
            cutoff = now - self._window_seconds
            self._discard_stale(cutoff)
            attempts = self._attempts[key]
            if len(attempts) >= self._limit:
                return max(1, ceil(attempts[0] + self._window_seconds - now))
            attempts.append(now)
            return 0

    def _discard_stale(self, cutoff: float) -> None:
        """Remove old attempts and empty client windows."""
        for key in list(self._attempts):
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self._attempts[key]


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply the login limit before validation or password hashing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Return a stable 429 response when an IP exhausts the sliding window."""
        if request.method == "POST" and request.url.path == "/api/auth/login":
            client = request.client.host if request.client else "unknown"
            delay = await request.app.state.login_rate_limiter.retry_after(client)
            if delay:
                return error_response(
                    status_code=429,
                    code=ErrorCode.RATE_LIMITED,
                    message="too many login attempts",
                    headers={"Retry-After": str(delay)},
                )
        return await call_next(request)
