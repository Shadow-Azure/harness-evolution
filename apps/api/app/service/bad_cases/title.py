"""Derive a displayable short title for externally owned issues."""

from __future__ import annotations

import re

UNNAMED_TITLE = "未命名问题"
TITLE_MAX_LENGTH = 255
_SENTENCE_END = re.compile(r"[。！？!?；;\n]|\.(?=\s|$)")  # noqa: RUF001


def _usable_title(value: object) -> str | None:
    """Return a stripped external title when it is a non-blank string."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _first_sentence(value: object) -> str | None:
    """Return the first sentence of an external description, if usable."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = _SENTENCE_END.search(text)
    if match is not None:
        text = text[: match.end()].strip()
    return text or None


def derive_title(title: object, description: object) -> tuple[str, bool]:
    """Return one displayable short title and whether it was derived.

    The external ``title`` value is authoritative when it is a non-blank string.
    When an external row carries a NULL, empty, or blank title, the description's
    first sentence becomes the display title; when neither field is usable the
    response falls back to :data:`UNNAMED_TITLE`. Derived titles are clamped to
    the storage width of the short-title column so the read model never exceeds
    what the column can hold.

    Args:
        title: External short title as read from the database boundary.
        description: External description body used as the fallback source.

    Returns:
        A tuple of the display title and whether it was derived because the
        external title was unusable.
    """
    external = _usable_title(title)
    if external is not None:
        return external[:TITLE_MAX_LENGTH], False
    sentence = _first_sentence(description)
    if sentence is None:
        return UNNAMED_TITLE, True
    return sentence[:TITLE_MAX_LENGTH], True
