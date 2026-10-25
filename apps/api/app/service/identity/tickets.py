"""One-time in-memory grants for future Server-Sent Events connections."""

import base64
import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_bytes, token_urlsafe
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
        self._clock = clock
        self._signing_key = token_bytes(32)
        self._grants: dict[str, tuple[EventTicketGrant, float]] = {}
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
        """Bind the issuing user, topics, and cursor to one signed opaque ticket."""
        ticket_id = token_urlsafe(32)
        grant = EventTicketGrant(
            user_id=user_id,
            topics=tuple(topics),
            last_event_id=last_event_id,
        )
        with self._lock:
            now = self._clock()
            self._prune_expired_locked(now)
            expires_at = now + self._ttl_seconds
            self._grants[ticket_id] = (grant, expires_at)
        return self._encode_ticket(ticket_id, expires_at)

    def consume(self, ticket: str) -> EventTicketGrant:
        """Remove a ticket and distinguish expiry from replay or absence."""
        parsed = self._decode_ticket(ticket)
        if parsed is None:
            raise self._invalid_ticket()
        ticket_id, expires_at = parsed
        with self._lock:
            now = self._clock()
            saved = self._grants.pop(ticket_id, None)
            self._prune_expired_locked(now)
        if now >= expires_at:
            raise AppError(
                status_code=401,
                code=ErrorCode.TICKET_EXPIRED,
                message="event ticket has expired",
            )
        if saved is None:
            raise self._invalid_ticket()
        grant, _ = saved
        return grant

    def _prune_expired_locked(self, now: float) -> None:
        """Remove expired grants while the caller holds the store lock."""
        expired = [ticket_id for ticket_id, (_, expiry) in self._grants.items() if expiry <= now]
        for ticket in expired:
            del self._grants[ticket]

    def _encode_ticket(self, ticket_id: str, expires_at: float) -> str:
        """Append an authenticated microsecond expiry to an opaque random id."""
        expiry_us = int(expires_at * 1_000_000)
        payload = f"{ticket_id}.{expiry_us}"
        signature = self._sign(payload)
        return f"{payload}.{signature}"

    def _decode_ticket(self, ticket: str) -> tuple[str, float] | None:
        """Validate ticket shape and signature before reading its expiry."""
        parts = ticket.split(".")
        if len(parts) != 3:
            return None
        ticket_id, expiry_text, signature = parts
        if not ticket_id or not expiry_text.isdigit():
            return None
        if not signature.isascii():
            return None
        payload = f"{ticket_id}.{expiry_text}"
        if not hmac.compare_digest(signature, self._sign(payload)):
            return None
        return ticket_id, int(expiry_text) / 1_000_000

    def _sign(self, payload: str) -> str:
        """Return a URL-safe HMAC over a ticket id and expiry."""
        digest = hmac.new(self._signing_key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    @staticmethod
    def _invalid_ticket() -> AppError:
        """Return the stable failure for malformed, unknown, or replayed tickets."""
        return AppError(
            status_code=401,
            code=ErrorCode.TICKET_INVALID,
            message="event ticket is invalid or already used",
        )
