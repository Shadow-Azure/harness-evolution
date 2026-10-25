"""Asia/Shanghai timestamp helpers for application-managed columns."""

from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    """Return the current timezone-aware Asia/Shanghai timestamp."""
    return datetime.now(SHANGHAI)


def as_shanghai(value: datetime) -> datetime:
    """Normalize a stored timestamp to timezone-aware Asia/Shanghai."""
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)
