"""MCP knowledge adapter whitelist, parsing, and multi-document events."""

from __future__ import annotations

import json

from app.service.acquisition.agent_tree import assemble_agent_trees
from app.service.acquisition.knowledge import (
    MCP_KNOWLEDGE_TOOL_NAMES,
    McpKnowledgeAdapter,
    knowledge_adapter_for,
)
from app.service.acquisition.normalize import ParsedTranscript, normalize_transcript

ROOT_ID = "91000000-0000-4000-8000-000000000001"
KNOWLEDGE_ROOT = "/workspace/knowledge"


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(text: str = "synthetic task") -> dict[str, object]:
    """Build one user turn with an explicit timestamp."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:00:00Z",
        "message": {"content": text},
    }


def mcp_call(
    tool_id: str,
    tool_name: str,
    *,
    message_id: str | None = None,
    timestamp: str = "2026-11-16T01:01:00Z",
) -> dict[str, object]:
    """Build one assistant record holding a single MCP tool call."""
    return {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": message_id or f"message-{tool_id}",
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": {"query": "synthetic query"},
                },
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    }


def mcp_result(
    tool_id: str,
    text: str,
    *,
    is_error: bool = False,
    timestamp: str = "2026-11-16T01:02:00Z",
) -> dict[str, object]:
    """Build one MCP tool result whose text content carries the provider payload."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "is_error": is_error,
                    "content": [{"type": "text", "text": text}],
                },
            ],
        },
    }


def parse(
    records: tuple[object, ...],
    *,
    roots: tuple[str, ...] = (KNOWLEDGE_ROOT,),
) -> ParsedTranscript:
    """Normalize one deterministic MCP transcript."""
    return normalize_transcript(
        jsonl(*records),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
        knowledge_roots=roots,
    )


def test_only_explicit_whitelisted_tool_names_have_an_adapter() -> None:
    """The whitelist is exact: no fuzzy `knowledge` substring matching."""
    assert MCP_KNOWLEDGE_TOOL_NAMES == (
        "mcp__knowledge__search",
        "mcp__knowledge__retrieve",
        "mcp__knowledge-base__search",
        "mcp__knowledge_base__search",
        "mcp__kb__search",
        "mcp__kb__retrieve",
    )
    for name in MCP_KNOWLEDGE_TOOL_NAMES:
        assert isinstance(knowledge_adapter_for(name), McpKnowledgeAdapter)
    for rejected in (
        "mcp__knowledge__list",
        "mcp__knowledge__fetch",
        "knowledge__search",
        "mcp__knowledge-search",
        "mcp__kb-search__query",
        "mcp__github__search",
        "Read",
        None,
    ):
        assert knowledge_adapter_for(rejected) is None


def test_search_and_retrieve_adapters_keep_distinct_retrieval_kinds() -> None:
    """Search and retrieve stay distinguishable in stored evidence."""
    search = knowledge_adapter_for("mcp__knowledge__search")
    retrieve = knowledge_adapter_for("mcp__kb__retrieve")

    assert search is not None
    assert retrieve is not None
    assert search.retrieval_kind == "mcp_search"
    assert retrieve.retrieval_kind == "mcp_retrieve"
    assert search.default_scope == "mcp_search"
    assert retrieve.default_scope == "mcp_retrieve"


def test_adapter_parses_single_object_envelopes_and_aliases() -> None:
    """One JSON object, a documents envelope, and every accepted alias parse."""
    adapter = knowledge_adapter_for("mcp__knowledge__search")
    assert adapter is not None

    single = adapter.parse(
        json.dumps(
            {
                "documentId": "doc-single",
                "sourcePath": "/knowledge/single.md",
                "version": "v3",
                "name": "Single",
                "collectionId": "handbook",
            },
        ),
    )
    envelope = adapter.parse(
        json.dumps(
            {
                "documents": [
                    {
                        "id": "doc-a",
                        "path": "/knowledge/a.md",
                        "contentHash": "abc123",
                        "title": "A",
                        "collection": "handbook",
                    },
                    {
                        "document_id": "doc-b",
                        "source_path": "/knowledge/b.md",
                        "digest": "def456",
                    },
                ],
            },
        ),
    )
    results = adapter.parse(json.dumps({"results": [{"id": "doc-r"}]}))
    items = adapter.parse(json.dumps({"items": [{"id": "doc-i"}]}))

    assert [document.document_id for document in single] == ["doc-single"]
    assert single[0].source_path == "/knowledge/single.md"
    assert single[0].revision == "v3"
    assert single[0].title == "Single"
    assert single[0].collection == "handbook"
    assert [document.document_id for document in envelope] == ["doc-a", "doc-b"]
    assert envelope[0].revision == "abc123"
    assert envelope[1].revision == "def456"
    assert [document.document_id for document in results] == ["doc-r"]
    assert [document.document_id for document in items] == ["doc-i"]


