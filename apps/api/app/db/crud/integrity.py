"""Classification of SQLAlchemy integrity failures across supported dialects."""

from sqlalchemy.exc import IntegrityError

_UNIQUE_MARKERS = (
    "unique constraint failed",
    "duplicate entry",
    "unique violation",
)


def is_unique_violation(error: IntegrityError) -> bool:
    """Return whether a driver integrity error is a uniqueness failure.

    SQLite and MySQL word the same constraint failure differently, and both
    adapters surface the original driver exception without a shared error code,
    so the markers are matched against the driver message. Those two dialects
    are the only ones this repository supports.
    """
    message = str(error.orig).lower()
    return any(marker in message for marker in _UNIQUE_MARKERS)
