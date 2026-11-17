"""The deployed entry point must render structured logging extras."""

from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.logging import KeyValueFormatter, configure_logging


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        1,
        message,
        (),
        None,
    )


def test_formatter_appends_sorted_structured_extras() -> None:
    """Extras become ``key=value`` pairs on the same physical line."""
    record = _record("upstream pull health")
    record.event = "upstream.health"
    record.status = "ok"
    record.sessions_requested = 2
    line = KeyValueFormatter("%(levelname)s %(message)s").format(record)
    assert line.startswith("INFO upstream pull health ")
    assert "event='upstream.health'" in line
    assert "status='ok'" in line
    assert "sessions_requested=2" in line
    assert "\n" not in line


def test_formatter_keeps_records_without_extras_clean() -> None:
    """A plain record is not padded with empty fields."""
    line = KeyValueFormatter("%(levelname)s %(message)s").format(_record("plain"))
    assert line == "INFO plain"


def test_formatter_escapes_embedded_newlines() -> None:
    """A multi-line value cannot forge a second log record."""
    record = _record("contract drift")
    record.reason = "line one\nline two"
    line = KeyValueFormatter("%(message)s").format(record)
    assert "\n" not in line
    assert "reason='line one\\nline two'" in line


def test_configure_logging_is_idempotent_and_renders_extras(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One root handler is installed and real records include their extras."""
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("m12-01-logging-test-secret-with-length"),
        log_level="debug",
    )
    try:
        configure_logging(settings)
        configure_logging(settings)
        structured = [
            handler for handler in root.handlers if getattr(handler, "_harness_evolution", False)
        ]
        assert len(structured) == 1
        assert root.level == logging.DEBUG
        logging.getLogger("app.test.upstream").info(
            "upstream pull health",
            extra={"event": "upstream.health", "status": "ok"},
        )
        captured = capsys.readouterr()
        assert "event='upstream.health'" in captured.err
        assert "status='ok'" in captured.err
    finally:
        for handler in list(root.handlers):
            if handler not in previous_handlers:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(previous_level)
