"""Pure Agent tree assembly contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.fixture_corpus import load_fixture_corpus
from app.service.acquisition.agent_tree import (
    AgentTreeAggregate,
    AssembledAgentNode,
    AssembledSessionTree,
    assemble_agent_trees,
)
from app.service.acquisition.normalize import (
    ParsedTranscript,
    normalize_transcript,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CORPUS_PATH = REPOSITORY_ROOT / "fixtures" / "m2-synthetic" / "corpus.json"
ROOT_ID = "11111111-1111-4111-8111-111111111111"


def jsonl(*records: object | str) -> str:
    """Encode deterministic JSONL test input."""
    return (
        "\n".join(
            record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
            for record in records
        )
        + "\n"
    )


def user(text: str, *, timestamp: str = "2026-10-20T01:00:00Z") -> dict[str, object]:
    """Build one root user record."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {"content": text},
    }


def assistant(
    message_id: str,
    tools: tuple[tuple[str, str], ...] = (),
    *,
    is_error: bool = False,
    model: str = "model-main",
    timestamp: str = "2026-10-20T01:01:00Z",
    cwd: str | None = None,
) -> dict[str, object]:
    """Build one assistant record with optional tool-use blocks."""
    content: list[dict[str, object]] = [{"type": "text", "text": "PRIVATE_ASSISTANT_TEXT"}]
    for tool_id, name in tools:
        content.append(
            {
                "type": "tool_use",
                "id": tool_id,
                "name": name,
                "input": {
                    "subagent_type": "Explore",
                    "skill": "review",
                    "name": "flow",
                    "description": "PRIVATE_DESCRIPTION",
                },
            },
        )
    if is_error:
        content.append({"type": "text", "text": "PRIVATE_ERROR_TEXT", "is_error": True})
    record: dict[str, object] = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": model,
            "content": content,
            "usage": {"input_tokens": 5, "output_tokens": 3},
        },
    }
    if cwd is not None:
        record["cwd"] = cwd
    return record


def api_error(
    message_id: str,
    *,
    timestamp: str = "2026-10-20T01:01:00Z",
) -> dict[str, object]:
    """Build one provider API-error assistant record."""
    return {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "isApiErrorMessage": True,
        "error": "PRIVATE_API_ERROR",
        "message": {
            "id": message_id,
            "model": "model-main",
            "content": [],
        },
    }


def parse(
    *records: object | str,
    agent_id: str,
    kind: str = "subagent",
    meta: dict[str, object] | None = None,
) -> ParsedTranscript:
    """Normalize one test transcript."""
    return normalize_transcript(
        jsonl(*records),
        root_session_id=ROOT_ID,
        agent_id=agent_id,
        agent_kind="main" if kind == "main" else "subagent",
        agent_meta=meta,
    )


def full_tree_transcripts() -> tuple[ParsedTranscript, ...]:
    """Build nested Agent, workflow, fork, teammate, and ordinary-skill cases."""
    main = parse(
        user("PRIVATE_PROMPT"),
        assistant(
            "main-message",
            (
                ("agent-a", "Agent"),
                ("skill-1", "Skill"),
                ("workflow-1", "Workflow"),
            ),
        ),
        agent_id=ROOT_ID,
        kind="main",
        meta={"model": "requested-main", "description": "PRIVATE_DESCRIPTION"},
    )
    agent_a = parse(
        assistant("agent-a-message", (("agent-b", "Agent"),), model="model-child"),
        agent_id="agent-a",
        meta={
            "agentType": "Explore",
            "description": "PRIVATE_DESCRIPTION",
            "toolUseId": "agent-a",
            "spawnDepth": 1,
        },
    )
    agent_b = parse(
        assistant("agent-b-message", model="model-grandchild"),
        agent_id="agent-b",
        meta={
            "agentType": "Explore",
            "description": "PRIVATE_DESCRIPTION",
            "toolUseId": "agent-b",
            "spawnDepth": 2,
        },
    )
    fork = parse(
        assistant("fork-message", is_error=True, model="model-fork"),
        agent_id="agent-fork",
        meta={
            "description": "PRIVATE_DESCRIPTION",
            "skillName": "review",
            "taskKind": "forked_skill",
            "spawnDepth": 1,
        },
    )
    teammate = parse(
        assistant("teammate-message", model="model-teammate"),
        agent_id="agent-teammate",
        meta={
            "agentType": "Explore",
            "description": "PRIVATE_DESCRIPTION",
            "spawnDepth": 1,
            "taskKind": "in_process_teammate",
            "teamName": "review-team",
        },
    )
    worker = parse(
        assistant("worker-message", model="model-worker"),
        agent_id="agent-worker",
        meta={
            "agentType": "workflow-subagent",
            "description": "PRIVATE_DESCRIPTION",
            "spawnDepth": 2,
        },
    )
    return main, agent_a, agent_b, fork, teammate, worker


