"""Automatic blocked-run backoff schedule shared by the sweeper and retry."""

from __future__ import annotations

from datetime import datetime, timedelta

RETRY_BACKOFF_MINUTES: tuple[int, ...] = (1, 5, 15)
MAX_RETRY_ATTEMPTS: int = len(RETRY_BACKOFF_MINUTES)


def next_retry_delay(attempts: int) -> timedelta | None:
    """Return the delay after ``attempts`` completed automatic retries.

    The design ladder is frozen at ``0 -> 1min``, ``1 -> 5min``, ``2 -> 15min``
    and ``>= 3 -> None`` (no further automatic retry). Non-integer and negative
    inputs are rejected so a corrupt counter can never invent a schedule.
    """
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise TypeError("retry attempts must be an integer")
    if attempts < 0:
        raise ValueError("retry attempts must not be negative")
    if attempts >= MAX_RETRY_ATTEMPTS:
        return None
    return timedelta(minutes=RETRY_BACKOFF_MINUTES[attempts])


def next_retry_at(now: datetime, attempts: int) -> datetime | None:
    """Return the absolute next-attempt deadline for one retry counter."""
    delay = next_retry_delay(attempts)
    return None if delay is None else now + delay


__all__ = [
    "MAX_RETRY_ATTEMPTS",
    "RETRY_BACKOFF_MINUTES",
    "next_retry_at",
    "next_retry_delay",
]
