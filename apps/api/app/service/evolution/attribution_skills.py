"""Attribution Skill registry, publication, binding, and resolution rules."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from app.config import DEFAULT_ATTRIBUTION_GOLDEN_SET
from app.db.crud.attribution_skills import (
    AttributionQualityEventRecord,
    AttributionSkillConflict,
    AttributionSkillRecord,
    AttributionSkillRepository,
)
from app.db.crud.evolution_targets import EvolutionTargetRecord
from app.errors import AppError, ErrorCode
from app.service.evolution.attribution import AttributionSkillSnapshot
from app.service.evolution.attribution_eval import (
    ShadowCandidate,
    ShadowEvaluationReport,
    evaluate_shadow,
    load_golden_set,
)
from app.service.evolution.attribution_executor import AGENT_SKILL_STUB_ENGINE
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
    quality_status: str


class AttributionQualityEvaluation(IdentityModel):
    """One persisted isolated shadow report and its audit identity."""

    id: str
    skill_revision_id: str
    actor_id: str
    created_at: datetime
    report: ShadowEvaluationReport


class AttributionQualityDecisionWrite(IdentityModel):
    """Human acceptance or rejection of one exact shadow evaluation."""

    evaluation_event_id: str = Field(min_length=1, max_length=36)
    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=1, max_length=2000)


class AttributionQualityEvent(IdentityModel):
    """Append-only evaluation, promotion, rejection, or rollback evidence."""

    id: str
    skill_revision_id: str
    event_type: str
    evaluation_hash: str | None
    payload: dict[str, Any]
    actor_id: str
    reason: str
    created_at: datetime


class AttributionQualityHistory(IdentityModel):
    """Ordered quality audit trail for one revision."""

    items: list[AttributionQualityEvent]


class AttributionRollbackWrite(IdentityModel):
    """Human reason attached to a workspace-default rollback."""

    reason: str = Field(min_length=1, max_length=2000)


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
        quality_status=record.quality_status,
    )


def _quality_public(record: AttributionQualityEventRecord) -> AttributionQualityEvent:
    """Map one append-only quality record to its API contract."""
    return AttributionQualityEvent(
        id=record.id,
        skill_revision_id=record.skill_revision_id,
        event_type=record.event_type,
        evaluation_hash=record.evaluation_hash,
        payload=dict(record.payload),
        actor_id=record.actor_id,
        reason=record.reason,
        created_at=record.created_at,
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

    def __init__(
        self,
        repository: AttributionSkillRepository,
        golden_set_path: Path = DEFAULT_ATTRIBUTION_GOLDEN_SET,
    ) -> None:
        """Bind the service to Skill persistence."""
        self._repository = repository
        self._golden_set_path = golden_set_path

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
        revision = await self._repository.get_revision(revision_id, workspace_id)
        if revision is None:
            raise self._not_found()
        if target_id is None and revision.quality_status != "eligible":
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_QUALITY_GATE_FAILED,
                message="attribution Skill revision is not production-eligible",
                details={"qualityStatus": revision.quality_status},
            )
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

    async def evaluate_revision(
        self,
        workspace_id: str,
        revision_id: str,
        actor_id: str,
    ) -> AttributionQualityEvaluation:
        """Run one revision against the sanitized Golden Set in isolation."""
        revision = await self._repository.get_revision(revision_id, workspace_id)
        if revision is None:
            raise self._not_found()
        engine = {
            "builtin_rule": "rule-v1",
            "agent_stub": AGENT_SKILL_STUB_ENGINE,
        }.get(revision.executor_type)
        if engine is None:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_ENGINE_UNAVAILABLE,
                message="attribution executor is not available in this deployment",
                details={"executorType": revision.executor_type},
            )
        report = await evaluate_shadow(
            load_golden_set(self._golden_set_path),
            ShadowCandidate(
                engine=engine,
                skill_key=revision.skill_key,
                skill_revision=revision.revision,
                skill_content_hash=revision.content_hash,
                skill_executor_type=revision.executor_type,
                skill_content=dict(revision.content),
            ),
        )
        event = await self._repository.record_quality_evaluation(
            workspace_id=workspace_id,
            revision_id=revision_id,
            actor_id=actor_id,
            evaluation_hash=report.evaluation_hash,
            payload=report.model_dump(mode="json", by_alias=True),
        )
        if event is None:
            raise self._not_found()
        return AttributionQualityEvaluation(
            id=event.id,
            skill_revision_id=event.skill_revision_id,
            actor_id=event.actor_id,
            created_at=event.created_at,
            report=report,
        )

    async def decide_quality(
        self,
        workspace_id: str,
        revision_id: str,
        actor_id: str,
        body: AttributionQualityDecisionWrite,
    ) -> AttributionSkillRevision:
        """Apply one human decision backed by an exact shadow report."""
        event = await self._repository.get_quality_event(
            body.evaluation_event_id,
            workspace_id,
        )
        current_golden_hash = load_golden_set(self._golden_set_path).content_hash
        if (
            event is None
            or event.skill_revision_id != revision_id
            or event.event_type != "evaluated"
        ):
            raise self._not_found()
        if event.payload.get("goldenSetHash") != current_golden_hash:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_QUALITY_GATE_FAILED,
                message="shadow evaluation uses a stale Golden Set",
                details={"currentGoldenSetHash": current_golden_hash},
            )
        try:
            record = await self._repository.decide_quality(
                workspace_id=workspace_id,
                revision_id=revision_id,
                evaluation_event_id=body.evaluation_event_id,
                decision=body.decision,
                actor_id=actor_id,
                reason=body.reason.strip(),
            )
        except ValueError as exc:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_QUALITY_GATE_FAILED,
                message=str(exc),
            ) from None
        if record is None:
            raise self._not_found()
        return _public(record)

    async def quality_history(
        self,
        workspace_id: str,
        revision_id: str,
    ) -> AttributionQualityHistory:
        """Return the immutable evaluation and decision trail for one revision."""
        if await self._repository.get_revision(revision_id, workspace_id) is None:
            raise self._not_found()
        return AttributionQualityHistory(
            items=[
                _quality_public(item)
                for item in await self._repository.list_quality_events(
                    workspace_id=workspace_id,
                    revision_id=revision_id,
                )
            ],
        )

    async def rollback_default(
        self,
        workspace_id: str,
        actor_id: str,
        body: AttributionRollbackWrite,
    ) -> EffectiveAttributionSkill:
        """Restore the prior eligible workspace revision or platform rule."""
        record = await self._repository.rollback_workspace_default(
            workspace_id=workspace_id,
            actor_id=actor_id,
            reason=body.reason.strip(),
        )
        if record is None:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_QUALITY_GATE_FAILED,
                message="workspace has no custom default attribution Skill to roll back",
            )
        return EffectiveAttributionSkill(**_public(record).model_dump(), source="workspace")

    async def unbind(self, workspace_id: str, *, target_id: str | None) -> None:
        """Remove one binding; future resolution falls back automatically."""
        await self._repository.unbind(workspace_id=workspace_id, target_id=target_id)

    async def resolve_for_run(
        self, target: EvolutionTargetRecord, package_id: str | None
    ) -> EffectiveAttributionSkill:
        if package_id or target.attribution_package_id:
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="Skill recomputation requires an available attribution runtime",
            )
        return await self.resolve(target.workspace_id, target.id)

    async def resolve(self, workspace_id: str, target_id: str) -> EffectiveAttributionSkill:
        """Resolve target override, workspace default, then platform default."""
        record, source = await self._repository.resolve(workspace_id, target_id)
        return EffectiveAttributionSkill(**_public(record).model_dump(), source=source)

    async def resolve_snapshot(
        self,
        workspace_id: str,
        skill_key: str,
        revision: int,
        content_hash: str,
    ) -> AttributionSkillSnapshot:
        """Resolve the exact immutable Skill identity frozen into one run."""
        record = await self._repository.get_snapshot(
            workspace_id=workspace_id,
            skill_key=skill_key,
            revision=revision,
            content_hash=content_hash,
        )
        if record is None:
            raise AppError(
                status_code=409,
                code=ErrorCode.ATTRIBUTION_SKILL_NOT_FOUND,
                message="frozen attribution Skill revision was not found",
            )
        return AttributionSkillSnapshot(
            executor_type=record.executor_type,
            content=record.content,
        )

    @staticmethod
    def _not_found() -> AppError:
        """Return the stable missing-Skill response."""
        return AppError(
            status_code=404,
            code=ErrorCode.ATTRIBUTION_SKILL_NOT_FOUND,
            message="attribution Skill was not found",
        )