def test_assembles_nested_workflow_fork_and_teammate_tree() -> None:
    """Every supported node type has a canonical parent and computed depth."""
    result = assemble_agent_trees(full_tree_transcripts())

    assert len(result.trees) == 1
    tree = result.trees[0]
    by_id = {node.id: node for node in tree.nodes}
    main = by_id[ROOT_ID]
    workflow = next(node for node in tree.nodes if node.kind == "workflow")

    assert main.parent_agent_id is None
    assert main.spawn_depth == 0
    assert by_id["agent-a"].parent_agent_id == ROOT_ID
    assert by_id["agent-a"].spawn_depth == 1
    assert by_id["agent-b"].parent_agent_id == "agent-a"
    assert by_id["agent-b"].spawn_depth == 2
    assert by_id["agent-fork"].parent_agent_id == ROOT_ID
    assert by_id["agent-fork"].agent_type is None
    assert by_id["agent-fork"].skill_name == "review"
    assert by_id["agent-teammate"].parent_agent_id == ROOT_ID
    assert by_id["agent-teammate"].team_name == "review-team"
    assert by_id["agent-worker"].parent_agent_id == workflow.id

    assert workflow.tool_use_id == "workflow-1"
    assert workflow.parent_agent_id == ROOT_ID
    assert workflow.lines == 0
    assert workflow.messages_count == 0
    assert workflow.tokens_total == 0
    assert workflow.tools_count == 0
    assert workflow.errors_count == 0
    assert len(workflow.id) <= 64
    assert not any(node.name == "Skill" for node in tree.nodes)

    assert tree.agents_count == 4
    assert tree.messages_count == sum(node.messages_count for node in tree.nodes)
    assert tree.tokens_total == sum(node.tokens_total for node in tree.nodes)
    assert tree.tools_count == sum(node.tools_count for node in tree.nodes)
    assert tree.errors_count == sum(node.errors_count for node in tree.nodes)
    assert tree.status == "partial"
    assert set(tree.models) == {
        "model-main",
        "model-child",
        "model-grandchild",
        "model-fork",
        "model-teammate",
        "model-worker",
    }
    assert tree.user_turns_count == 1
    assert tree.skill_names == ("review",)

    positions = {node.id: index for index, node in enumerate(tree.nodes)}
    assert positions[ROOT_ID] == 0
    for node in tree.nodes:
        if node.parent_agent_id is not None:
            assert positions[node.parent_agent_id] < positions[node.id]


def test_missing_or_unknown_parent_tool_use_id_degrades_to_main() -> None:
    """Nodes without a parent call remain reachable and produce stable warnings."""
    main = parse(
        assistant("root-message"),
        agent_id=ROOT_ID,
        kind="main",
    )
    missing = parse(
        assistant("missing-message"),
        agent_id="agent-missing",
        meta={"agentType": "Explore", "description": "PRIVATE_DESCRIPTION"},
    )
    unknown = parse(
        assistant("unknown-message"),
        agent_id="agent-unknown",
        meta={
            "agentType": "Explore",
            "description": "PRIVATE_DESCRIPTION",
            "toolUseId": "not-in-parent",
        },
    )

    result = assemble_agent_trees((main, missing, unknown))

    tree = result.trees[0]
    assert tree.parent_by_id()["agent-missing"] == ROOT_ID
    assert tree.parent_by_id()["agent-unknown"] == ROOT_ID
    main_node = next(node for node in tree.nodes if node.id == ROOT_ID)
    for agent_id in ("agent-missing", "agent-unknown"):
        child = next(node for node in tree.nodes if node.id == agent_id)
        matching = [
            event
            for event in main_node.events
            if event.kind == "agent" and event.tool_use_id == child.tool_use_id
        ]
        assert len(matching) == 1
        assert matching[0].message_offset == main_node.messages_count
        assert matching[0].line_no > 0
    assert [issue.code for issue in result.issues] == [
        "MISSING_PARENT_TOOL_USE_ID",
        "UNKNOWN_PARENT_TOOL_USE_ID",
    ]
    rendered = repr(result.issues)
    for secret in ("PRIVATE_PROMPT", "PRIVATE_DESCRIPTION", "PRIVATE_ASSISTANT_TEXT"):
        assert secret not in rendered


