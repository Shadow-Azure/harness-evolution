"""Canonical knowledge-root paths, root matching, and document identities.

A workspace declares the document roots whose reads count as knowledge triggers.
The rules live here so workspace configuration, parser evidence, and replay all
share one canonical form: forward slashes, no trailing separator, absolute, no
parent traversal, bounded count and length.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

MAX_KNOWLEDGE_ROOTS = 20
"""Maximum number of knowledge roots one workspace may configure."""

MAX_KNOWLEDGE_ROOT_LENGTH = 512
"""Maximum length of one canonical knowledge root."""

_MAX_DOCUMENT_ID = 255
_DUPLICATE_SLASHES = re.compile(r"/{2,}")


class KnowledgeRootError(ValueError):
    """One configured knowledge root cannot be canonicalized."""

    def __init__(self, reason: str, index: int = 0) -> None:
        """Keep the stable reason and position without echoing the path."""
        self.reason = reason
        self.index = index
        super().__init__(f"invalid knowledge root at index {index}: {reason}")


def _canonical_root(value: object, index: int) -> str | None:
    """Return the canonical absolute root or raise a stable reason."""
    if not isinstance(value, str):
        raise KnowledgeRootError("not_a_string", index)
    text = value.strip().replace("\\", "/")
    if not text:
        return None
    if "\x00" in text:
        raise KnowledgeRootError("nul_byte", index)
    if not text.startswith("/"):
        raise KnowledgeRootError("not_absolute", index)
    if ".." in text.split("/"):
        raise KnowledgeRootError("parent_traversal", index)
    text = _DUPLICATE_SLASHES.sub("/", text)
    if len(text) > MAX_KNOWLEDGE_ROOT_LENGTH:
        raise KnowledgeRootError("too_long", index)
    return text.rstrip("/") or "/"


def normalize_knowledge_roots(values: Iterable[object] | None) -> tuple[str, ...]:
    """Canonicalize one workspace's roots, preserving order and dropping duplicates."""
    if values is None:
        return ()
    items: Iterable[object] = (values,) if isinstance(values, str) else values
    roots: list[str] = []
    for index, value in enumerate(items):
        root = _canonical_root(value, index)
        if root is None or root in roots:
            continue
        roots.append(root)
        if len(roots) > MAX_KNOWLEDGE_ROOTS:
            raise KnowledgeRootError("too_many", index)
    return tuple(roots)


def _canonical_document_path(value: str) -> str | None:
    """Return an absolute path that is safe to compare against configured roots."""
    text = value.strip().replace("\\", "/")
    if not text or "\x00" in text or not text.startswith("/"):
        return None
    if ".." in text.split("/"):
        return None
    return _DUPLICATE_SLASHES.sub("/", text).rstrip("/") or "/"


def match_knowledge_root(path: str | None, roots: Iterable[str]) -> str | None:
    """Return the longest configured root containing ``path``, if any.

    Matching is segment-aligned: ``/kb`` covers ``/kb/a.md`` but never
    ``/kb2/a.md``. Relative or traversal paths never match.
    """
    if path is None:
        return None
    candidate = _canonical_document_path(path)
    if candidate is None:
        return None
    matched: str | None = None
    for root in roots:
        if root == "/":
            contained = candidate.startswith("/")
        else:
            contained = candidate == root or candidate.startswith(root + "/")
        if contained and (matched is None or len(root) > len(matched)):
            matched = root
    return matched


def knowledge_document_id(path: str, root: str) -> str:
    """Derive a stable document identity from the root-relative path."""
    relative = path[len(root) :] if root != "/" else path
    relative = relative.lstrip("/")
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:32]
    return f"doc:{digest}"[:_MAX_DOCUMENT_ID]
