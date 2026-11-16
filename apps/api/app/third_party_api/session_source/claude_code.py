"""Claude Code session-source adapter and its closed envelope metadata schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.third_party_api.session_source.base import BaseSessionSourceAdapter
from app.third_party_api.session_source.factory import SessionSourceFactory


class ClaudeAgentMeta(BaseModel):
    """The closed Claude Code metadata slice an envelope may carry.

    Keys mirror the ``*.meta.json`` shape already consumed by the Claude trace
    parser. Unknown keys are rejected so a new runtime cannot smuggle its
    metadata through the Claude vocabulary.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )

    agent_type: str | None = None
    agent_version: str | None = None
    agent_listing_delta: Any = None
    color: str | None = None
    description: str | None = None
    finished: bool | None = None
    is_built_in: bool | None = None
    model: str | None = None
    name: str | None = None
    parent_agent_id: str | None = None
    parent_tool_use_id: str | None = None
    permission_mode: str | None = None
    picked_effort_model: str | None = None
    plan_mode_required: bool | None = None
    prompt_snapshot: Any = None
    request_non_interactive: bool | None = None
    request_shape: str | None = None
    resolved_model: str | None = None
    skill_name: str | None = None
    skill_version: str | None = None
    spawn_depth: int | None = Field(default=None, ge=0)
    task_kind: str | None = None
    team_name: str | None = None
    tool_use_id: str | None = None
    version: str | None = None
    workflow_agent_id: str | None = None
    workflow_id: str | None = None
    workflow_tool_use_id: str | None = None


@SessionSourceFactory.register
class ClaudeCodeSessionSourceAdapter(BaseSessionSourceAdapter):
    """Interpret Claude Code envelope metadata for the shared projection."""

    runtime_key = "claude-code"

    def parse_agent_meta(self, meta: Mapping[str, object]) -> Mapping[str, object]:
        """Validate the closed Claude metadata slice and return camelCase keys."""
        parsed = ClaudeAgentMeta.model_validate(dict(meta))
        return parsed.model_dump(by_alias=True, exclude_none=True)