def test_duplicate_parent_tool_use_ids_do_not_create_ambiguous_edges() -> None:
    """Children never share an ambiguous parent call or synthetic anchor."""
    main = parse(
        assistant(
            "root-message",
            (
                ("duplicate-parent", "Agent"),
                ("duplicate-parent", "Agent"),
            ),
        ),
        agent_id=ROOT_ID,
        kind="main",
    )
    first = parse(
        assistant("first-message"),
        agent_id="agent-first",
        meta={"agentType": "Explore", "toolUseId": "duplicate-parent"},
    )
    second = parse(
        assistant("second-message"),
        agent_id="agent-second",
        meta={"agentType": "Explore", "toolUseId": "duplicate-parent"},
    )

    result = assemble_agent_trees((main, first, second))

    tree = result.trees[0]
    main_node = next(node for node in tree.nodes if node.id == ROOT_ID)
    children = [
        next(node for node in tree.nodes if node.id == agent_id)
        for agent_id in ("agent-first", "agent-second")
    ]
    assert all(child.parent_agent_id == ROOT_ID for child in children)
    assert len({child.tool_use_id for child in children}) == 2
    for child in children:
        assert child.tool_use_id is not None
        assert (
            sum(
                event.tool_use_id == child.tool_use_id and event.kind == "agent"
                for event in main_node.events
            )
            == 1
        )
    codes = [issue.code for issue in result.issues]
    assert codes.count("DUPLICATE_TOOL_USE_ID") == 1
    assert codes.count("AMBIGUOUS_PARENT_TOOL_USE_ID") == 2


def test_session_status_uses_final_assistant_and_fatal_error_rules() -> None:
    """Unanswered and unrecovered provider failures are fail, not ok."""
    unanswered = parse(
        user("FIRST_PRIVATE_PROMPT"),
        assistant("first-answer"),
        user("SECOND_PRIVATE_PROMPT", timestamp="2026-10-20T01:02:00Z"),
        agent_id=ROOT_ID,
        kind="main",
    )
    assert assemble_agent_trees((unanswered,)).trees[0].status == "fail"

    fatal = parse(
        user("PRIVATE_PROMPT"),
        assistant("answer"),
        api_error("fatal", timestamp="2026-10-20T01:02:00Z"),
        agent_id=ROOT_ID,
        kind="main",
    )
    assert assemble_agent_trees((fatal,)).trees[0].status == "fail"

    recovered = parse(
        user("PRIVATE_PROMPT"),
        api_error("transient"),
        assistant("answer", timestamp="2026-10-20T01:02:00Z"),
        agent_id=ROOT_ID,
        kind="main",
    )
    assert assemble_agent_trees((recovered,)).trees[0].status == "ok"


def test_rejects_missing_duplicate_main_and_parent_cycle() -> None:
    """Invalid roots are rejected instead of producing unreachable trees."""
    orphan = parse(assistant("orphan-message"), agent_id="agent-orphan")
    missing_main = assemble_agent_trees((orphan,))
    assert missing_main.trees == ()
    assert [issue.code for issue in missing_main.issues] == ["MISSING_MAIN_AGENT"]

    main = parse(assistant("root-message"), agent_id=ROOT_ID, kind="main")
    duplicate_main = replace(
        parse(assistant("duplicate-main"), agent_id="other-main", kind="main"),
        root_session_id=ROOT_ID,
    )
    duplicate = assemble_agent_trees((main, duplicate_main))
    assert duplicate.trees == ()
    assert [issue.code for issue in duplicate.issues] == ["DUPLICATE_MAIN_AGENT"]

    main_with_calls = parse(
        assistant(
            "root-message",
            (("agent-a-root", "Agent"), ("agent-b-root", "Agent")),
        ),
        agent_id=ROOT_ID,
        kind="main",
    )
    agent_a = parse(
        assistant("a-message", (("b-call", "Agent"),)),
        agent_id="agent-a",
        meta={"toolUseId": "b-call"},
    )
    agent_b = parse(
        assistant("b-message", (("a-call", "Agent"),)),
        agent_id="agent-b",
        meta={"toolUseId": "a-call"},
    )
    cycle = assemble_agent_trees((main_with_calls, agent_a, agent_b))
    assert cycle.trees == ()
    assert {issue.code for issue in cycle.issues} == {"PARENT_CYCLE"}


