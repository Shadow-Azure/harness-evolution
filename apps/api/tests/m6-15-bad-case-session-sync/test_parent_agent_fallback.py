"""Parent-agent fallback for trajectories that have no tool-use metadata."""

from __future__ import annotations

import json

from app.service.acquisition.agent_tree import assemble_agent_trees
from app.service.acquisition.normalize import ParsedTranscript, normalize_transcript

ROOT = "root-session"
MAIN = "root-session"
CHILD = "agent-a"
GRANDCHILD = "agent-b"


def _jsonl(*records: object) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records)


def _assistant(
    message_id: str, content: list[dict[str, object]] | None = None
) -> dict[str, object]:
    return {
        "type": "assistant",
        "timestamp": "2026-10-30T10:00:00+08:00",
        "message": {"id": message_id, "model": "model", "content": content or []},
    }


def _user(prompt: str) -> dict[str, object]:
    return {
        "type": "user",
        "timestamp": "2026-10-30T09:59:00+08:00",
        "message": {"content": prompt},
    }


def _parse(
    records: tuple[object, ...],
    *,
    agent_id: str,
    kind: str,
    meta: dict[str, object] | None = None,
) -> ParsedTranscript:
    return normalize_transcript(
        _jsonl(*records),
        root_session_id=ROOT,
        agent_id=agent_id,
        agent_kind="main" if kind == "main" else "subagent",
        agent_meta=meta,
    )


def test_normalize_reads_parent_agent_id_and_accepts_both_tool_keys() -> None:
    parsed = _parse(
        (_assistant("one"),),
        agent_id=CHILD,
        kind="subagent",
        meta={"parentAgentId": CHILD, "parentToolUseId": "tool-parent"},
    )
    assert parsed.parent_agent_id == CHILD
    assert parsed.parent_tool_use_id == "tool-parent"

    preferred = _parse(
        (_assistant("two"),),
        agent_id=CHILD,
        kind="subagent",
        meta={"toolUseId": "tool-preferred", "parentToolUseId": "tool-fallback"},
    )
    assert preferred.parent_tool_use_id == "tool-preferred"


def test_tree_anchors_missing_tool_edge_to_parent_agent() -> None:
    main = _parse(
        (
            _user("prompt"),
            _assistant(
                "main-message",
                [
                    {
                        "type": "tool_use",
                        "id": "tool-a",
                        "name": "Agent",
                        "input": {"description": "child"},
                    },
                ],
            ),
        ),
        agent_id=MAIN,
        kind="main",
    )
    child = _parse(
        (_assistant("child-message"),),
        agent_id=CHILD,
        kind="subagent",
        meta={"toolUseId": "tool-a", "agentType": "Explore"},
    )
    grandchild = _parse(
        (_assistant("grandchild-message"),),
        agent_id=GRANDCHILD,
        kind="subagent",
        meta={"parentAgentId": CHILD},
    )

    result = assemble_agent_trees((main, child, grandchild))
    tree = result.trees[0]
    by_id = {node.id: node for node in tree.nodes}
    assert by_id[CHILD].parent_agent_id == MAIN
    assert by_id[GRANDCHILD].parent_agent_id == CHILD
    assert not [
        issue
        for issue in result.issues
        if issue.agent_id == GRANDCHILD and issue.code == "MISSING_PARENT_TOOL_USE_ID"
    ]
