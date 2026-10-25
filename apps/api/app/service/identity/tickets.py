"""One-time in-memory grants for future Server-Sent Events connections."""

from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_urlsafe
from threading import Lock
from time import monotonic

from app.errors import AppError, ErrorCode


@dataclass(frozen=True, slots=True)
class EventTicketGrant:
    """Issuing principal, topics, and replay cursor authorized by one ticket."""

    user_id: str
    topics: tuple[str, ...]
    last_event_id: int


class TicketStore:
    """Issue short-lived topic grants and consume each exactly once."""

    def __init__(
        self,
        ttl_seconds: int = 60,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Create a bounded, thread-safe store for one application process."""
        self._ttl_seconds = ttl_seconds
        self._expired_retention_seconds = max(ttl_seconds, 60)
        self._clock = clock
        self._grants: dict[str, tuple[EventTicketGrant, float]] = {}
        self._expired: dict[str, float] = {}
        self._lock = Lock()

    @property
    def expires_in(self) -> int:
        """Return the issued ticket lifetime in whole seconds."""
        return self._ttl_seconds

    @property
    def active_count(self) -> int:
        """Return the number of unexpired, unconsumed grants."""
        with self._lock:
            self._prune_expired_locked(self._clock())
            return len(self._grants)

    def issue(self, *, user_id: str, topics: tuple[str, ...], last_event_id: int) -> str:
        """Bind the issuing user, topics, and cursor to one opaque ticket."""
        ticket = token_urlsafe(32)
        grant = EventTicketGrant(
            user_id=user_id,
            topics=tuple(topics),
            last_event_id=last_event_id,
        )
        with self._lock:
            now = self._clock()
            self._prune_expired_locked(now)
            self._grants[ticket] = (grant, now + self._ttl_seconds)
        return ticket

    def consume(self, ticket: str) -> EventTicketGrant:
        """Remove a ticket and distinguish expiry from replay or absence."""
        with self._lock:
            now = self._clock()
            saved = self._grants.pop(ticket, None)
            expired = ticket in self._expired
            if saved is not None:
                grant, expires_at = saved
                expired = now >= expires_at
                if expired:
                    self._expired[ticket] = now + self._expired_retention_seconds
            self._prune_expired_locked(now)
        if expired:
            raise AppError(
                status_code=401,
                code=ErrorCode.TICKET_EXPIRED,
                message="event ticket has expired",
            )
        if saved is None:
            raise AppError(
                status_code=401,
                code=ErrorCode.TICKET_INVALID,
                message="event ticket is invalid or already used",
            )
        return grant

    def _prune_expired_locked(self, now: float) -> None:
        """Remove expired grants while the caller holds the store lock."""
        stale_tombstones = [
            ticket for ticket, retain_until in self._expired.items() if retain_until <= now
        ]
        for ticket in stale_tombstones:
            del self._expired[ticket]
        expired = [ticket for ticket, (_, expiry) in self._grants.items() if expiry <= now]
        for ticket in expired:
            del self._grants[ticket]
            self._expired[ticket] = now + self._expired_retention_seconds