def test_ordering_is_deterministic_after_input_shuffle() -> None:
    """Canonical node ordering does not depend on provider or caller order."""
    transcripts = full_tree_transcripts()
    forward = assemble_agent_trees(transcripts)
    reverse = assemble_agent_trees(tuple(reversed(transcripts)))

    assert _tree_signature(forward) == _tree_signature(reverse)


def test_synthetic_corpus_assembles_all_documented_node_types() -> None:
    """Fixture payload truth and manifest tree structure stay reconciled."""
    corpus = load_fixture_corpus(CORPUS_PATH)
    transcripts = tuple(
        normalize_transcript(
            agent.payload.content,
            root_session_id=root.record.id,
            agent_id=agent.record.id,
            agent_kind=agent.record.kind,
            agent_meta=agent.record.meta,
        )
        for root in corpus.root_sessions
        for agent in root.agents
        if agent.record.kind != "workflow"
    )

    result = assemble_agent_trees(transcripts)
    workflow_manifest = next(
        agent.record
        for root in corpus.root_sessions
        for agent in root.agents
        if agent.record.kind == "workflow"
    )
    worker_manifest = next(
        agent.record
        for root in corpus.root_sessions
        for agent in root.agents
        if agent.record.agent_type == "workflow-subagent"
    )
    assembled_workflow = next(
        node for tree in result.trees for node in tree.nodes if node.kind == "workflow"
    )
    assembled_worker = next(
        node for tree in result.trees for node in tree.nodes if node.id == worker_manifest.id
    )

    assert result.aggregate == AgentTreeAggregate(
        root_sessions=4,
        nodes=8,
        agents=3,
        subagents=3,
        teammates=0,
        backtracked_subagents=3,
        workflow_nodes=1,
        forked_skill_nodes=1,
        roots_with_complete_parents=4,
        warning_count=0,
        warning_codes=(),
    )
    assert all(
        node.parent_agent_id is not None
        for tree in result.trees
        for node in tree.nodes
        if node.kind != "main"
    )
    assert sum(node.kind == "workflow" for tree in result.trees for node in tree.nodes) == 1
    assert (
        sum(node.task_kind == "forked_skill" for tree in result.trees for node in tree.nodes) == 1
    )
    assert assembled_workflow.id == workflow_manifest.id
    assert assembled_workflow.parent_agent_id == workflow_manifest.parent_agent_id
    assert assembled_workflow.tool_use_id == workflow_manifest.tool_use_id
    assert assembled_worker.parent_agent_id == worker_manifest.parent_agent_id
    assert assembled_worker.parent_agent_id == assembled_workflow.id
    assert [tree.status for tree in result.trees] == ["ok", "ok", "partial", "ok"]


def _tree_signature(
    result: object,
) -> tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]:
    """Return deterministic tree node and warning signatures."""
    trees = tuple(
        tuple(node.id for node in tree.nodes)
        for tree in result.trees  # type: ignore[attr-defined]
    )
    issues = tuple(issue.code for issue in result.issues)  # type: ignore[attr-defined]
    return trees, issues


@pytest.mark.parametrize(
    "bad_transcripts",
    [
        (),
        (
            replace(
                parse(assistant("x"), agent_id=ROOT_ID, kind="main"),
                root_session_id="",
            ),
        ),
    ],
)
def test_empty_or_empty_root_input_has_no_tree(
    bad_transcripts: tuple[ParsedTranscript, ...],
) -> None:
    """An empty aggregate is explicit rather than an implicit success."""
    result = assemble_agent_trees(bad_transcripts)
    assert isinstance(result.aggregate, AgentTreeAggregate)
    assert result.aggregate.root_sessions == 0
    assert result.trees == ()


