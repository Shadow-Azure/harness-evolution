"""Pure Asia/Shanghai window, grain, and bucket math for the workspace overview.

Nothing here touches the database: the HTTP boundary parses raw query strings,
this module decides whether the requested window is legal, which grain is
actually returned, and which bucket starts a continuous series must contain.

Window boundaries are inclusive local dates. ``bucket_starts`` only returns the
bucket starts that intersect ``[start, end]``; the trend aggregation fills every
returned bucket, so a day without cases still appears with zero counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.errors import AppError, ErrorCode
from app.utils.time import now_shanghai

Grain = Literal["day", "week", "month"]

GRAINS: tuple[Grain, ...] = ("day", "week", "month")
"""Every grain the trend response may carry."""

RANGE_CHOICES: tuple[int, ...] = (7, 30, 90)
"""The three quick ranges the UI offers; any other value is rejected."""

DEFAULT_RANGE_DAYS = 90
"""Range used when neither explicit boundaries nor a range are supplied."""

MAX_SPAN_DAYS = 366
"""Largest inclusive window accepted; 367 days and beyond is a validation error."""

MIN_SUPPORTED_DATE = date(1970, 1, 1)
"""Earliest local boundary the overview accepts; earlier dates are out of contract."""

MAX_SUPPORTED_DATE = date(2999, 12, 31)
"""Latest local boundary; leaves room for the half-open ``end + 1 day`` predicate."""

DAY_GRAIN_MAX_SPAN = 92
"""Longest inclusive window that keeps day grain; longer spans downgrade to week."""


@dataclass(frozen=True, slots=True)
class Window:
    """One resolved inclusive overview window and its effective grain."""

    start: date
    end: date
    grain: Grain

    @property
    def span_days(self) -> int:
        """Return the inclusive number of local days in this window."""
        return (self.end - self.start).days + 1


def _window_error(reason: str, **details: object) -> AppError:
    """Build the shared 422 failure for an unusable window request."""
    return AppError(
        status_code=422,
        code=ErrorCode.WINDOW_INVALID,
        message=f"invalid overview window: {reason}",
        details={"reason": reason, **details},
    )


def _resolve_range(range_days: int | None) -> int:
    """Return the requested range, defaulting to 90 and rejecting unknown values."""
    if range_days is None:
        return DEFAULT_RANGE_DAYS
    if range_days not in RANGE_CHOICES:
        raise _window_error(
            "unsupported range",
            range=range_days,
            allowed=list(RANGE_CHOICES),
        )
    return range_days


def _resolve_bounds(
    *,
    date_from: date | None,
    date_to: date | None,
    range_days: int,
    today: date,
) -> tuple[date, date]:
    """Resolve inclusive boundaries from explicit dates or an anchored range.

    Both boundaries win over ``range``, which is then ignored even when it is not
    one of the supported values. Exactly one boundary requires an explicit
    ``range``: the supplied boundary anchors the window and the missing side is
    derived so the inclusive length equals ``range_days``. With no boundary at
    all the window ends today.
    """
    if date_from is not None and date_to is not None:
        return date_from, date_to
    if date_from is not None:
        return date_from, date_from + timedelta(days=range_days - 1)
    if date_to is not None:
        return date_to - timedelta(days=range_days - 1), date_to
    return today - timedelta(days=range_days - 1), today


def resolve_window(
    *,
    date_from: date | None,
    date_to: date | None,
    range_days: int | None,
    grain: str,
    today: date | None = None,
) -> Window:
    """Validate the request and return the window plus its effective grain.

    ``grain="day"`` downgrades to ``"week"`` when the inclusive span exceeds 92
    days, so a long range never produces hundreds of day buckets. The downgraded
    grain is what the trend response must expose. Boundaries outside
    ``MIN_SUPPORTED_DATE .. MAX_SUPPORTED_DATE`` and any date arithmetic overflow
    are rejected with ``WINDOW_INVALID`` instead of surfacing a 500.
    """
    if grain not in GRAINS:
        raise AppError(
            status_code=422,
            code=ErrorCode.GRAIN_INVALID,
            message="grain must be one of day, week, month",
            details={"grain": grain, "allowed": list(GRAINS)},
        )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise _window_error(
            "from is after to",
            from_date=date_from.isoformat(),
            to_date=date_to.isoformat(),
        )
    if (date_from is None) != (date_to is None) and range_days is None:
        raise _window_error("a single boundary requires an explicit range")
    # An explicit pair is a complete window, so a leftover ``range`` from the
    # client is ignored rather than validated; only a range that participates in
    # deriving a boundary has to be one of the three supported values.
    resolved_range = (
        DEFAULT_RANGE_DAYS
        if date_from is not None and date_to is not None
        else _resolve_range(range_days)
    )
    try:
        start, end = _resolve_bounds(
            date_from=date_from,
            date_to=date_to,
            range_days=resolved_range,
            today=today or now_shanghai().date(),
        )
    except OverflowError:
        raise _window_error("window is outside the supported date range") from None
    if start < MIN_SUPPORTED_DATE or end > MAX_SUPPORTED_DATE:
        raise _window_error(
            "window is outside the supported date range",
            from_date=start.isoformat(),
            to_date=end.isoformat(),
            minDate=MIN_SUPPORTED_DATE.isoformat(),
            maxDate=MAX_SUPPORTED_DATE.isoformat(),
        )
    span_days = (end - start).days + 1
    if span_days > MAX_SPAN_DAYS:
        raise _window_error(
            "window is longer than 366 days",
            spanDays=span_days,
            maxDays=MAX_SPAN_DAYS,
        )
    effective: Grain = grain
    if effective == "day" and span_days > DAY_GRAIN_MAX_SPAN:
        effective = "week"
    return Window(start=start, end=end, grain=effective)


def bucket_start(day: date, grain: Grain) -> date:
    """Return the start of the bucket containing one local date."""
    if grain == "day":
        return day
    if grain == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _next_bucket(start: date, grain: Grain) -> date:
    """Return the bucket start immediately after ``start`` for this grain."""
    if grain == "week":
        return start + timedelta(days=7)
    if start.month == 12:
        return date(start.year + 1, 1, 1)
    return date(start.year, start.month + 1, 1)


def bucket_starts(window: Window) -> list[date]:
    """Return every bucket start intersecting the window, in ascending order."""
    if window.grain == "day":
        span = (window.end - window.start).days
        return [window.start + timedelta(days=offset) for offset in range(span + 1)]
    starts: list[date] = []
    current = bucket_start(window.start, window.grain)
    while current <= window.end:
        starts.append(current)
        current = _next_bucket(current, window.grain)
    return starts


def bucket_label(start: date, grain: Grain) -> str:
    """Render the short bucket label: ``MM-DD`` for day/week, ``YYYY-MM`` for month."""
    if grain == "month":
        return f"{start.year:04d}-{start.month:02d}"
    return f"{start.month:02d}-{start.day:02d}"
