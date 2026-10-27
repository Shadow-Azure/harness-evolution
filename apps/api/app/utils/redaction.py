"""Shared redaction and bounded diagnostic helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_CREDENTIAL_KEY_PATTERN = (
    r"(?:HE_[A-Z0-9_]+|"
    r"(?:[A-Za-z0-9]+[ _-])*(?:"
    r"password(?:[ _-]?hash)?|passwd|token|secret(?:[ _-]?key)?|"
    r"authorization|api[ _-]?key|credential|private[ _-]?key|"
    r"access[ _-]?key(?:[ _-]?id)?|secret[ _-]?access[ _-]?key))"
)
_AUTHORIZATION_VALUE_PATTERN = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic)\s+[a-z0-9._~+/=-]+",
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)",
)
_QUOTED_SECRET_PATTERN = re.compile(
    rf'(?i)(["\'](?:{_CREDENTIAL_KEY_PATTERN})["\']\s*:\s*)(["\'])[^"\']*\2',
)
_SECRET_PATTERN = re.compile(
    rf"(?i)\b({_CREDENTIAL_KEY_PATTERN})\b(\s*[:=]\s*)"
    r"(?:bearer\s+|basic\s+)?(?:[\"'][^\"']*[\"']|[^\s,;}\]]+)",
)
_PRIVATE_KEY_BLOCK_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.DOTALL,
)
_PROVIDER_CREDENTIAL_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:sk|rk)-(?:(?:proj|svcacct|admin)-)?[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|"
        r"github_pat_[A-Za-z0-9_]{20,})\b",
    ),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
    ),
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")
_DETAIL_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
_SENSITIVE_KEY_SUFFIXES = (
    "password",
    "passwordhash",
    "passwd",
    "token",
    "secret",
    "secretkey",
    "authorization",
    "apikey",
    "privatekey",
    "credential",
)
_SENSITIVE_KEY_PREFIXES = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "apikey",
    "privatekey",
    "credential",
)
_SENSITIVE_NORMALIZED_KEYS = {
    "accesskey",
    "accesskeyid",
    "awsaccesskeyid",
    "awssecretaccesskey",
    "awssessiontoken",
    "secretaccesskey",
}


def redact_text(value: str) -> str:
    """Remove inline credentials and bearer values from free-form text."""
    redacted = _PRIVATE_KEY_BLOCK_PATTERN.sub("<redacted>", value)
    redacted = _AUTHORIZATION_VALUE_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = _URL_CREDENTIAL_PATTERN.sub(r"\1<redacted>\3", redacted)
    redacted = _QUOTED_SECRET_PATTERN.sub(r"\1\2<redacted>\2", redacted)
    redacted = _SECRET_PATTERN.sub(r"\1\2<redacted>", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer <redacted>", redacted)
    for pattern in _PROVIDER_CREDENTIAL_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def is_sensitive_key(key: str) -> bool:
    """Recognize credential keys across snake_case and camelCase payloads."""
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return (
        key.upper().startswith("HE_")
        or normalized in _SENSITIVE_NORMALIZED_KEYS
        or normalized.startswith(_SENSITIVE_KEY_PREFIXES)
        or normalized.endswith(_SENSITIVE_KEY_SUFFIXES)
    )


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
