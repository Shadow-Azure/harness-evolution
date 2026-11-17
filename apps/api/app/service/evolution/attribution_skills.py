"""Attribution Skill registry, publication, binding, and resolution rules."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field

from app.db.crud.attribution_skills import (
    AttributionSkillConflict,
    AttributionSkillRecord,
    AttributionSkillRepository,
)
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import IdentityModel

_SKILL_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SUPPORTED_OUTPUT_SCHEMA = "probe-report/v2"
ExecutorType = Literal["builtin_rule", "agent_stub", "agent"]


class AttributionSkillRevisionWrite(IdentityModel):
    """Content and compatibility metadata for one immutable revision."""

    content: dict[str, Any]
    executor_type: ExecutorType = "agent_stub"
    output_schema_version: str = Field(default=SUPPORTED_OUTPUT_SCHEMA, max_length=32)


class AttributionSkillCreate(AttributionSkillRevisionWrite):
    """Create one Skill and publish its first revision."""

    skill_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)


class AttributionSkillBindingWrite(IdentityModel):
    """Select one published immutable revision for a binding."""

    skill_revision_id: str = Field(min_length=1, max_length=36)


class AttributionSkillStateWrite(IdentityModel):
    """Enable or disable a workspace-owned Skill."""

    enabled: bool


class AttributionSkillRevision(IdentityModel):
    """Public immutable Skill revision."""

    id: str
    skill_id: str
    workspace_id: str | None
    skill_key: str
    display_name: str
    description: str
    built_in: bool
    enabled: bool
    revision: int
    content: dict[str, Any]
    content_hash: str
    executor_type: str
    output_schema_version: str
    status: str


class AttributionSkillList(IdentityModel):
    """All platform and workspace Skill revisions visible in one workspace."""

    items: list[AttributionSkillRevision]


class EffectiveAttributionSkill(AttributionSkillRevision):
    """Resolved Skill revision plus the precedence source that selected it."""

    source: Literal["target", "workspace", "platform"]


def _public(record: AttributionSkillRecord) -> AttributionSkillRevision:
    """Map one persistence record to its public contract."""
    return AttributionSkillRevision(
        id=record.revision_id,
        skill_id=record.id,
        workspace_id=record.workspace_id,
        skill_key=record.skill_key,
        display_name=record.display_name,
        description=record.description,
        built_in=record.built_in,
        enabled=record.enabled,
        revision=record.revision,
        content=dict(record.content),
        content_hash=record.content_hash,
        executor_type=record.executor_type,
        output_schema_version=record.output_schema_version,
        status=record.status,
    )


def _content_hash(content: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 identity of controlled Skill content."""
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_revision(body: AttributionSkillRevisionWrite) -> str:
    """Validate compatibility and return the stable content hash."""
    if body.output_schema_version != SUPPORTED_OUTPUT_SCHEMA:
        raise AppError(
            status_code=422,
            code=ErrorCode.ATTRIBUTION_SKILL_INVALID,
            message="attribution Skill output schema is incompatible",
            details={"supported": SUPPORTED_OUTPUT_SCHEMA},
        )
    if not body.content:
        raise AppError(
            status_code=422,
            code=ErrorCode.ATTRIBUTION_SKILL_INVALID,
            message="attribution Skill content is required",
        )
    return _content_hash(body.content)


class AttributionSkillService:
    """Own Skill validation, immutable publication, and binding precedence."""

    def __init__(self, repository: AttributionSkillRepository) -> None:
        """Bind the service to Skill persistence."""
        self._repository = repository

    async def list(self, workspace_id: str) -> AttributionSkillList:
        """List every revision visible to one workspace."""
        return AttributionSkillList(
            items=[_public(item) for item in await self._repository.list(workspace_id)],
        )

    async def create(
        self,
        workspace_id: str,
        body: AttributionSkillCreate,
    ) -> AttributionSkillRevision:
        """Create and publish revision one of a workspace Skill."""
        skill_key = body.skill_key.strip().lower()
        if not _SKILL_KEY.fullmatch(skill_key) or skill_key == "platform-default":
            raise AppError(
                status_code=422,
                code=ErrorCode.ATTRIBUTION_SKILL_INVALID,
                message="attribution Skill key is invalid",
            )
        content_hash = _validate_revision(body)
        try:
            record = await self._repository.create(
                workspace_id=workspace_id,
                skill_key=skill_key,
                display_name=body.display_name.strip(),
                description=body.description.strip(),
                content=body.content,
                content_hash=content_hash,
                executor_type=body.executor_type,
                output_schema_version=body.output_schema_version,
            )
        except AttributionSkillConflict:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_SKILL_EXISTS,
                message="attribution Skill already exists",
            ) from None
        return _public(record)

    async def publish(
        self,
        workspace_id: str,
        skill_id: str,
        body: AttributionSkillRevisionWrite,
    ) -> AttributionSkillRevision:
        """Append one revision; existing revision content is never updated."""
        content_hash = _validate_revision(body)
        try:
            record = await self._repository.publish_revision(
                skill_id=skill_id,
                workspace_id=workspace_id,
                content=body.content,
                content_hash=content_hash,
                executor_type=body.executor_type,
                output_schema_version=body.output_schema_version,
            )
        except AttributionSkillConflict:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_SKILL_EXISTS,
                message="identical attribution Skill revision already exists",
            ) from None
        if record is None:
            raise self._not_found()
        return _public(record)

    async def set_enabled(
        self,
        workspace_id: str,
        skill_id: str,
        enabled: bool,
    ) -> None:
        """Change future eligibility without mutating historical revisions."""
        if not await self._repository.set_enabled(skill_id, workspace_id, enabled):
            raise self._not_found()

    async def bind(
        self,
        workspace_id: str,
        revision_id: str,
        *,
        target_id: str | None,
    ) -> EffectiveAttributionSkill:
        """Bind a published compatible revision and return the effective result."""
        if not await self._repository.bind(
            workspace_id=workspace_id,
            revision_id=revision_id,
            target_id=target_id,
        ):
            raise AppError(
                status_code=404,
                code=ErrorCode.ATTRIBUTION_SKILL_NOT_FOUND,
                message="Skill revision or target was not found",
            )
        return await self.resolve(workspace_id, target_id or "")

    async def unbind(self, workspace_id: str, *, target_id: str | None) -> None:
        """Remove one binding; future resolution falls back automatically."""
        await self._repository.unbind(workspace_id=workspace_id, target_id=target_id)

    async def resolve(self, workspace_id: str, target_id: str) -> EffectiveAttributionSkill:
        """Resolve target override, workspace default, then platform default."""
        record, source = await self._repository.resolve(workspace_id, target_id)
        return EffectiveAttributionSkill(**_public(record).model_dump(), source=source)

    @staticmethod
    def _not_found() -> AppError:
        """Return the stable missing-Skill response."""
        return AppError(
            status_code=404,
            code=ErrorCode.ATTRIBUTION_SKILL_NOT_FOUND,
            message="attribution Skill was not found",
        )
