"""Pure Agent session tree assembly from normalized transcripts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import PurePath
from typing import Literal

from app.service.acquisition.normalize import (
    ParsedEvent,
    ParsedIssue,
    ParsedTranscript,
    ParsedUserTurn,
    RootMetadata,
)

AgentKind = Literal["main", "subagent", "workflow"]
SessionStatus = Literal["ok", "partial", "fail"]


@dataclass(frozen=True, slots=True)
class AssembledAgentNode:
    """One persistable Agent node without message or content-block detail."""

    id: str
    root_session_id: str
    parent_agent_id: str | None
    kind: AgentKind
    agent_type: str | None
    task_kind: str | None
    team_name: str | None
    name: str | None
    skill_name: str | None
    model: str | None
    requested_model: str | None
    description: str | None
    tool_use_id: str | None
    spawn_depth: int
    lines: int
    messages_count: int
    tokens_total: int
    tools_count: int
    errors_count: int
    sort_key: float
    events: tuple[ParsedEvent, ...]
    user_turns: tuple[ParsedUserTurn, ...]
    agent_meta: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AssembledSessionTree:
    """A flat, canonically ordered Agent tree plus session aggregates."""

    id: str
    short_title: str
    title: str
    search_text: str
    repo_name: str
    root_metadata: RootMetadata
    model: str | None
    models: tuple[str, ...]
    skill_names: tuple[str, ...]
    status: SessionStatus
    user_turns_count: int
    messages_count: int
    tools_count: int
    errors_count: int
    agents_count: int
    tokens_total: int
    started_at: datetime | None
    ended_at: datetime | None
    nodes: tuple[AssembledAgentNode, ...]
    user_turns: tuple[ParsedUserTurn, ...]

    def parent_by_id(self) -> dict[str, str | None]:
        """Return the canonical parent lookup for structural verification."""
        return {node.id: node.parent_agent_id for node in self.nodes}


@dataclass(frozen=True, slots=True)
class AgentTreeAggregate:
    """Privacy-safe aggregate emitted by local tree verification."""

    root_sessions: int
    nodes: int
    agents: int
    subagents: int
    teammates: int
    backtracked_subagents: int
    workflow_nodes: int
    forked_skill_nodes: int
    roots_with_complete_parents: int
    warning_count: int
    warning_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentTreeAssemblyResult:
    """All successfully assembled roots plus stable structural issues."""

    trees: tuple[AssembledSessionTree, ...]
    issues: tuple[ParsedIssue, ...]
    aggregate: AgentTreeAggregate


@dataclass(frozen=True, slots=True)
class _PendingNode:
    """Mutable-in-construction node identity before canonical ordering."""

    node: AssembledAgentNode
    event_anchor: tuple[int, int, str]


def _issue(
    session_id: str,
    agent_id: str,
    line_no: int,
    code: str,
    message: str,
) -> ParsedIssue:
    """Create one stable, transcript-free structural warning."""
    return ParsedIssue(
        session_id=session_id,
        agent_id=agent_id,
        line_no=line_no,
        code=code,
        message=message,
    )


def _meta_string(meta: Mapping[str, object], key: str) -> str | None:
    """Read an optional string from frozen provider metadata."""
    value = meta.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _workflow_id(root_session_id: str, tool_use_id: str) -> str:
    """Create a stable cross-root workflow node identity."""
    digest = hashlib.sha256(f"{root_session_id}\0{tool_use_id}".encode()).hexdigest()
    return f"wf_{digest[:32]}"


def _event_anchor(event: ParsedEvent) -> tuple[int, int, str]:
    """Use provider source position as the first sibling-order key."""
    return (event.line_no, event.event_index, event.tool_use_id or "")


def _transcript_node(transcript: ParsedTranscript) -> AssembledAgentNode:
    """Project one normalized transcript into a parentless node candidate."""
    return AssembledAgentNode(
        id=transcript.agent_id,
        root_session_id=transcript.root_session_id,
        parent_agent_id=None,
        kind="main" if transcript.agent_kind == "main" else "subagent",
        agent_type=transcript.agent_type,
        task_kind=transcript.task_kind,
        team_name=transcript.team_name,
        name=transcript.name,
        skill_name=transcript.skill_name,
        model=transcript.model,
        requested_model=transcript.requested_model,
        description=_meta_string(transcript.agent_meta, "description"),
        tool_use_id=transcript.parent_tool_use_id,
        spawn_depth=transcript.spawn_depth,
        lines=transcript.lines,
        messages_count=transcript.messages_count,
        tokens_total=transcript.tokens_total,
        tools_count=transcript.tools_count,
        errors_count=transcript.errors_count,
        sort_key=0.0,
        events=transcript.events,
        user_turns=transcript.user_turns,
        agent_meta=transcript.agent_meta,
    )


def _workflow_node(
    root_session_id: str,
    owner_id: str,
    event: ParsedEvent,
    spawn_depth: int,
) -> AssembledAgentNode:
    """Create a zero-statistics Workflow node from its parent trigger."""
    if event.tool_use_id is None:
        raise ValueError("workflow event is missing a tool-use identity")
    return AssembledAgentNode(
        id=_workflow_id(root_session_id, event.tool_use_id),
        root_session_id=root_session_id,
        parent_agent_id=owner_id,
        kind="workflow",
        agent_type="workflow",
        task_kind=None,
        team_name=None,
        name=event.name,
        skill_name=None,
        model=None,
        requested_model=None,
        description=event.description,
        tool_use_id=event.tool_use_id,
        spawn_depth=spawn_depth,
        lines=0,
        messages_count=0,
        tokens_total=0,
        tools_count=0,
        errors_count=0,
        sort_key=0.0,
        events=(),
        user_turns=(),
        agent_meta={},
    )


def _cycle_nodes(
    nodes: dict[str, AssembledAgentNode],
    main_id: str,
) -> set[str]:
    """Return every node participating in a parent cycle."""
    cycle_nodes: set[str] = set()
    for node_id in nodes:
        seen: set[str] = set()
        current: str | None = node_id
        while current is not None and current != main_id:
            if current in seen:
                cycle_nodes.add(current)
                break
            seen.add(current)
            current = nodes.get(current, nodes[main_id]).parent_agent_id
    return cycle_nodes


def _depths(nodes: dict[str, AssembledAgentNode], main_id: str) -> dict[str, int]:
    """Compute canonical depth by walking canonical parent links."""
    depths: dict[str, int] = {}
    for node_id in nodes:
        depth = 0
        current = node_id
        seen: set[str] = set()
        while current != main_id:
            if current in seen:
                raise ValueError("parent cycle")
            seen.add(current)
            parent = nodes[current].parent_agent_id
            if parent is None or parent not in nodes:
                raise ValueError("unreachable parent")
            current = parent
            depth += 1
        depths[node_id] = depth
    return depths


def _canonical_order(
    nodes: dict[str, AssembledAgentNode],
    anchors: dict[str, tuple[int, int, str]],
    depths: dict[str, int],
    main_id: str,
) -> tuple[AssembledAgentNode, ...]:
    """Order parents before children, then by source position and stable id."""
    ordered = sorted(
        nodes.values(),
        key=lambda node: (
            depths[node.id],
            0 if node.id == main_id else 1,
            anchors.get(node.id, (10**9, 10**9, node.id)),
            node.id,
        ),
    )
    return tuple(replace(node, sort_key=float(index)) for index, node in enumerate(ordered))


def _synthetic_tool_use_id(root_session_id: str, agent_id: str) -> str:
    """Create a deterministic parent-call identity for a recovered edge."""
    digest = hashlib.sha256(f"{root_session_id}\0{agent_id}".encode()).hexdigest()[:16]
    return f"synthetic-agent-{digest}"


def _synthetic_agent_event(
    *,
    root_session_id: str,
    agent_id: str,
    event_index: int,
    message_offset: int,
    line_no: int,
) -> ParsedEvent:
    """Create the deterministic edge anchor for a missing parent trigger."""
    return ParsedEvent(
        event_index=event_index,
        line_no=line_no,
        message_offset=message_offset,
        kind="agent",
        name="synthetic-agent",
        description=None,
        tool_use_id=_synthetic_tool_use_id(root_session_id, agent_id),
    )


def _session_status(
    main: AssembledAgentNode,
    main_transcript: ParsedTranscript,
    nodes: tuple[AssembledAgentNode, ...],
    transcripts: tuple[ParsedTranscript, ...],
) -> SessionStatus:
    """Apply the documented whole-tree status precedence."""
    if (
        main.messages_count == 0
        or not main_transcript.ended_with_assistant
        or any(transcript.fatal_error_unrecovered for transcript in transcripts)
    ):
        return "fail"
    if any(node.errors_count > 0 for node in nodes):
        return "partial"
    return "ok"


def _assemble_root(
    root_session_id: str,
    transcripts: tuple[ParsedTranscript, ...],
) -> tuple[AssembledSessionTree | None, tuple[ParsedIssue, ...]]:
    """Assemble one root, returning no tree if its structural identity is invalid."""
    issues: list[ParsedIssue] = list(
        issue for transcript in transcripts for issue in transcript.issues
    )
    mains = [transcript for transcript in transcripts if transcript.agent_kind == "main"]
    if not mains:
        return None, (
            _issue(
                root_session_id,
                root_session_id,
                0,
                "MISSING_MAIN_AGENT",
                "Root session has no main Agent transcript",
            ),
        )
    if len(mains) != 1:
        return None, (
            _issue(
                root_session_id,
                mains[0].agent_id,
                0,
                "DUPLICATE_MAIN_AGENT",
                "Root session has multiple main Agent transcripts",
            ),
        )

    main_transcript = mains[0]
    main_id = main_transcript.agent_id
    by_agent = {transcript.agent_id: transcript for transcript in transcripts}
    if len(by_agent) != len(transcripts):
        return None, (
            _issue(
                root_session_id,
                main_id,
                0,
                "DUPLICATE_AGENT_ID",
                "Root session contains duplicate Agent identities",
            ),
        )

    nodes: dict[str, AssembledAgentNode] = {
        transcript.agent_id: _transcript_node(transcript) for transcript in transcripts
    }
    anchors: dict[str, tuple[int, int, str]] = {
        transcript.agent_id: (
            transcript.user_turns[0].line_no if transcript.user_turns else 0,
            0,
            transcript.agent_id,
        )
        for transcript in transcripts
    }

    tool_events: dict[str, tuple[str, ParsedEvent]] = {}
    ambiguous_tool_ids: set[str] = set()
    skill_events: dict[str, list[tuple[str, ParsedEvent]]] = {}
    workflow_events: dict[str, tuple[str, ParsedEvent]] = {}
    skill_name_events: dict[str, list[tuple[str, ParsedEvent]]] = {}
    for owner_id, node in tuple(nodes.items()):
        for event in node.events:
            if event.tool_use_id is None:
                continue
            if event.tool_use_id in tool_events:
                ambiguous_tool_ids.add(event.tool_use_id)
                issues.append(
                    _issue(
                        root_session_id,
                        owner_id,
                        event.line_no,
                        "DUPLICATE_TOOL_USE_ID",
                        "Tool use identity is not unique inside the root session",
                    ),
                )
            tool_events[event.tool_use_id] = (owner_id, event)
            if event.kind == "skill":
                skill_events.setdefault(event.tool_use_id, []).append((owner_id, event))
                if event.name is not None:
                    skill_name_events.setdefault(event.name, []).append((owner_id, event))
            elif event.kind == "workflow":
                workflow_events[event.tool_use_id] = (owner_id, event)
                workflow_node = _workflow_node(
                    root_session_id,
                    owner_id,
                    event,
                    nodes[owner_id].spawn_depth + 1,
                )
                if workflow_node.id in nodes:
                    issues.append(
                        _issue(
                            root_session_id,
                            owner_id,
                            event.line_no,
                            "DUPLICATE_WORKFLOW_ID",
                            "Workflow trigger maps to a duplicate synthetic identity",
                        ),
                    )
                    continue
                nodes[workflow_node.id] = workflow_node
                anchors[workflow_node.id] = _event_anchor(event)

    workflow_ids = tuple(sorted(node.id for node in nodes.values() if node.kind == "workflow"))

    def fallback_to_main(
        transcript: ParsedTranscript,
        code: str,
        message: str,
        *,
        line_no: int = 0,
    ) -> None:
        nodes[transcript.agent_id] = replace(
            nodes[transcript.agent_id],
            parent_agent_id=main_id,
        )
        if code:
            issues.append(
                _issue(
                    root_session_id,
                    transcript.agent_id,
                    line_no,
                    code,
                    message,
                ),
            )

    def append_missing_parent_event(transcript: ParsedTranscript) -> None:
        main = nodes[main_id]
        tool_use_id = _synthetic_tool_use_id(root_session_id, transcript.agent_id)
        suffix = 0
        while tool_use_id in tool_events:
            suffix += 1
            tool_use_id = f"{_synthetic_tool_use_id(root_session_id, transcript.agent_id)}-{suffix}"
        event = _synthetic_agent_event(
            root_session_id=root_session_id,
            agent_id=transcript.agent_id,
            event_index=len(main.events),
            message_offset=main.messages_count,
            line_no=max((item.line_no for item in main.events), default=0) + 1,
        )
        if suffix:
            event = replace(event, tool_use_id=f"{event.tool_use_id}-{suffix}")
        nodes[main_id] = replace(main, events=(*main.events, event))
        nodes[transcript.agent_id] = replace(
            nodes[transcript.agent_id],
            parent_agent_id=main_id,
            tool_use_id=event.tool_use_id,
        )
        anchors[transcript.agent_id] = _event_anchor(event)
        tool_events[event.tool_use_id or ""] = (main_id, event)

    for transcript in sorted(
        (item for item in transcripts if item.agent_kind == "subagent"),
        key=lambda item: item.agent_id,
    ):
        if transcript.task_kind == "in_process_teammate":
            fallback_to_main(
                transcript,
                "",
                "",
            )
            continue

        if transcript.task_kind == "forked_skill":
            matches: list[tuple[str, ParsedEvent]]
            if transcript.parent_tool_use_id is not None:
                matches = skill_events.get(transcript.parent_tool_use_id, [])
            else:
                matches = (
                    skill_name_events.get(transcript.skill_name, [])
                    if transcript.skill_name is not None
                    else []
                )
            if len(matches) == 1:
                owner_id, event = matches[0]
                nodes[transcript.agent_id] = replace(
                    nodes[transcript.agent_id],
                    parent_agent_id=owner_id,
                    agent_type=None,
                    name=None,
                    description=event.description,
                    tool_use_id=event.tool_use_id,
                )
                anchors[transcript.agent_id] = _event_anchor(event)
            else:
                fallback_to_main(
                    transcript,
                    "MISSING_FORKED_SKILL_PARENT",
                    "Forked skill parent trigger could not be resolved",
                )
            continue

        if transcript.agent_type == "workflow-subagent":
            explicit = (
                _meta_string(transcript.agent_meta, "workflowAgentId")
                or _meta_string(transcript.agent_meta, "workflowId")
                or _meta_string(transcript.agent_meta, "workflowToolUseId")
            )
            workflow_parent: str | None = None
            if explicit in nodes and nodes[explicit].kind == "workflow":
                workflow_parent = explicit
            elif explicit is not None and explicit in workflow_events:
                workflow_parent = next(
                    node.id
                    for node in nodes.values()
                    if node.kind == "workflow" and node.tool_use_id == explicit
                )
            elif len(workflow_ids) == 1:
                workflow_parent = workflow_ids[0]
            if workflow_parent is not None:
                nodes[transcript.agent_id] = replace(
                    nodes[transcript.agent_id],
                    parent_agent_id=workflow_parent,
                )
            else:
                fallback_to_main(
                    transcript,
                    "AMBIGUOUS_WORKFLOW_PARENT",
                    "Workflow subagent has no unambiguous Workflow parent",
                )
            continue

        parent_tool = transcript.parent_tool_use_id
        if parent_tool is None:
            parent_agent = transcript.parent_agent_id
            if parent_agent is not None and parent_agent in nodes:
                nodes[transcript.agent_id] = replace(
                    nodes[transcript.agent_id],
                    parent_agent_id=parent_agent,
                )
                parent_node = nodes[parent_agent]
                parent_anchor = (
                    _event_anchor(parent_node.events[-1])
                    if parent_node.events
                    else anchors.get(parent_agent)
                )
                if parent_anchor is not None:
                    anchors[transcript.agent_id] = parent_anchor
                continue
            fallback_to_main(
                transcript,
                "MISSING_PARENT_TOOL_USE_ID",
                "Subagent has no parent tool-use identity",
            )
            append_missing_parent_event(transcript)
            continue
        if parent_tool in ambiguous_tool_ids:
            fallback_to_main(
                transcript,
                "AMBIGUOUS_PARENT_TOOL_USE_ID",
                "Subagent parent tool-use identity is ambiguous",
            )
            append_missing_parent_event(transcript)
            continue
        matched = tool_events.get(parent_tool)
        if matched is None or matched[1].kind != "agent":
            fallback_to_main(
                transcript,
                "UNKNOWN_PARENT_TOOL_USE_ID",
                "Subagent parent tool-use identity has no Agent trigger",
            )
            append_missing_parent_event(transcript)
            continue
        owner_id, event = matched
        nodes[transcript.agent_id] = replace(
            nodes[transcript.agent_id],
            parent_agent_id=owner_id,
            description=event.description,
        )
        anchors[transcript.agent_id] = _event_anchor(event)

    nodes[main_id] = replace(nodes[main_id], parent_agent_id=None)
    cycle_nodes = _cycle_nodes(nodes, main_id)
    if cycle_nodes:
        cycle_issues = [
            _issue(
                root_session_id,
                node_id,
                nodes[node_id].events[0].line_no if nodes[node_id].events else 0,
                "PARENT_CYCLE",
                "Agent parent links contain a cycle",
            )
            for node_id in sorted(cycle_nodes)
        ]
        return None, tuple([*issues, *cycle_issues])
    try:
        depths = _depths(nodes, main_id)
    except ValueError:
        return None, tuple(
            [
                *issues,
                _issue(
                    root_session_id,
                    main_id,
                    0,
                    "UNREACHABLE_AGENT",
                    "Agent can not be traced back to the main Agent",
                ),
            ],
        )

    ordered_nodes = _canonical_order(nodes, anchors, depths, main_id)
    main = next(node for node in ordered_nodes if node.id == main_id)
    first_turn = main_transcript.user_turns[0].prompt_text if main_transcript.user_turns else ""
    title = (first_turn or main.name or root_session_id).strip()
    short_title = title[:120]
    project_path = main_transcript.root_metadata.cwd or ""
    repo_name = PurePath(project_path.rstrip("/")).name if project_path else ""
    starts = [
        timestamp
        for transcript in transcripts
        for timestamp in (transcript.started_at,)
        if timestamp is not None
    ]
    ends = [
        timestamp
        for transcript in transcripts
        for timestamp in (transcript.ended_at,)
        if timestamp is not None
    ]
    if not starts or not ends:
        return None, tuple(
            [
                *issues,
                _issue(
                    root_session_id,
                    main_id,
                    0,
                    "MISSING_SESSION_TIMESTAMP",
                    "Root session has no timestamped transcript records",
                ),
            ],
        )
    started = min(starts)
    ended = max(ends)
    tree = AssembledSessionTree(
        id=root_session_id,
        short_title=short_title,
        title=title,
        search_text=f"{title} {repo_name}".strip().lower()[:512],
        repo_name=repo_name,
        root_metadata=main_transcript.root_metadata,
        model=main.model,
        models=tuple(
            sorted(
                {node.model for node in ordered_nodes if node.model is not None},
            ),
        ),
        skill_names=tuple(
            sorted(
                {
                    event.name
                    for node in ordered_nodes
                    for event in node.events
                    if event.kind == "skill" and event.name is not None
                },
            ),
        ),
        status=_session_status(main, main_transcript, ordered_nodes, transcripts),
        user_turns_count=len(main.user_turns),
        messages_count=sum(node.messages_count for node in ordered_nodes),
        tools_count=sum(node.tools_count for node in ordered_nodes),
        errors_count=sum(node.errors_count for node in ordered_nodes),
        agents_count=sum(
            node.kind == "subagent" and node.task_kind != "forked_skill" for node in ordered_nodes
        ),
        tokens_total=sum(node.tokens_total for node in ordered_nodes),
        started_at=started,
        ended_at=ended,
        nodes=ordered_nodes,
        user_turns=main.user_turns,
    )
    return tree, tuple(issues)


def assemble_agent_trees(
    transcripts: tuple[ParsedTranscript, ...],
) -> AgentTreeAssemblyResult:
    """Assemble all roots into deterministic flat trees and aggregate counts."""
    grouped: dict[str, list[ParsedTranscript]] = {}
    for transcript in transcripts:
        grouped.setdefault(transcript.root_session_id, []).append(transcript)

    trees: list[AssembledSessionTree] = []
    issues: list[ParsedIssue] = []
    for root_id in sorted(grouped):
        if not root_id:
            issues.append(
                _issue(
                    root_id,
                    root_id,
                    0,
                    "INVALID_ROOT_SESSION_ID",
                    "Root session identity is missing",
                ),
            )
            continue
        tree, root_issues = _assemble_root(root_id, tuple(grouped[root_id]))
        issues.extend(root_issues)
        if tree is not None:
            trees.append(tree)

    ordered_trees = tuple(trees)
    nodes = tuple(node for tree in ordered_trees for node in tree.nodes)
    aggregate = AgentTreeAggregate(
        root_sessions=len(ordered_trees),
        nodes=len(nodes),
        agents=sum(node.kind == "subagent" for node in nodes),
        subagents=sum(node.kind == "subagent" for node in nodes),
        teammates=sum(node.task_kind == "in_process_teammate" for node in nodes),
        backtracked_subagents=sum(
            node.kind == "subagent" and node.parent_agent_id is not None for node in nodes
        ),
        workflow_nodes=sum(node.kind == "workflow" for node in nodes),
        forked_skill_nodes=sum(node.task_kind == "forked_skill" for node in nodes),
        roots_with_complete_parents=sum(
            all(node.parent_agent_id is not None for node in tree.nodes if node.kind != "main")
            for tree in ordered_trees
        ),
        warning_count=len(issues),
        warning_codes=tuple(sorted({issue.code for issue in issues})),
    )
    return AgentTreeAssemblyResult(
        trees=ordered_trees,
        issues=tuple(issues),
        aggregate=aggregate,
    )
