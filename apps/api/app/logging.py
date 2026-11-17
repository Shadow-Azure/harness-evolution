"""One-line structured logging for the deployed API entry point."""

from __future__ import annotations

import logging

from app.config import Settings

_STANDARD_ATTRIBUTES = frozenset(
    {
        *logging.LogRecord("", 0, "", 0, "", (), None).__dict__,
        "asctime",
        "message",
        "taskName",
    },
)


class KeyValueFormatter(logging.Formatter):
    """Render the human message plus bounded ``key=value`` structured extras."""

    def format(self, record: logging.LogRecord) -> str:
        """Append every non-standard record field on the same physical line."""
        rendered = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_")
        }
        if not extras:
            return rendered
        pairs = " ".join(f"{key}={value!r}" for key, value in sorted(extras.items()))
        return f"{rendered} {pairs}"


def configure_logging(settings: Settings) -> None:
    """Install one idempotent root handler that emits the configured level."""
    root = logging.getLogger()
    handler = next(
        (item for item in root.handlers if getattr(item, "_harness_evolution", False)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(
            KeyValueFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
        )
        handler._harness_evolution = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
