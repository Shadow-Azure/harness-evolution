"""Stable sortable identifier generation."""

from ulid import ULID


def new_id() -> str:
    """Return a sortable 26-character identifier suitable for string primary keys."""
    return str(ULID())
