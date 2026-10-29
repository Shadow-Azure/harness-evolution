"""Strict loader for deterministic development and demo fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

MAX_CORPUS_BYTES = 128 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024
ROOT_SESSION_COUNT = 4
PRIVATE_MARKER = re.compile(
    r"(?:/Users/|/home/|[A-Za-z]:\\|\\\\[^\\\s]+\\|claude-code-sessions|"
    r"\.claude/|sk-ant-|Bearer\s+[A-Za-z0-9]|"
    r"(?:https?|ssh|git)://[^/\s@]+@|"
    r"HE_(?:JWT|DB|ADMIN)_)",
    re.IGNORECASE,
)
CREDENTIAL_QUERY_KEYS = frozenset(
    {"access_token", "api_key", "password", "secret", "signature", "token"},
)


class FixtureModel(BaseModel):
    """Closed camelCase fixture schema shared by every nested object."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class UserTurnFixture(FixtureModel):
    """One deterministic user prompt anchor."""

    id: str = Field(min_length=1, max_length=36)
    seq: int = Field(ge=1)
    prompt_text: str = Field(min_length=1, max_length=2_000)
    started_at: datetime
    line_no: int = Field(ge=1)
    message_offset: int = Field(ge=0)


class AgentEventFixture(FixtureModel):
    """One skill, agent, or workflow trigger within an agent transcript."""

    event_index: int = Field(ge=0)
    line_no: int = Field(ge=1)
    message_offset: int = Field(ge=0)
    kind: Literal["skill", "agent", "workflow"]
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    tool_use_id: str | None = Field(default=None, max_length=128)


class AgentFixture(FixtureModel):
    """One agent transcript and its normalized read-model metadata."""

    id: str = Field(min_length=1, max_length=64)
    kind: Literal["main", "subagent", "workflow"]
    agent_type: str | None = Field(default=None, max_length=64)
    task_kind: str | None = Field(default=None, max_length=32)
    team_name: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=255)
    skill_name: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=64)
    requested_model: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2_000)
    tool_use_id: str | None = Field(default=None, max_length=128)
    parent_agent_id: str | None = Field(default=None, max_length=64)
    spawn_depth: int = Field(ge=0)
    messages_count: int = Field(ge=0)
    tokens_total: int = Field(ge=0)
    tools_count: int = Field(ge=0)
    errors_count: int = Field(ge=0)
    meta: dict[str, object] | None = None
    sort_key: float
    payload_file: str | None = Field(default=None, min_length=1, max_length=256)
    events: tuple[AgentEventFixture, ...] = ()
    user_turns: tuple[UserTurnFixture, ...] = ()


class SessionFixture(FixtureModel):
    """One deterministic root session."""

    id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    short_title: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=2_000)
    repo_name: str = Field(min_length=1, max_length=255)
    project_path: str = Field(min_length=1, max_length=2_000)
    git_branch: str | None = Field(default=None, max_length=255)
    cli_version: str | None = Field(default=None, max_length=32)
    entrypoint: str | None = Field(default=None, max_length=16)
    started_at: datetime
    ended_at: datetime
    status: Literal["ok", "partial", "fail"]
    source_type: Literal["script", "http_api"]
    imported_at: datetime
    updated_at: datetime
    agents: tuple[AgentFixture, ...] = Field(min_length=1)

    @field_validator("project_path")
    @classmethod
    def validate_synthetic_project_path(cls, value: str) -> str:
        """Constrain fixture paths to a stable synthetic workspace root."""
        path = Path(value)
        if not value.startswith("/workspace/") or "\\" in value or ".." in path.parts:
            raise ValueError("projectPath must be an absolute synthetic /workspace path")
        return value

    @model_validator(mode="after")
    def validate_session(self) -> SessionFixture:
        """Require a single main node and monotonic session time."""
        mains = [agent for agent in self.agents if agent.kind == "main"]
        if len(mains) != 1:
            raise ValueError("each session must contain exactly one main agent")
        if mains[0].id != self.id:
            raise ValueError("the main agent id must equal the root session id")
        if self.ended_at < self.started_at:
            raise ValueError("session endedAt must not precede startedAt")
        return self


