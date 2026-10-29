"""Public session list, overview, and execution-tree contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.service.identity.schemas import IdentityModel

SessionStatus = Literal["ok", "partial", "fail"]
AgentKind = Literal["main", "subagent", "workflow"]
EventKind = Literal["skill", "agent", "workflow"]
TaskKind = Literal["in_process_teammate", "forked_skill"]


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
    model: str | None
    started_at: datetime
    duration_seconds: int = Field(ge=0)
    status: SessionStatus
    skills: list[str]
    stats: SessionStats


class SessionListResponse(IdentityModel):
    """Current-page session cards."""

    items: list[SessionListItem]


class SessionEvent(IdentityModel):
    """One skill, Agent, or workflow trigger within an Agent node."""

    line: int = Field(ge=1)
    kind: EventKind
    name: str | None
    desc: str
    tool_use_id: str | None
    message_offset: int = Field(ge=0)


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
    agents: list[SessionAgent]
    bad_cases: list[SessionBadCase]
