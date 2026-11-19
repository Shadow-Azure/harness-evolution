"""Shared definition-body normalization and identity hashing.

The trace parser and the target content resolver must use one implementation:
the same body extraction and normalization has to produce the same digest on
both sides of the attribution. ``normalize_definition_body`` strips
runtime-added suffixes and line-ending noise; ``definition_hash`` hashes only
the normalized body, so a provider source path can never change the identity.
"""

from __future__ import annotations

import hashlib
import re

_COMMON_DEFINITION_SUFFIX = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"(?:subagent\s+permissions?|permission\s+notes?|agent\s+notes?|notes|token\s+budget)\b",
    re.IGNORECASE,
)


def normalize_definition_body(text: str) -> str | None:
    """Strip runtime-added common suffixes before hashing a definition body."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    lines = normalized.split("\n")
    cut = len(lines)
    for index, line in enumerate(lines):
        if _COMMON_DEFINITION_SUFFIX.match(line):
            cut = index
            break
    body = "\n".join(lines[:cut]).rstrip()
    return body or None


def definition_hash(text: str) -> str | None:
    """Hash a normalized definition body without retaining its source text."""
    body = normalize_definition_body(text)
    if body is None:
        return None
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def digest_revision(text: str) -> str | None:
    """Return the normalized ``digest:`` revision for one definition body."""
    digest = definition_hash(text)
    return None if digest is None else f"digest:{digest}"
