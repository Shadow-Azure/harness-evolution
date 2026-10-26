"""Member-readable evolution target and normalized model catalogs."""

import asyncio

from app.db.crud.evolution_targets import (
    EvolutionTargetRecord,
    EvolutionTargetRepository,
)
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import IdentityModel
from app.third_party_api.git.remote import GitRemote, RepoInvalid


class CatalogTarget(IdentityModel):
    """One enabled evolution target and its remote versions."""

    id: str
    name: str
    repo_url: str
    sub_dir: str
    default_ref: str
    versions: list[str]


class CatalogTargets(IdentityModel):
    """Enabled targets grouped by the kind selectable in the wizard."""

    skill: list[CatalogTarget]
    agent: list[CatalogTarget]


class CatalogModel(IdentityModel):
    """One normalized model and its usage across the trace corpus."""

    model: str
    session_count: int
    agent_count: int


class CatalogModels(IdentityModel):
    """The complete model catalog."""

    items: list[CatalogModel]


class CatalogService:
    """Compose catalog reads from target configuration and normalized tables."""

    def __init__(
        self,
        repository: EvolutionTargetRepository,
        git_remote: GitRemote,
    ) -> None:
        """Bind the catalog to its configuration store and remote tag reader."""
        self._repository = repository
        self._git_remote = git_remote

    async def targets(self) -> CatalogTargets:
        """Return enabled targets grouped by object type with remote tags."""
        rows = await self._repository.list(enabled_only=True)
        versions = await asyncio.gather(
            *(self._versions(row.repo_url) for row in rows),
        )
        grouped: dict[str, list[CatalogTarget]] = {"skill": [], "agent": []}
        for row, tags in zip(rows, versions, strict=True):
            grouped[row.object_type].append(_catalog_target(row, tags))
        return CatalogTargets(skill=grouped["skill"], agent=grouped["agent"])

    async def models(self) -> CatalogModels:
        """Return normalized model counts without parsing trace payloads."""
        rows = await self._repository.list_models()
        return CatalogModels(
            items=[
                CatalogModel(
                    model=row.model,
                    session_count=row.session_count,
                    agent_count=row.agent_count,
                )
                for row in rows
            ],
        )

    async def _versions(self, repo_url: str) -> list[str]:
        """Resolve sorted unique tags through the sanitized remote boundary."""
        try:
            tags = await self._git_remote.list_tags(repo_url)
        except RepoInvalid:
            raise AppError(
                status_code=422,
                code=ErrorCode.REPO_INVALID,
                message="repository or ref is invalid",
            ) from None
        return sorted(set(tags))


def _catalog_target(
    row: EvolutionTargetRecord,
    versions: list[str],
) -> CatalogTarget:
    """Map one enabled persistence record to the public catalog item."""
    return CatalogTarget(
        id=row.id,
        name=row.object_name,
        repo_url=row.repo_url,
        sub_dir=row.sub_dir,
        default_ref=row.default_ref,
        versions=versions,
    )
