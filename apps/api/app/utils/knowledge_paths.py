"""Canonical knowledge-root paths, root matching, and document identities.

A workspace declares the document roots whose reads count as knowledge triggers.
The rules live here so workspace configuration, parser evidence, and replay all
share one canonical form: POSIX absolute paths, forward slashes, no trailing
separator, no parent traversal, bounded count and length on write.

Paths are POSIX-only by design. A Windows drive path (``C:/kb``) is not absolute
under these rules; the deployment targets macOS and Linux.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

MAX_KNOWLEDGE_ROOTS = 20
"""Maximum number of knowledge roots one workspace may configure."""

MAX_KNOWLEDGE_ROOT_LENGTH = 512
"""Maximum length of one canonical knowledge root."""

MAX_DOCUMENT_PATH_LENGTH = 1024
"""Maximum length of one stored document source path."""

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
    root = text.rstrip("/") or "/"
    if root == "/":
        raise KnowledgeRootError("too_broad", index)
    return root


def normalize_knowledge_roots(values: Iterable[object] | None) -> tuple[str, ...]:
    """Canonicalize one workspace's roots for storage, enforcing write limits."""
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


def merge_knowledge_roots(values: Iterable[object] | None) -> tuple[str, ...]:
    """Canonicalize and dedupe a read-side union of workspace roots.

    Replay merges the roots of every workspace that reported one root session, so
    the write-side per-workspace limit must not apply here. Invalid stored values
    are ignored instead of failing the whole replay.
    """
    if values is None:
        return ()
    items: Iterable[object] = (values,) if isinstance(values, str) else values
    roots: list[str] = []
    for index, value in enumerate(items):
        try:
            root = _canonical_root(value, index)
        except KnowledgeRootError:
            continue
        if root is None or root in roots:
            continue
        roots.append(root)
    return tuple(roots)


def decode_knowledge_roots(value: object) -> tuple[str, ...]:
    """Decode one stored JSON root array, tolerating a JSON string payload."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def canonical_knowledge_path(path: str | None) -> str | None:
    """Return the canonical absolute document path, or ``None`` when unusable."""
    if path is None:
        return None
    text = path.strip().replace("\\", "/")
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
    candidate = canonical_knowledge_path(path)
    if candidate is None:
        return None
    matched: str | None = None
    for root in roots:
        contained = candidate == root or candidate.startswith(root + "/")
        if contained and (matched is None or len(root) > len(matched)):
            matched = root
    return matched


def knowledge_document_id(path: str, root: str) -> str:
    """Derive a stable document identity from the canonical root-relative path."""
    canonical = canonical_knowledge_path(path) or path.replace("\\", "/").strip()
    if canonical == root:
        relative = ""
    elif canonical.startswith(root + "/"):
        relative = canonical[len(root) :]
    else:
        relative = canonical
    relative = relative.lstrip("/")
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:32]
    return f"doc:{digest}"[:_MAX_DOCUMENT_ID]
