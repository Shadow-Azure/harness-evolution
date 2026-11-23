"""Persistence for workspace-owned attribution Skill ZIP packages."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.crud.integrity import is_unique_violation
from app.db.models.domain import (
    attribution_skill_package_bindings,
    attribution_skill_packages,
    evolution_targets,
)
from app.errors import AppError, ErrorCode


@dataclass(frozen=True, slots=True)
class AttributionSkillPackageRecord:
    """Stored package metadata plus its extracted prompt."""

    id: str
    workspace_id: str
    skill_name: str
    uploader_id: str | None
    uploader_name: str
    archive_name: str
    file_count: int
    size_bytes: int
    content_hash: str
    storage_path: str
    skill_md_path: str
    prompt_text: str
    created_at: datetime


class AttributionSkillPackageConflict(Exception):
    """A workspace already owns a package with this Skill name."""


def _record(row: object) -> AttributionSkillPackageRecord:
    """Translate one SQLAlchemy row mapping into the persistence boundary."""
    values = row  # typed mappings vary across SQLAlchemy dialects
    return AttributionSkillPackageRecord(
        id=str(values["id"]),  # type: ignore[index]
        workspace_id=str(values["workspace_id"]),  # type: ignore[index]
        skill_name=str(values["skill_name"]),  # type: ignore[index]
        uploader_id=(
            str(values["uploader_id"])  # type: ignore[index]
            if values["uploader_id"] is not None  # type: ignore[index]
            else None
        ),
        uploader_name=str(values["uploader_name"]),  # type: ignore[index]
        archive_name=str(values["archive_name"]),  # type: ignore[index]
        file_count=int(values["file_count"]),  # type: ignore[index]
        size_bytes=int(values["size_bytes"]),  # type: ignore[index]
        content_hash=str(values["content_hash"]),  # type: ignore[index]
        storage_path=str(values["storage_path"]),  # type: ignore[index]
        skill_md_path=str(values["skill_md_path"]),  # type: ignore[index]
        prompt_text=str(values["prompt_text"]),  # type: ignore[index]
        created_at=values["created_at"],  # type: ignore[index]
    )


class AttributionSkillPackageRepository:
    """Store package metadata and one optional custom binding per workspace."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database."""
        self._database = database

    async def list(self, workspace_id: str) -> tuple[AttributionSkillPackageRecord, ...]:
        """Return custom packages newest first."""
        statement = (
            select(attribution_skill_packages)
            .where(attribution_skill_packages.c.workspace_id == workspace_id)
            .order_by(attribution_skill_packages.c.created_at.desc())
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_record(row) for row in rows)

    async def get(
        self,
        workspace_id: str,
        package_id: str,
    ) -> AttributionSkillPackageRecord | None:
        """Return one package only inside its owning workspace."""
        statement = select(attribution_skill_packages).where(
            attribution_skill_packages.c.workspace_id == workspace_id,
            attribution_skill_packages.c.id == package_id,
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _record(row) if row is not None else None

    async def create(self, record: AttributionSkillPackageRecord) -> None:
        """Insert metadata after the service has durably extracted the package."""
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(attribution_skill_packages).values(
                        id=record.id,
                        workspace_id=record.workspace_id,
                        skill_name=record.skill_name,
                        uploader_id=record.uploader_id,
                        uploader_name=record.uploader_name,
                        archive_name=record.archive_name,
                        file_count=record.file_count,
                        size_bytes=record.size_bytes,
                        content_hash=record.content_hash,
                        storage_path=record.storage_path,
                        skill_md_path=record.skill_md_path,
                        prompt_text=record.prompt_text,
                        created_at=record.created_at,
                    ),
                )
            except IntegrityError as exc:
                if is_unique_violation(exc):
                    raise AttributionSkillPackageConflict from exc
                raise

    async def bound_targets(self, workspace: str, package: str) -> builtins.list[str]:
        t = evolution_targets.c
        async with self._database.session() as session:
            return list(
                (
                    await session.scalars(
                        select(t.object_name)
                        .where(t.workspace_id == workspace, t.attribution_package_id == package)
                        .order_by(t.object_name)
                    )
                ).all()
            )

    async def delete(
        self,
        workspace_id: str,
        package_id: str,
    ) -> AttributionSkillPackageRecord | None:
        """Delete a package and any active binding, returning its storage metadata."""
        record = await self.get(workspace_id, package_id)
        if record is None:
            return None
        async with self._database.transaction() as session:
            await session.execute(
                select(attribution_skill_packages.c.id)
                .where(attribution_skill_packages.c.id == package_id)
                .with_for_update()
            )
            if await session.scalar(
                select(evolution_targets.c.id)
                .where(
                    evolution_targets.c.workspace_id == workspace_id,
                    evolution_targets.c.attribution_package_id == package_id,
                )
                .limit(1)
                .with_for_update()
            ):
                raise AppError(
                    status_code=409,
                    code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_INVALID,
                    message="Skill is bound to an evolution target",
                )
            await session.execute(
                delete(attribution_skill_package_bindings).where(
                    attribution_skill_package_bindings.c.workspace_id == workspace_id,
                    attribution_skill_package_bindings.c.package_id == package_id,
                ),
            )
            await session.execute(
                delete(attribution_skill_packages).where(
                    attribution_skill_packages.c.workspace_id == workspace_id,
                    attribution_skill_packages.c.id == package_id,
                ),
            )
        return record
