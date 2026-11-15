"""Pure window, grain, and bucket math for the workspace overview endpoints."""

from datetime import date, timedelta

import pytest

from app.errors import AppError, ErrorCode
from app.service.overview.window import (
    DEFAULT_RANGE_DAYS,
    Window,
    bucket_label,
    bucket_start,
    bucket_starts,
    resolve_window,
)

TODAY = date(2026, 11, 16)


def _window(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    range_days: int | None = None,
    grain: str = "day",
) -> Window:
    """Resolve a window with today pinned so the tests never depend on the clock."""
    return resolve_window(
        date_from=date_from,
        date_to=date_to,
        range_days=range_days,
        grain=grain,
        today=TODAY,
    )


def _error(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    range_days: int | None = None,
    grain: str = "day",
) -> AppError:
    """Resolve a window that must fail and return its application error."""
    with pytest.raises(AppError) as raised:
        _window(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            grain=grain,
        )
    return raised.value


def test_default_range_is_ninety_days_ending_today() -> None:
    """No boundaries and no range means the last 90 local days inclusive."""
    window = _window()

    assert window.start == date(2026, 8, 19)
    assert window.end == TODAY
    assert window.span_days == DEFAULT_RANGE_DAYS == 90
    assert window.grain == "day"


@pytest.mark.parametrize("range_days", [7, 30, 90])
def test_every_supported_range_keeps_its_inclusive_length(range_days: int) -> None:
    """7/30/90 all end today and cover exactly that many local days."""
    window = _window(range_days=range_days)

    assert window.end == TODAY
    assert window.span_days == range_days
    assert window.start == TODAY - timedelta(days=range_days - 1)


@pytest.mark.parametrize("range_days", [0, 14, 365])
def test_unsupported_range_is_a_window_error(range_days: int) -> None:
    """Only the three quick ranges exist; 0, 14, and 365 are rejected, not clamped."""
    error = _error(range_days=range_days)

    assert error.code is ErrorCode.WINDOW_INVALID
    assert error.status_code == 422
    assert error.details["range"] == range_days


def test_explicit_boundaries_are_inclusive_and_win_over_range() -> None:
    """from/to define the window and a leftover range is ignored, even when invalid."""
    window = _window(
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        range_days=7,
    )
    ignored_zero = _window(
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        range_days=0,
    )

    assert window.start == date(2026, 3, 1)
    assert window.end == date(2026, 3, 31)
    assert window.span_days == 31
    assert ignored_zero.start == date(2026, 3, 1)
    assert ignored_zero.end == date(2026, 3, 31)


@pytest.mark.parametrize(
    ("date_from", "date_to", "range_days"),
    [
        (date(9999, 12, 31), None, 7),
        (None, date(1, 1, 1), 7),
        (date(9999, 1, 1), date(9999, 12, 31), None),
    ],
)
def test_extreme_dates_are_a_window_error(
    date_from: date | None,
    date_to: date | None,
    range_days: int | None,
) -> None:
    """Dates whose arithmetic overflows or fall outside the contract are a 422, not a 500."""
    error = _error(date_from=date_from, date_to=date_to, range_days=range_days)

    assert error.code is ErrorCode.WINDOW_INVALID
    assert error.status_code == 422
    assert error.details["reason"] == "window is outside the supported date range"


def test_supported_date_range_boundaries_are_inclusive() -> None:
    """The documented 1970..2999 contract accepts windows at both endpoints."""
    earliest = _window(date_from=date(1970, 1, 1), date_to=date(1970, 1, 7))
    latest = _window(
        date_from=date(2999, 12, 25),
        date_to=date(2999, 12, 31),
        grain="month",
    )

    assert (earliest.start, earliest.end) == (date(1970, 1, 1), date(1970, 1, 7))
    assert (latest.start, latest.end) == (date(2999, 12, 25), date(2999, 12, 31))
    assert latest.grain == "month"


def test_single_day_window_has_one_bucket() -> None:
    """from == to is a legal one-day window."""
    window = _window(date_from=date(2026, 11, 16), date_to=date(2026, 11, 16))

    assert window.span_days == 1
    assert bucket_starts(window) == [date(2026, 11, 16)]


def test_from_after_to_is_a_window_error() -> None:
    """A reversed window is rejected instead of silently swapped."""
    error = _error(date_from=date(2026, 11, 17), date_to=date(2026, 11, 16))

    assert error.code is ErrorCode.WINDOW_INVALID
    assert error.details["from_date"] == "2026-11-17"


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [(date(2026, 1, 1), None), (None, date(2026, 1, 1))],
)
def test_single_boundary_without_range_is_a_window_error(
    date_from: date | None,
    date_to: date | None,
) -> None:
    """One boundary only works together with an explicit range."""
    error = _error(date_from=date_from, date_to=date_to)

    assert error.code is ErrorCode.WINDOW_INVALID
    assert error.details["reason"] == "a single boundary requires an explicit range"


