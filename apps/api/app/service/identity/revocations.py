"""Bounded in-process replay protection for rotating refresh tokens."""

import asyncio
from collections.abc import Callable
from time import time


class RefreshRevocationStore:
    """Atomically consume refresh ids and lazily prune entries after their expiry."""

    def __init__(self, clock: Callable[[], float] = time) -> None:
        """Create an empty revocation index with an injectable wall clock."""
        self._clock = clock
        self._revoked: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Return the number of stored revocations for diagnostics and tests."""
        return len(self._revoked)

    async def consume_once(self, token_id: str, *, expires_at: float) -> bool:
        """Atomically claim an unseen refresh id, rejecting every concurrent replay."""
        async with self._lock:
            now = self._clock()
            self._prune(now)
            if token_id in self._revoked:
                return False
            self._revoked[token_id] = expires_at
            return True

    async def revoke(self, token_id: str, *, expires_at: float) -> None:
        """Revoke a refresh id until its signed expiry."""
        async with self._lock:
            self._prune(self._clock())
            self._revoked[token_id] = expires_at

    def _prune(self, now: float) -> None:
        """Drop revocations that cannot protect any live refresh token."""
        expired = [token_id for token_id, expiry in self._revoked.items() if expiry <= now]
        for token_id in expired:
            del self._revoked[token_id]
