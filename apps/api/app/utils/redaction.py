"""Shared redaction and bounded diagnostic helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[_-]?key)\b"
    r"\s*[:=]\s*(?:bearer\s+)?\S+",
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_ENV_SECRET_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:PASSWORD|TOKEN|SECRET|KEY|AUTH|CREDENTIAL)[A-Z0-9_]*)"
    r"=([^\s]+)",
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")
_DETAIL_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
_SENSITIVE_KEY_SUFFIXES = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "apikey",
    "credential",
)


def redact_text(value: str) -> str:
    """Remove inline credentials and bearer values from free-form text."""
    redacted = _SECRET_PATTERN.sub(r"\1=<redacted>", value)
    redacted = _ENV_SECRET_PATTERN.sub(r"\1=<redacted>", redacted)
    return _BEARER_PATTERN.sub("Bearer <redacted>", redacted)


def is_sensitive_key(key: str) -> bool:
    """Recognize credential keys across snake_case and camelCase payloads."""
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized.endswith(_SENSITIVE_KEY_SUFFIXES)


def sanitize_value(value: Any) -> Any:
    """Recursively redact credentials before a value becomes durable."""
    if isinstance(value, Mapping):
        return {
            str(key): ("<redacted>" if is_sensitive_key(str(key)) else sanitize_value(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def sanitize_message(message: str, *, limit: int = 512) -> str:
    """Redact and bound one single-line human-readable event summary."""
    compact = " ".join(message.splitlines()).strip()
    if not compact:
        return "event"
    return redact_text(_CONTROL_PATTERN.sub(" ", compact))[:limit]


def sanitize_detail(detail: str | None, *, limit: int = 8_192) -> str | None:
    """Redact diagnostics while preserving readable stack lines and an 8KB cap."""
    if detail is None:
        return None
    normalized = detail.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _DETAIL_CONTROL_PATTERN.sub("", normalized)
    return truncate_utf8(redact_text(normalized), limit=limit)


def sanitize_job_payload(value: Any) -> Any:
    """Recursively redact credential fields before a job payload becomes durable."""
    return sanitize_value(value)


def sanitize_job_error(message: str, *, limit: int = 2_000) -> str:
    """Redact credentials, collapse controls, and bound persisted failure text."""
    compact = " ".join(message.splitlines()).strip()
    if not compact:
        return "job failed"
    redacted = redact_text(compact)
    redacted = _CONTROL_PATTERN.sub(" ", redacted)
    return truncate_utf8(redacted, limit=limit)


def truncate_utf8(value: str, *, limit: int) -> str:
    """Return the longest whole-character prefix whose UTF-8 encoding fits the byte cap."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    encoded = value.encode()
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode(errors="ignore")
