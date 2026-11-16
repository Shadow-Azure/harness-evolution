"""Public session list, overview, and execution-tree contracts."""

from datetime import datetime
from typing import Literal, cast, get_args

from pydantic import Field

from app.service.identity.schemas import IdentityModel

SessionStatus = Literal["ok", "partial", "fail"]
AgentKind = Literal["main", "subagent", "workflow"]
EventKind = Literal["skill", "agent", "workflow"]
TaskKind = Literal["in_process_teammate", "forked_skill"]
ExecutionOutcome = Literal["completed", "interrupted", "failed", "legacy_unknown"]
EndReason = Literal[
    "end_turn",
    "tool_use_open",
    "missing_report",
    "external_failed",
    "external_interrupted",
]
DefinitionSource = Literal["prompt_snapshot", "api_request_shape", "builtin", "unknown"]
RelationConfidence = Literal["authoritative", "derived", "synthetic", "unresolved"]

EXECUTION_OUTCOMES: frozenset[str] = frozenset(
    cast(tuple[str, ...], get_args(ExecutionOutcome)),
)
END_REASONS: frozenset[str] = frozenset(cast(tuple[str, ...], get_args(EndReason)))
DEFINITION_SOURCES: frozenset[str] = frozenset(
    cast(tuple[str, ...], get_args(DefinitionSource)),
)
RELATION_CONFIDENCES: frozenset[str] = frozenset(
    cast(tuple[str, ...], get_args(RelationConfidence)),
)


def _missing(value: object) -> bool:
    """Hide optional evidence fields unless the source actually recorded them."""
    return value is None


class SessionStats(IdentityModel):
    """Backend-computed whole-tree card statistics."""

    user_turns: int = Field(ge=0)
    messages: int = Field(ge=0)
    tools: int = Field(ge=0)
    errors: int = Field(ge=0)
    agents: int = Field(ge=0)
    bad_cases: int = Field(ge=0)
    tokens: int = Field(ge=0)
    fail_per_100_messages: float = Field(ge=0)
    bad_cases_per_100_messages: float = Field(ge=0)


class SessionListItem(IdentityModel):
    """One root-session card shared by list and overview routes."""

    id: str
    short: str
    title: str
    repo: str
    runtime_key: str
    model: str | None
    started_at: datetime
    duration_seconds: int = Field(ge=0)
    status: SessionStatus
    execution_outcome: ExecutionOutcome
    skills: list[str]
    stats: SessionStats


class SessionListResponse(IdentityModel):
    """One current page plus counters."""

    items: list[SessionListItem]
    total: int = Field(
        ge=0,
        description=(
            "Normalized sessions matching q and status across the whole scope; "
            "pending roots are excluded."
        ),
    )
    pending_sessions: int = Field(
        ge=0,
        description=(
            "Distinct roots reported inside the scope that have no normalized "
            "session yet; independent of q and status."
        ),
    )


class SessionEvent(IdentityModel):
    """One skill, Agent, or workflow trigger within an Agent node."""

    line: int = Field(ge=1)
    kind: EventKind
    name: str | None
    desc: str
    tool_use_id: str | None
    message_offset: int = Field(ge=0)
    object_revision: str | None = Field(
        default=None,
        max_length=96,
        exclude_if=_missing,
        description="tag:<tag> / digest:<hash> / unknown evidence for the triggered object.",
    )
    definition_hash: str | None = Field(
        default=None,
        max_length=64,
        exclude_if=_missing,
        description="Stable body hash of the triggered skill or agent definition.",
    )
    file_read_hash: str | None = Field(
        default=None,
        max_length=64,
        exclude_if=_missing,
        description="Content hash for a complete file read that supplied the evidence.",
    )
    read_complete: bool | None = Field(
        default=None,
        exclude_if=_missing,
        description="Whether the evidence source file was read in full.",
    )
    relation_confidence: RelationConfidence | None = Field(
        default=None,
        exclude_if=_missing,
        description="Strength of the parent-child evidence for an agent trigger.",
    )


class SessionAgent(IdentityModel):
    """One flat Agent node consumed directly by the execution-flow graph."""

    agent_id: str
    parent_agent_id: str | None
    kind: AgentKind
    agent_type: str | None
    task_kind: TaskKind | None
    team_name: str | None
    skill_name: str | None
    label: str
    desc: str
    tool_use_id: str | None
    spawn_depth: int = Field(ge=0)
    lines: int = Field(ge=0)
    messages_count: int = Field(ge=0)
    execution_outcome: ExecutionOutcome
    end_reason: EndReason | None = Field(default=None, exclude_if=_missing)
    agent_definition_hash: str | None = Field(
        default=None,
        max_length=64,
        exclude_if=_missing,
        description="Stable body hash of this agent's definition when it has one.",
    )
    definition_source: DefinitionSource | None = Field(
        default=None,
        exclude_if=_missing,
        description="Where the agent definition body was recovered from.",
    )
    events: list[SessionEvent]


class BadCaseAnchor(IdentityModel):
    """Stable host Agent and event index for one problem card."""

    agent_id: str
    event_index: int = Field(ge=-1)


class BadCaseAgent(IdentityModel):
    """The reporter that originally supplied a problem report."""

    session_id: str
    agent_id: str | None


class SessionBadCase(IdentityModel):
    """One read-only problem connected to the execution tree.

    ``title`` is the short display title and ``reason`` the description body;
    ``reason`` maps from the ``bad_cases.bad_case_description`` column.
    """

    bad_case_id: str
    bad_case_type: Literal["self", "discovery"]
    object_name: str
    object_type: Literal["skill", "agent"]
    object_version: str | None
    anchor: BadCaseAnchor
    bad_case_agent: BadCaseAgent
    title: str
    reason: str


class SessionTree(IdentityModel):
    """Flat canonical Agent tree plus anchored read-only problem cards."""

    session_id: str
    runtime_key: str
    agents: list[SessionAgent]
    bad_cases: list[SessionBadCase]
