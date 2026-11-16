"""MCP knowledge-provider adapters and privacy-safe document evidence.

Only explicitly whitelisted MCP tool names are recognized. Provider responses are
parsed for document identity and revision; document bodies, chunks, and raw
responses are never retained. Malformed or unexpected payloads yield no events.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

KnowledgeRetrievalKind = Literal["file_read", "mcp_search", "mcp_retrieve"]

MAX_KNOWLEDGE_DOCUMENTS = 100
"""Maximum documents one retrieval result may contribute as evidence."""

_MAX_DOCUMENT_ID = 255
_MAX_DOCUMENT_REVISION = 96
_MAX_TITLE = 255
_MAX_COLLECTION = 255
_MAX_SOURCE_PATH = 1024

_ID_KEYS = ("id", "documentId", "document_id")
_PATH_KEYS = ("path", "sourcePath", "source_path")
_REVISION_KEYS = ("revision", "version", "digest", "contentHash")
_TITLE_KEYS = ("title", "name")
_COLLECTION_KEYS = ("collection", "collectionId")
_LIST_KEYS = ("documents", "results", "items")


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """One document returned by a knowledge provider or a file read."""

    document_id: str
    revision: str
    source_path: str | None
    title: str | None
    collection: str | None
    retrieval_kind: KnowledgeRetrievalKind


@dataclass(frozen=True, slots=True)
class McpKnowledgeAdapter:
    """One whitelisted MCP knowledge tool family and its result parser."""

    tool_names: tuple[str, ...]
    retrieval_kind: KnowledgeRetrievalKind
    default_scope: str

    def parse(self, text: str | None) -> tuple[KnowledgeDocument, ...]:
        """Parse one tool result into stable, deduplicated document identities."""
        records = _decode_documents(text)
        if not records:
            return ()
        documents: list[KnowledgeDocument] = []
        for record in records:
            document = _document(record, self.retrieval_kind)
            if document is not None:
                documents.append(document)
            if len(documents) >= MAX_KNOWLEDGE_DOCUMENTS:
                break
        unique = {
            (document.document_id, document.source_path or "", document.revision): document
            for document in documents
        }
        return tuple(unique[key] for key in sorted(unique))


_SEARCH_TOOL_NAMES = (
    "mcp__knowledge__search",
    "mcp__knowledge-base__search",
    "mcp__knowledge_base__search",
    "mcp__kb__search",
)
_RETRIEVE_TOOL_NAMES = (
    "mcp__knowledge__retrieve",
    "mcp__kb__retrieve",
)

MCP_KNOWLEDGE_ADAPTERS: tuple[McpKnowledgeAdapter, ...] = (
    McpKnowledgeAdapter(
        tool_names=_SEARCH_TOOL_NAMES,
        retrieval_kind="mcp_search",
        default_scope="mcp_search",
    ),
    McpKnowledgeAdapter(
        tool_names=_RETRIEVE_TOOL_NAMES,
        retrieval_kind="mcp_retrieve",
        default_scope="mcp_retrieve",
    ),
)
"""Every supported MCP knowledge tool family; no fuzzy name matching exists."""

MCP_KNOWLEDGE_TOOL_NAMES: tuple[str, ...] = (
    "mcp__knowledge__search",
    "mcp__knowledge__retrieve",
    "mcp__knowledge-base__search",
    "mcp__knowledge_base__search",
    "mcp__kb__search",
    "mcp__kb__retrieve",
)
"""Explicit whitelist in documented order; a lookalike name is not knowledge."""

_ADAPTERS_BY_TOOL: dict[str, McpKnowledgeAdapter] = {
    name: adapter for adapter in MCP_KNOWLEDGE_ADAPTERS for name in adapter.tool_names
}


def knowledge_adapter_for(tool_name: str | None) -> McpKnowledgeAdapter | None:
    """Return the adapter owning one exact tool name, if it is whitelisted."""
    if not tool_name:
        return None
    return _ADAPTERS_BY_TOOL.get(tool_name)


def _decode_documents(text: str | None) -> tuple[dict[str, object], ...] | None:
    """Decode a single JSON document, a list envelope, or NDJSON records."""
    if text is None or not text.strip():
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _decode_ndjson(text)
    if isinstance(parsed, dict):
        for key in _LIST_KEYS:
            if key in parsed:
                value = parsed[key]
                if not isinstance(value, list):
                    return None
                return tuple(item for item in value if isinstance(item, dict))
        return (parsed,)
    if isinstance(parsed, list):
        return tuple(item for item in parsed if isinstance(item, dict))
    return None


def _decode_ndjson(text: str) -> tuple[dict[str, object], ...] | None:
    """Decode one object per line, treating any broken line as no evidence."""
    records: list[dict[str, object]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(item, dict):
            return None
        records.append(item)
    return tuple(records) or None


def _text_field(
    record: dict[str, object],
    keys: tuple[str, ...],
    limit: int,
) -> str | None:
    """Read the first non-empty string field without touching body fields."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return None


def _document(
    record: dict[str, object],
    retrieval_kind: KnowledgeRetrievalKind,
) -> KnowledgeDocument | None:
    """Project one provider record onto the stored document evidence."""
    source_path = _text_field(record, _PATH_KEYS, _MAX_SOURCE_PATH)
    document_id = _text_field(record, _ID_KEYS, _MAX_DOCUMENT_ID)
    if document_id is None:
        if source_path is None:
            return None
        digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:32]
        document_id = f"doc:{digest}"
    revision = _text_field(record, _REVISION_KEYS, _MAX_DOCUMENT_REVISION) or "unknown"
    return KnowledgeDocument(
        document_id=document_id,
        revision=revision,
        source_path=source_path,
        title=_text_field(record, _TITLE_KEYS, _MAX_TITLE),
        collection=_text_field(record, _COLLECTION_KEYS, _MAX_COLLECTION),
        retrieval_kind=retrieval_kind,
    )


__all__ = [
    "MAX_KNOWLEDGE_DOCUMENTS",
    "MCP_KNOWLEDGE_ADAPTERS",
    "MCP_KNOWLEDGE_TOOL_NAMES",
    "KnowledgeDocument",
    "KnowledgeRetrievalKind",
    "McpKnowledgeAdapter",
    "knowledge_adapter_for",
]