def test_adapter_parses_ndjson_and_ignores_bodies() -> None:
    """NDJSON documents are accepted while provider body text is never retained."""
    adapter = knowledge_adapter_for("mcp__kb__search")
    assert adapter is not None

    documents = adapter.parse(
        "\n".join(
            [
                json.dumps({"id": "doc-1", "path": "/knowledge/1.md", "content": "SECRET BODY"}),
                json.dumps({"id": "doc-2", "path": "/knowledge/2.md", "text": "SECRET BODY"}),
            ],
        ),
    )

    assert [document.document_id for document in documents] == ["doc-1", "doc-2"]
    rendered = repr(documents)
    assert "SECRET BODY" not in rendered
    assert all(not hasattr(document, "content") for document in documents)


def test_adapter_returns_empty_for_bad_or_empty_payloads() -> None:
    """Broken JSON, unknown shapes, and empty results never raise."""
    adapter = knowledge_adapter_for("mcp__knowledge__search")
    assert adapter is not None

    assert adapter.parse("not json at all") == ()
    assert adapter.parse("") == ()
    assert adapter.parse("{}") == ()
    assert adapter.parse("[]") == ()
    assert adapter.parse(json.dumps({"documents": "not-a-list"})) == ()
    assert adapter.parse("\n".join(['{"id": "ok"}', "broken"])) == ()
    assert adapter.parse(json.dumps({"documents": [{"title": "no identity"}]})) == ()


def test_adapter_bounds_and_stably_sorts_documents() -> None:
    """At most 100 documents are kept, deduplicated by identity, in stable order."""
    adapter = knowledge_adapter_for("mcp__kb__retrieve")
    assert adapter is not None
    payload = {
        "documents": [
            {"id": "doc-b", "path": "/knowledge/b.md", "revision": "2"},
            {"id": "doc-a", "path": "/knowledge/a.md", "revision": "1"},
            {"id": "doc-b", "path": "/knowledge/b.md", "revision": "2"},
        ],
    }
    documents = adapter.parse(json.dumps(payload))
    many = adapter.parse(
        json.dumps({"documents": [{"id": f"doc-{index:03d}"} for index in range(150)]}),
    )

    assert [(document.document_id, document.revision) for document in documents] == [
        ("doc-a", "1"),
        ("doc-b", "2"),
    ]
    assert len(many) == 100
    assert [document.document_id for document in many] == [
        f"doc-{index:03d}" for index in range(100)
    ]


def test_mcp_documents_emit_one_event_each_with_the_call_coordinates() -> None:
    """Every returned document becomes its own knowledge event."""
    text = json.dumps(
        {
            "documents": [
                {
                    "id": "doc-runbook",
                    "path": "/knowledge/runbook.md",
                    "revision": "r7",
                    "title": "Runbook",
                    "collection": "handbook",
                },
            ],
        },
    )
    parsed = parse(
        (
            user(),
            mcp_call(
                "tool-search",
                "mcp__knowledge__search",
                timestamp="2026-11-16T01:04:00Z",
            ),
            mcp_result("tool-search", text, timestamp="2026-11-16T01:08:00Z"),
        ),
    )

    assert len(parsed.events) == 1
    event = parsed.events[0]
    assert event.kind == "knowledge"
    assert event.name == "Runbook"
    assert event.document_id == "doc-runbook"
    assert event.document_revision == "r7"
    assert event.object_revision == "provider:r7"
    assert event.source_path == "/knowledge/runbook.md"
    assert event.retrieval_kind == "mcp_search"
    assert event.retrieval_scope == "handbook"
    assert event.tool_use_id == "tool-search"
    assert event.line_no == 2
    assert event.message_offset == 0
    assert event.triggered_at is not None
    assert event.triggered_at.hour == 9
    assert event.triggered_at.minute == 4


def test_mcp_documents_without_a_collection_use_the_adapter_scope() -> None:
    """A provider that names no collection keeps the adapter default scope."""
    parsed = parse(
        (
            user(),
            mcp_call("tool-retrieve", "mcp__kb__retrieve"),
            mcp_result("tool-retrieve", json.dumps({"documents": [{"id": "doc-1"}]})),
        ),
    )

    assert parsed.events[0].retrieval_kind == "mcp_retrieve"
    assert parsed.events[0].retrieval_scope == "mcp_retrieve"
    assert parsed.events[0].source_path is None
    assert parsed.events[0].name == "doc-1"