def test_single_boundary_with_range_keeps_the_range_length() -> None:
    """The supplied boundary anchors the window and the range preserves its length."""
    from_only = _window(date_from=date(2026, 11, 1), range_days=7)
    to_only = _window(date_to=date(2026, 11, 1), range_days=7)

    assert (from_only.start, from_only.end) == (date(2026, 11, 1), date(2026, 11, 7))
    assert (to_only.start, to_only.end) == (date(2026, 10, 26), date(2026, 11, 1))
    assert from_only.span_days == to_only.span_days == 7


def test_span_of_367_days_is_rejected_and_366_is_accepted() -> None:
    """The hard ceiling is 366 inclusive days."""
    start = date(2026, 1, 1)
    longest = _window(date_from=start, date_to=start + timedelta(days=365))
    too_long = _error(date_from=start, date_to=start + timedelta(days=366))

    assert longest.span_days == 366
    assert too_long.code is ErrorCode.WINDOW_INVALID
    assert too_long.details["spanDays"] == 367


def test_day_grain_survives_up_to_92_days() -> None:
    """92 inclusive days still returns day grain and 92 buckets."""
    window = _window(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 1) + timedelta(days=91),
        grain="day",
    )

    assert window.span_days == 92
    assert window.grain == "day"
    assert len(bucket_starts(window)) == 92


def test_day_grain_downgrades_to_week_after_92_days() -> None:
    """93 day-grain days become week buckets and the response carries week."""
    window = _window(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 4, 3),
        grain="day",
    )

    assert window.span_days == 93
    assert window.grain == "week"


def test_explicit_week_and_month_grains_are_never_downgraded() -> None:
    """Only day grain downgrades; week and month stay as requested."""
    week = _window(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        grain="week",
    )
    month = _window(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        grain="month",
    )

    assert week.grain == "week"
    assert month.grain == "month"


def test_unknown_grain_is_a_grain_error() -> None:
    """An unknown grain reports GRAIN_INVALID rather than the generic 422."""
    error = _error(grain="hour")

    assert error.code is ErrorCode.GRAIN_INVALID
    assert error.status_code == 422
    assert error.details["allowed"] == ["day", "week", "month"]


def test_day_buckets_are_continuous_across_a_year_boundary() -> None:
    """Day buckets never skip a local date, including 12-31 to 01-01."""
    window = _window(date_from=date(2026, 12, 30), date_to=date(2027, 1, 2))

    assert bucket_starts(window) == [
        date(2026, 12, 30),
        date(2026, 12, 31),
        date(2027, 1, 1),
        date(2027, 1, 2),
    ]
    assert [bucket_label(day, "day") for day in bucket_starts(window)] == [
        "12-30",
        "12-31",
        "01-01",
        "01-02",
    ]


def test_leap_day_belongs_to_its_own_day_bucket() -> None:
    """2028-02-29 is a bucket of its own."""
    window = _window(date_from=date(2028, 2, 28), date_to=date(2028, 3, 1))

    assert date(2028, 2, 29) in bucket_starts(window)
    assert len(bucket_starts(window)) == 3


def test_month_buckets_use_the_first_of_each_month() -> None:
    """Month buckets start on the 1st and cover every touched month once."""
    window = _window(date_from=date(2026, 1, 15), date_to=date(2026, 4, 2), grain="month")

    starts = bucket_starts(window)

    assert starts == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]
    assert [bucket_label(day, "month") for day in starts] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
    ]


def test_month_buckets_cross_the_year_boundary() -> None:
    """December rolls into January of the next year without a gap."""
    window = _window(date_from=date(2026, 11, 20), date_to=date(2027, 1, 3), grain="month")

    assert bucket_starts(window) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]


def test_week_buckets_start_on_iso_monday() -> None:
    """ISO weeks start Monday, including a week that spans month and year ends."""
    window = _window(date_from=date(2026, 12, 30), date_to=date(2027, 1, 12), grain="week")

    starts = bucket_starts(window)

    assert starts == [date(2026, 12, 28), date(2027, 1, 4), date(2027, 1, 11)]
    assert all(day.weekday() == 0 for day in starts)
    assert [bucket_label(day, "week") for day in starts] == ["12-28", "01-04", "01-11"]


def test_week_bucket_contains_its_days_and_never_before_the_window() -> None:
    """The first bucket starts before ``start`` when the window opens mid-week."""
    window = _window(date_from=date(2026, 11, 11), date_to=date(2026, 11, 12), grain="week")

    assert window.start.weekday() == 2
    assert bucket_starts(window) == [date(2026, 11, 9)]
    assert bucket_start(date(2026, 11, 12), "week") == date(2026, 11, 9)


def test_bucket_start_maps_every_grain() -> None:
    """bucket_start is the pure mapping used by the trend aggregation."""
    assert bucket_start(date(2026, 11, 11), "day") == date(2026, 11, 11)
    assert bucket_start(date(2026, 11, 11), "week") == date(2026, 11, 9)
    assert bucket_start(date(2026, 11, 11), "month") == date(2026, 11, 1)