def test_public_node_contract_has_no_message_content_fields() -> None:
    """Persistable tree nodes expose structural fields only."""
    result = assemble_agent_trees(full_tree_transcripts())
    node = result.trees[0].nodes[0]
    assert isinstance(node, AssembledAgentNode)
    assert not hasattr(node, "content")
    assert not hasattr(node, "prompt_text")
    assert isinstance(result.trees[0], AssembledSessionTree)


def test_preserves_provider_depth_adds_missing_edge_and_complete_title() -> None:
    """Provider metadata and persistence fields survive tree canonicalization."""
    long_prompt = "PRIVATE_PROMPT " + ("X" * 300)
    main = parse(
        user(long_prompt, timestamp="2026-10-20T01:00:00Z"),
        assistant("main-message", cwd="/private/project/PrivateRepo"),
        agent_id=ROOT_ID,
        kind="main",
    )
    child = parse(
        assistant(
            "child-message",
            timestamp="2026-10-20T02:00:00Z",
        ),
        agent_id="agent-child",
        meta={
            "agentType": "Explore",
            "description": "META_DESCRIPTION",
            "spawnDepth": 7,
        },
    )

    result = assemble_agent_trees((main, child))

    tree = result.trees[0]
    main_node = next(node for node in tree.nodes if node.kind == "main")
    child_node = next(node for node in tree.nodes if node.id == "agent-child")
    assert child_node.spawn_depth == 7
    assert child_node.parent_agent_id == ROOT_ID
    assert len(main_node.events) == 1
    assert main_node.events[0].kind == "agent"
    assert main_node.events[0].tool_use_id is not None
    assert tree.started_at is not None
    assert tree.ended_at is not None
    assert tree.started_at.year == 2026
    assert tree.ended_at.hour == 10
    assert tree.title.endswith("X" * 300)
    assert len(tree.title) > len(tree.short_title) == 120
    assert tree.search_text == tree.search_text.lower()
    assert "PRIVATE_PROMPT" not in tree.search_text
    assert "privaterepo" in tree.search_text
    assert "/private/project" not in tree.search_text


def test_trigger_metadata_controls_node_name_and_description() -> None:
    """Subagent and forked skill fields come from their trigger events."""
    main = parse(
        user("PRIVATE_PROMPT", timestamp="2026-10-20T01:00:00Z"),
        assistant(
            "main-message",
            (
                ("skill-parent", "Skill"),
                ("agent-parent", "Agent"),
            ),
        ),
        agent_id=ROOT_ID,
        kind="main",
    )
    fork = parse(
        assistant("fork-message"),
        agent_id="agent-fork",
        meta={
            "name": "META_NAME",
            "description": "META_DESCRIPTION",
            "skillName": "skill",
            "taskKind": "forked_skill",
            "toolUseId": "skill-parent",
        },
    )
    agent = parse(
        assistant("agent-message"),
        agent_id="agent-child",
        meta={
            "name": "META_NAME",
            "description": "META_DESCRIPTION",
            "agentType": "Explore",
            "toolUseId": "agent-parent",
        },
    )

    tree = assemble_agent_trees((main, fork, agent)).trees[0]
    nodes = {node.id: node for node in tree.nodes}

    assert nodes["agent-fork"].name is None
    assert nodes["agent-fork"].description == "PRIVATE_DESCRIPTION"
    assert nodes["agent-child"].description == "PRIVATE_DESCRIPTION"


def test_assistant_only_session_has_persistable_bounds_and_rejects_no_time() -> None:
    """Session bounds include assistant records and never emit NULL dates."""
    main = parse(
        assistant("main-message", timestamp="2026-10-20T03:00:00Z"),
        agent_id=ROOT_ID,
        kind="main",
    )

    tree = assemble_agent_trees((main,)).trees[0]

    assert tree.started_at is not None
    assert tree.ended_at is not None
    assert tree.started_at.hour == 11
    assert tree.ended_at.hour == 11

    without_time = dict(assistant("untimed-message"))
    without_time.pop("timestamp")
    untimed = parse(
        without_time,
        agent_id=ROOT_ID,
        kind="main",
    )
    rejected = assemble_agent_trees((untimed,))
    assert rejected.trees == ()
    assert [issue.code for issue in rejected.issues] == ["MISSING_SESSION_TIMESTAMP"]
