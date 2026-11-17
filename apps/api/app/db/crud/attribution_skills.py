"""Persistence for immutable attribution Skill revisions and bindings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.crud.integrity import is_unique_violation
from app.db.models.domain import (
    attribution_skill_bindings,
    attribution_skill_revisions,
    attribution_skills,
    evolution_targets,
)
from app.utils.ids import new_id
from app.utils.time import now_shanghai

PLATFORM_SKILL_ID = "attribution-skill-platform-default"
PLATFORM_REVISION_ID = "attr-skill-platform-default-r1"
TARGET_BINDING_PREFIX = "target:"
WORKSPACE_DEFAULT_BINDING = "workspace-default"


@dataclass(frozen=True, slots=True)
class AttributionSkillRecord:
    """One Skill definition joined to one immutable revision."""

    id: str
    workspace_id: str | None
    skill_key: str
    display_name: str
    description: str
    built_in: bool
    enabled: bool
    revision_id: str
    revision: int
    content: Mapping[str, Any]
    content_hash: str
    executor_type: str
    output_schema_version: str
    status: str


class AttributionSkillConflict(Exception):
    """A Skill identity or revision already exists."""


class AttributionSkillReferenced(Exception):
    """A Skill revision is still referenced by a binding or historical run."""


def _record(row: RowMapping) -> AttributionSkillRecord:
    """Translate one joined row into the immutable persistence boundary."""
    content = row["content"]
    return AttributionSkillRecord(
        id=str(row["id"]),
        workspace_id=(str(row["workspace_id"]) if row["workspace_id"] is not None else None),
        skill_key=str(row["skill_key"]),
        display_name=str(row["display_name"]),
        description=str(row["description"]),
        built_in=bool(row["built_in"]),
        enabled=bool(row["enabled"]),
        revision_id=str(row["revision_id"]),
        revision=int(row["revision"]),
        content=dict(content) if isinstance(content, Mapping) else {},
        content_hash=str(row["content_hash"]),
        executor_type=str(row["executor_type"]),
        output_schema_version=str(row["output_schema_version"]),
        status=str(row["status"]),
    )


def _joined() -> Any:
    """Return the common definition/revision projection."""
    return select(
        attribution_skills.c.id,
        attribution_skills.c.workspace_id,
        attribution_skills.c.skill_key,
        attribution_skills.c.display_name,
        attribution_skills.c.description,
        attribution_skills.c.built_in,
        attribution_skills.c.enabled,
        attribution_skill_revisions.c.id.label("revision_id"),
        attribution_skill_revisions.c.revision,
        attribution_skill_revisions.c.content,
        attribution_skill_revisions.c.content_hash,
        attribution_skill_revisions.c.executor_type,
        attribution_skill_revisions.c.output_schema_version,
        attribution_skill_revisions.c.status,
    ).join(
        attribution_skill_revisions,
        attribution_skill_revisions.c.skill_id == attribution_skills.c.id,
    )


class AttributionSkillRepository:
    """Store Skill definitions, append-only revisions, and effective bindings."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database."""
        self._database = database

    async def list(self, workspace_id: str) -> tuple[AttributionSkillRecord, ...]:
        """Return platform and workspace Skills with every revision."""
        statement = (
            _joined()
            .where(
                (attribution_skills.c.workspace_id == workspace_id)
                | (attribution_skills.c.workspace_id.is_(None)),
            )
            .order_by(
                attribution_skills.c.built_in.desc(),
                attribution_skills.c.skill_key,
                attribution_skill_revisions.c.revision.desc(),
            )
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_record(row) for row in rows)

    async def get_revision(
        self,
        revision_id: str,
        workspace_id: str,
    ) -> AttributionSkillRecord | None:
        """Return a revision visible to one workspace."""
        statement = _joined().where(
            attribution_skill_revisions.c.id == revision_id,
            (attribution_skills.c.workspace_id == workspace_id)
            | (attribution_skills.c.workspace_id.is_(None)),
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _record(row) if row is not None else None

    async def get_snapshot(
        self,
        *,
        workspace_id: str,
        skill_key: str,
        revision: int,
        content_hash: str,
    ) -> AttributionSkillRecord | None:
        """Return the exact immutable revision frozen into a historical run."""
        statement = _joined().where(
            attribution_skills.c.skill_key == skill_key,
            attribution_skill_revisions.c.revision == revision,
            attribution_skill_revisions.c.content_hash == content_hash,
            (attribution_skills.c.workspace_id == workspace_id)
            | (attribution_skills.c.workspace_id.is_(None)),
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _record(row) if row is not None else None

    async def create(
        self,
        *,
        workspace_id: str,
        skill_key: str,
        display_name: str,
        description: str,
        content: Mapping[str, Any],
        content_hash: str,
        executor_type: str,
        output_schema_version: str,
    ) -> AttributionSkillRecord:
        """Create a workspace Skill and its first published revision atomically."""
        skill_id = new_id()
        revision_id = new_id()
        now = now_shanghai()
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(attribution_skills).values(
                        id=skill_id,
                        workspace_id=workspace_id,
                        skill_key=skill_key,
                        display_name=display_name,
                        description=description,
                        built_in=False,
                        enabled=True,
                        created_at=now,
                        updated_at=now,
                    ),
                )
                await session.execute(
                    insert(attribution_skill_revisions).values(
                        id=revision_id,
                        skill_id=skill_id,
                        revision=1,
                        content=dict(content),
                        content_hash=content_hash,
                        executor_type=executor_type,
                        output_schema_version=output_schema_version,
                        status="published",
                        created_at=now,
                    ),
                )
            except IntegrityError as exc:
                if is_unique_violation(exc):
                    raise AttributionSkillConflict from exc
                raise
        created = await self.get_revision(revision_id, workspace_id)
        if created is None:
            raise RuntimeError("created attribution Skill disappeared")
        return created

    async def publish_revision(
        self,
        *,
        skill_id: str,
        workspace_id: str,
        content: Mapping[str, Any],
        content_hash: str,
        executor_type: str,
        output_schema_version: str,
    ) -> AttributionSkillRecord | None:
        """Append one published revision without mutating historical content."""
        revision_id = new_id()
        async with self._database.transaction() as session:
            owned = (
                await session.execute(
                    select(attribution_skills.c.id).where(
                        attribution_skills.c.id == skill_id,
                        attribution_skills.c.workspace_id == workspace_id,
                        attribution_skills.c.built_in.is_(False),
                    ),
                )
            ).scalar_one_or_none()
            if owned is None:
                return None
            next_revision = (
                int(
                    (
                        await session.execute(
                            select(func.max(attribution_skill_revisions.c.revision)).where(
                                attribution_skill_revisions.c.skill_id == skill_id,
                            ),
                        )
                    ).scalar_one()
                    or 0,
                )
                + 1
            )
            try:
                await session.execute(
                    insert(attribution_skill_revisions).values(
                        id=revision_id,
                        skill_id=skill_id,
                        revision=next_revision,
                        content=dict(content),
                        content_hash=content_hash,
                        executor_type=executor_type,
                        output_schema_version=output_schema_version,
                        status="published",
                        created_at=now_shanghai(),
                    ),
                )
            except IntegrityError as exc:
                if is_unique_violation(exc):
                    raise AttributionSkillConflict from exc
                raise
        return await self.get_revision(revision_id, workspace_id)

    async def set_enabled(self, skill_id: str, workspace_id: str, enabled: bool) -> bool:
        """Enable or disable a workspace Skill for future resolution."""
        statement = (
            update(attribution_skills)
            .where(
                attribution_skills.c.id == skill_id,
                attribution_skills.c.workspace_id == workspace_id,
                attribution_skills.c.built_in.is_(False),
            )
            .values(enabled=enabled, updated_at=now_shanghai())
        )
        async with self._database.transaction() as session:
            result = await session.execute(statement)
        return bool(getattr(result, "rowcount", 0))

    async def bind(
        self,
        *,
        workspace_id: str,
        revision_id: str,
        target_id: str | None,
    ) -> bool:
        """Upsert a target or workspace-default binding after ownership checks."""
        binding_key = (
            f"{TARGET_BINDING_PREFIX}{target_id}" if target_id else WORKSPACE_DEFAULT_BINDING
        )
        now = now_shanghai()
        async with self._database.transaction() as session:
            visible_revision = (
                await session.execute(
                    select(attribution_skill_revisions.c.id)
                    .join(attribution_skills)
                    .where(
                        attribution_skill_revisions.c.id == revision_id,
                        attribution_skill_revisions.c.status == "published",
                        attribution_skills.c.enabled.is_(True),
                        (attribution_skills.c.workspace_id == workspace_id)
                        | (attribution_skills.c.workspace_id.is_(None)),
                    ),
                )
            ).scalar_one_or_none()
            if visible_revision is None:
                return False
            if target_id is not None:
                owned_target = (
                    await session.execute(
                        select(evolution_targets.c.id).where(
                            evolution_targets.c.id == target_id,
                            evolution_targets.c.workspace_id == workspace_id,
                        ),
                    )
                ).scalar_one_or_none()
                if owned_target is None:
                    return False
            existing = (
                await session.execute(
                    select(attribution_skill_bindings.c.id).where(
                        attribution_skill_bindings.c.workspace_id == workspace_id,
                        attribution_skill_bindings.c.binding_key == binding_key,
                    ),
                )
            ).scalar_one_or_none()
            if existing is None:
                await session.execute(
                    insert(attribution_skill_bindings).values(
                        id=new_id(),
                        workspace_id=workspace_id,
                        binding_key=binding_key,
                        target_id=target_id,
                        skill_revision_id=revision_id,
                        created_at=now,
                        updated_at=now,
                    ),
                )
            else:
                await session.execute(
                    update(attribution_skill_bindings)
                    .where(attribution_skill_bindings.c.id == existing)
                    .values(skill_revision_id=revision_id, updated_at=now),
                )
        return True

    async def unbind(self, *, workspace_id: str, target_id: str | None) -> bool:
        """Delete one mutable binding without touching historical revisions."""
        binding_key = (
            f"{TARGET_BINDING_PREFIX}{target_id}" if target_id else WORKSPACE_DEFAULT_BINDING
        )
        async with self._database.transaction() as session:
            result = await session.execute(
                delete(attribution_skill_bindings).where(
                    attribution_skill_bindings.c.workspace_id == workspace_id,
                    attribution_skill_bindings.c.binding_key == binding_key,
                ),
            )
        return bool(getattr(result, "rowcount", 0))

    async def resolve(
        self,
        workspace_id: str,
        target_id: str,
    ) -> tuple[AttributionSkillRecord, Literal["target", "workspace", "platform"]]:
        """Resolve target, workspace, then protected platform default revision."""
        bindings: tuple[tuple[str, Literal["target", "workspace"]], ...] = (
            (f"{TARGET_BINDING_PREFIX}{target_id}", "target"),
            (WORKSPACE_DEFAULT_BINDING, "workspace"),
        )
        for binding_key, source in bindings:
            statement = (
                _joined()
                .join(
                    attribution_skill_bindings,
                    attribution_skill_bindings.c.skill_revision_id
                    == attribution_skill_revisions.c.id,
                )
                .where(
                    attribution_skill_bindings.c.workspace_id == workspace_id,
                    attribution_skill_bindings.c.binding_key == binding_key,
                    attribution_skills.c.enabled.is_(True),
                    attribution_skill_revisions.c.status == "published",
                )
            )
            async with self._database.session() as session:
                row = (await session.execute(statement)).mappings().one_or_none()
            if row is not None:
                return _record(row), source
        platform = await self.get_revision(PLATFORM_REVISION_ID, workspace_id)
        if platform is None:
            raise RuntimeError("platform default attribution Skill is missing")
        return platform, "platform"