def test_non_whitelisted_mcp_tools_and_errored_results_emit_nothing() -> None:
    """A lookalike tool or an error result produces no document evidence."""
    payload = json.dumps({"documents": [{"id": "doc-1"}]})
    lookalike = parse(
        (
            user(),
            mcp_call("tool-other", "mcp__knowledge-search__query"),
            mcp_result("tool-other", payload),
        ),
    )
    errored = parse(
        (
            user(),
            mcp_call("tool-error", "mcp__knowledge__search"),
            mcp_result("tool-error", payload, is_error=True),
        ),
    )

    assert lookalike.events == ()
    assert errored.events == ()


def test_bad_mcp_json_emits_no_event_and_no_issue_noise() -> None:
    """Unparseable provider text is silently ignored, never raised."""
    parsed = parse(
        (
            user(),
            mcp_call("tool-broken", "mcp__knowledge__search"),
            mcp_result("tool-broken", "provider exploded"),
        ),
    )

    assert parsed.events == ()
    assert all(issue.code != "INVALID_JSONL_LINE" for issue in parsed.issues)


def test_multiple_documents_keep_a_stable_order_across_out_of_order_results() -> None:
    """Documents are ordered by their call line, then by identity."""
    first_payload = json.dumps(
        {
            "documents": [
                {"id": "doc-z", "path": "/knowledge/z.md"},
                {"id": "doc-a", "path": "/knowledge/a.md"},
            ],
        },
    )
    second_payload = json.dumps({"documents": [{"id": "doc-m", "path": "/knowledge/m.md"}]})
    parsed = parse(
        (
            user(),
            mcp_call("tool-first", "mcp__knowledge__search"),
            mcp_call("tool-second", "mcp__knowledge__search"),
            mcp_result("tool-second", second_payload),
            mcp_result("tool-first", first_payload),
        ),
    )

    assert [(event.line_no, event.document_id) for event in parsed.events] == [
        (2, "doc-a"),
        (2, "doc-z"),
        (3, "doc-m"),
    ]
    assert [event.event_index for event in parsed.events] == [0, 1, 2]


def test_provider_revision_and_object_revision_use_distinct_vocabularies() -> None:
    """documentRevision keeps the provider value; objectRevision is prefixed."""
    parsed = parse(
        (
            user(),
            mcp_call("tool-search", "mcp__knowledge__search"),
            mcp_result(
                "tool-search",
                json.dumps({"documents": [{"id": "doc-a", "revision": "2026.11"}]}),
            ),
            mcp_call("tool-unknown", "mcp__kb__search"),
            mcp_result("tool-unknown", json.dumps({"documents": [{"id": "doc-b"}]})),
        ),
    )

    by_id = {event.document_id: event for event in parsed.events}
    assert by_id["doc-a"].document_revision == "2026.11"
    assert by_id["doc-a"].object_revision == "provider:2026.11"
    assert by_id["doc-b"].document_revision == "unknown"
    assert by_id["doc-b"].object_revision == "unknown"


def test_prefixed_provider_revisions_keep_their_own_vocabulary() -> None:
    """A provider that already returns tag:/digest:/provider: is not double-wrapped."""
    parsed = parse(
        (
            user(),
            mcp_call("tool-search", "mcp__knowledge__search"),
            mcp_result(
                "tool-search",
                json.dumps(
                    {
                        "documents": [
                            {"id": "doc-digest", "revision": "digest:abc123"},
                            {"id": "doc-tag", "revision": "tag:v9"},
                            {"id": "doc-provider", "revision": "provider:raw"},
                        ],
                    },
                ),
            ),
        ),
    )

    by_id = {event.document_id: event for event in parsed.events}
    assert by_id["doc-digest"].object_revision == "digest:abc123"
    assert by_id["doc-tag"].object_revision == "tag:v9"
    assert by_id["doc-provider"].object_revision == "provider:raw"
    assert by_id["doc-digest"].document_revision == "digest:abc123"


def test_multiple_documents_from_one_call_are_not_ambiguous_tool_uses() -> None:
    """One retrieval call owning several document events stays free of issues."""
    payload = json.dumps(
        {"documents": [{"id": "doc-a", "path": "/knowledge/a.md"}, {"id": "doc-b"}]},
    )
    parsed = parse(
        (
            user(),
            mcp_call("tool-search", "mcp__knowledge__search"),
            mcp_result("tool-search", payload),
        ),
    )

    assembled = assemble_agent_trees((parsed,))

    assert [event.document_id for event in assembled.trees[0].nodes[0].events] == [
        "doc-a",
        "doc-b",
    ]
    assert all(issue.code != "DUPLICATE_TOOL_USE_ID" for issue in assembled.issues)