class BadCaseFixture(FixtureModel):
    """One synthetic externally-owned issue report."""

    bad_case_id: str = Field(min_length=1, max_length=64)
    bad_case_session_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    bad_case_type: Literal["self", "discovery"]
    object_name: str = Field(min_length=1, max_length=128)
    object_type: Literal["skill", "agent"]
    object_version: str | None = Field(default=None, max_length=64)
    bad_case_agent_id: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2_000)
    meta_data: dict[str, object] | None = None
    source: str | None = Field(default=None, max_length=64)
    created_at: datetime
    updated_at: datetime

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Require a non-blank short title for every demo problem card."""
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class ProbeFixture(FixtureModel):
    """One synthetic externally-owned root-cause report."""

    probe_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    probe_type: Literal["skill", "agent"]
    probe_object: str = Field(min_length=1, max_length=128)
    object_version: str | None = Field(default=None, max_length=64)
    attribute_type: Literal["model", "prompt", "error"]
    probe_description: str = Field(min_length=1, max_length=2_000)
    probe_analysis: str = Field(min_length=1, max_length=8_000)
    created_at: datetime
    updated_at: datetime


class BadCaseAnalysisFixture(FixtureModel):
    """One synthetic attribution state."""

    bad_case_id: str = Field(min_length=1, max_length=64)
    analysis_status: Literal["unanalyzed", "analyzed_nonissue", "analyzed_issue"]
    probe_id: str | None = Field(default=None, max_length=64)
    analysis_result: dict[str, object] | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_probe_link(self) -> BadCaseAnalysisFixture:
        """Enforce the documented analysis-to-probe relationship."""
        if (self.analysis_status == "analyzed_issue") != (self.probe_id is not None):
            raise ValueError("only analyzed_issue rows may link a probe")
        return self


class EvolutionTargetFixture(FixtureModel):
    """One synthetic evolution target configuration."""

    id: str = Field(min_length=1, max_length=36)
    object_type: Literal["skill", "agent"]
    object_name: str = Field(min_length=1, max_length=128)
    repo_url: str = Field(min_length=1, max_length=1024)
    sub_dir: str = Field(min_length=1, max_length=512)
    default_ref: str = Field(min_length=1, max_length=128)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("repo_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        """Accept network repository URLs without embedded credentials."""
        parsed = urlparse(value)
        if parsed.scheme not in {"git", "http", "https", "ssh"} or not parsed.hostname:
            raise ValueError("repoUrl must be an absolute network repository URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("repoUrl must not contain userinfo credentials")
        if any(key.lower() in CREDENTIAL_QUERY_KEYS for key, _ in parse_qsl(parsed.query)):
            raise ValueError("repoUrl must not contain credential query parameters")
        return value


class FixtureManifest(FixtureModel):
    """Top-level fixture corpus schema."""

    version: Literal[1]
    scope: Literal["m2-synthetic"]
    root_sessions: tuple[SessionFixture, ...] = Field(min_length=ROOT_SESSION_COUNT)
    bad_cases: tuple[BadCaseFixture, ...] = ()
    bad_case_analyses: tuple[BadCaseAnalysisFixture, ...] = ()
    probe_reports: tuple[ProbeFixture, ...] = ()
    evolution_targets: tuple[EvolutionTargetFixture, ...] = ()


@dataclass(frozen=True, slots=True)
class LoadedPayload:
    """A validated JSONL payload with derived identity."""

    content: str
    content_hash: str
    line_count: int

    @property
    def present(self) -> bool:
        """Return whether this agent owns a transcript payload."""
        return self.line_count > 0


@dataclass(frozen=True, slots=True)
class FixtureAgent:
    """An agent fixture plus its loaded payload."""

    record: AgentFixture
    payload: LoadedPayload

    @property
    def content(self) -> str:
        """Return the validated raw JSONL."""
        return self.payload.content

    @property
    def content_hash(self) -> str:
        """Return the derived SHA-256 content hash."""
        return self.payload.content_hash

    @property
    def line_count(self) -> int:
        """Return the derived non-empty JSONL line count."""
        return self.payload.line_count

    @property
    def has_payload(self) -> bool:
        """Return whether the node has an independently stored transcript."""
        return self.payload.present


@dataclass(frozen=True, slots=True)
class FixtureSession:
    """A root session fixture with loaded agents."""

    record: SessionFixture
    agents: tuple[FixtureAgent, ...]

    @property
    def id(self) -> str:
        """Return the root session id."""
        return self.record.id


@dataclass(frozen=True, slots=True)
class FixtureCorpus:
    """A fully validated and payload-loaded fixture corpus."""

    manifest: FixtureManifest
    root_sessions: tuple[FixtureSession, ...]
    total_bytes: int

    @property
    def agents(self) -> tuple[FixtureAgent, ...]:
        """Flatten all loaded agents in deterministic session order."""
        return tuple(agent for session in self.root_sessions for agent in session.agents)


def _ensure_unique(values: Iterable[Hashable], label: str) -> None:
    seen: set[Hashable] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label}: {value}")
        seen.add(value)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one object while rejecting keys that JSON would silently overwrite."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_payload(
    path: Path,
    corpus_root: Path,
    *,
    expected_session_id: str,
    expected_agent_id: str,
) -> LoadedPayload:
    resolved = path.resolve()
    if not resolved.is_relative_to(corpus_root.resolve()):
        raise ValueError(f"payload path escapes corpus root: {path}")
    data = resolved.read_bytes()
    if len(data) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES}-byte budget: {path.name}")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"payload is not UTF-8 JSONL: {path.name}") from exc
    lines = content.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise ValueError(f"payload must contain non-empty JSONL lines: {path.name}")
    for line in lines:
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except json.JSONDecodeError as exc:
            raise ValueError(f"payload is not valid JSONL: {path.name}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"payload lines must be JSON objects: {path.name}")
        session_id = value.get("sessionId")
        if session_id != expected_session_id:
            raise ValueError(
                f"payload session id does not match manifest: {path.name}: {session_id}",
            )
        agent_id = value.get("agentId")
        if expected_agent_id != expected_session_id and agent_id is None:
            raise ValueError(f"payload agent id is required for child agent: {path.name}")
        if agent_id is not None and agent_id != expected_agent_id:
            raise ValueError(
                f"payload agent id does not match manifest: {path.name}: {agent_id}",
            )
    return LoadedPayload(
        content=content,
        content_hash=hashlib.sha256(data).hexdigest(),
        line_count=len(lines),
    )


def load_fixture_corpus(path: Path) -> FixtureCorpus:
    """Load, validate, and size-bound one deterministic fixture corpus."""
    corpus_root = path.parent.resolve()
    raw = path.read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > MAX_CORPUS_BYTES:
        raise ValueError(f"fixture corpus exceeds {MAX_CORPUS_BYTES}-byte budget")
    if PRIVATE_MARKER.search(raw):
        raise ValueError(
            "fixture corpus contains a real-session path marker, credential, or secret",
        )
    try:
        manifest = FixtureManifest.model_validate_json(raw)
    except ValueError as exc:
        raise ValueError(f"invalid fixture corpus: {exc}") from exc
    if len(manifest.root_sessions) != ROOT_SESSION_COUNT:
        raise ValueError(f"fixture corpus must contain exactly {ROOT_SESSION_COUNT} roots")

    _ensure_unique((session.id for session in manifest.root_sessions), "root session id")
    loaded_sessions: list[FixtureSession] = []
    allowed_files = {"corpus.json"}
    total_payload_bytes = 0
    all_agent_ids = [agent.id for session in manifest.root_sessions for agent in session.agents]
    _ensure_unique(iter(all_agent_ids), "agent id")
    all_agent_locations = {
        agent.id: (session.id, agent.kind)
        for session in manifest.root_sessions
        for agent in session.agents
    }
    all_user_turn_ids: list[str] = []

    for session in manifest.root_sessions:
        loaded_agents: list[FixtureAgent] = []
        session_agent_ids = {agent.id for agent in session.agents}
        for agent in session.agents:
            if agent.parent_agent_id is not None and agent.parent_agent_id not in session_agent_ids:
                raise ValueError(f"unknown parent agent id: {agent.parent_agent_id}")
            if agent.spawn_depth == 0 and agent.parent_agent_id is not None:
                raise ValueError("root agents cannot declare a parent")
            if agent.spawn_depth > 0 and agent.parent_agent_id is None:
                raise ValueError("nested agents must declare a parent")
            if agent.kind != "main" and agent.user_turns:
                raise ValueError("only main agents may own user turns")
            _ensure_unique(
                (event.event_index for event in agent.events),
                f"agent {agent.id} event index",
            )
            _ensure_unique(
                (turn.seq for turn in agent.user_turns),
                f"agent {agent.id} user turn sequence",
            )
            all_user_turn_ids.extend(turn.id for turn in agent.user_turns)
            if agent.kind == "workflow":
                if agent.payload_file is not None or agent.messages_count != 0:
                    raise ValueError("workflow nodes cannot own a transcript")
                payload = LoadedPayload(
                    content="",
                    content_hash=hashlib.sha256(b"").hexdigest(),
                    line_count=0,
                )
            else:
                if agent.payload_file is None:
                    raise ValueError(f"agent {agent.id} must provide a payloadFile")
                payload_path = corpus_root / agent.payload_file
                relative = payload_path.resolve().relative_to(corpus_root)
                allowed_files.add(relative.as_posix())
                payload = _load_payload(
                    payload_path,
                    corpus_root,
                    expected_session_id=session.id,
                    expected_agent_id=agent.id,
                )
            if PRIVATE_MARKER.search(payload.content):
                raise ValueError(
                    f"payload contains a real-session path marker: {agent.payload_file}"
                )
            total_payload_bytes += len(payload.content.encode("utf-8"))
            loaded_agents.append(FixtureAgent(record=agent, payload=payload))
        loaded_sessions.append(FixtureSession(record=session, agents=tuple(loaded_agents)))

    _ensure_unique(iter(all_user_turn_ids), "user turn id")

    if total_payload_bytes > MAX_CORPUS_BYTES:
        raise ValueError(f"payload corpus exceeds {MAX_CORPUS_BYTES}-byte budget")

    actual_files = {
        file.relative_to(corpus_root).as_posix()
        for file in corpus_root.rglob("*")
        if file.is_file()
    }
    unexpected = sorted(actual_files - allowed_files)
    if unexpected:
        raise ValueError(f"unlisted fixture file: {unexpected[0]}")

    session_ids = {session.id for session in manifest.root_sessions}
    _ensure_unique((case.bad_case_id for case in manifest.bad_cases), "bad case id")
    for case in manifest.bad_cases:
        if case.bad_case_session_id not in session_ids:
            raise ValueError(f"bad case references unknown session: {case.bad_case_session_id}")
        if case.bad_case_agent_id is not None:
            location = all_agent_locations.get(case.bad_case_agent_id)
            if location is None:
                raise ValueError(f"bad case references unknown agent: {case.bad_case_agent_id}")
            agent_session_id, agent_kind = location
            if agent_session_id != case.bad_case_session_id:
                raise ValueError("bad case agent must belong to the same session")
            if agent_kind == "main":
                raise ValueError("bad case main agent anchor must be null, not a root agent")
    _ensure_unique((probe.probe_id for probe in manifest.probe_reports), "probe id")
    for probe in manifest.probe_reports:
        if probe.session_id not in session_ids:
            raise ValueError(f"probe references unknown session: {probe.session_id}")
    bad_case_ids = {case.bad_case_id for case in manifest.bad_cases}
    _ensure_unique(
        (analysis.bad_case_id for analysis in manifest.bad_case_analyses),
        "bad case analysis",
    )
    probe_ids = {probe.probe_id for probe in manifest.probe_reports}
    for analysis in manifest.bad_case_analyses:
        if analysis.bad_case_id not in bad_case_ids:
            raise ValueError(f"analysis references unknown bad case: {analysis.bad_case_id}")
        if analysis.probe_id is not None and analysis.probe_id not in probe_ids:
            raise ValueError(f"analysis references unknown probe: {analysis.probe_id}")
    _ensure_unique((target.id for target in manifest.evolution_targets), "target id")

    return FixtureCorpus(
        manifest=manifest,
        root_sessions=tuple(loaded_sessions),
        total_bytes=total_payload_bytes,
    )
