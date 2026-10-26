"""Evolution target configuration validation, CRUD, and version reads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import Field

from app.db.crud.evolution_targets import (
    EvolutionTargetConflict,
    EvolutionTargetInUse,
    EvolutionTargetRecord,
)
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import IdentityModel
from app.third_party_api.git.remote import GitRemote, RepoInvalid

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+@-]{0,127}$")
_SCP_REMOTE = re.compile(
    r"^[A-Za-z0-9._-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?:"
    r"[^\s:][^\s]*$",
)


class EvolutionTargetWrite(IdentityModel):
    """Mutable target configuration accepted by create and update."""

    object_type: Literal["skill", "agent"]
    object_name: str = Field(max_length=128)
    repo_url: str = Field(max_length=1024)
    sub_dir: str = Field(max_length=512)
    default_ref: str = Field(max_length=128)
    enabled: bool = True


class EvolutionTarget(EvolutionTargetWrite):
    """Persisted target returned to clients."""

    id: str


class EvolutionTargetList(IdentityModel):
    """Complete target configuration collection."""

    items: list[EvolutionTarget]


class EvolutionTargetVersions(IdentityModel):
    """Remote tags and the persisted default reference."""

    versions: list[str]
    default_ref: str


class EvolutionTargetStore(Protocol):
    """Persistence operations consumed by the target service."""

    async def list(self, *, enabled_only: bool = False) -> tuple[EvolutionTargetRecord, ...]:
        """Return configured targets."""

    async def get(self, target_id: str) -> EvolutionTargetRecord | None:
        """Return one target."""

    async def find(
        self,
        object_type: str,
        object_name: str,
    ) -> EvolutionTargetRecord | None:
        """Return one object pair."""

    async def insert(self, values: Mapping[str, object]) -> EvolutionTargetRecord:
        """Insert one target."""

    async def update(
        self,
        target_id: str,
        values: Mapping[str, object],
    ) -> EvolutionTargetRecord:
        """Update one target."""

    async def delete(self, target_id: str) -> bool:
        """Delete one target."""

    async def has_active_runs(self, target_id: str) -> bool:
        """Return whether a target has a non-terminal run."""


def _repo_invalid() -> AppError:
    """Return the one sanitized invalid-target response."""
    return AppError(
        status_code=422,
        code=ErrorCode.REPO_INVALID,
        message="repository or ref is invalid",
    )


def _normalize_text(value: str, *, field: str, maximum: int) -> str:
    """Trim one input and reject empty, control-bearing, or overlong text."""
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or _CONTROL.search(normalized):
        raise _repo_invalid()
    if field == "default_ref" and (
        not _REF.fullmatch(normalized)
        or ".." in normalized
        or "@{" in normalized
        or normalized.endswith((".", "/"))
    ):
        raise _repo_invalid()
    return normalized


def _validate_sub_dir(value: str) -> str:
    """Normalize a non-empty POSIX repository-relative directory."""
    normalized = _normalize_text(value, field="sub_dir", maximum=512)
    path = PurePosixPath(normalized)
    if (
        "\\" in normalized
        or path.is_absolute()
        or str(path) == "."
        or any(part == ".." for part in path.parts)
    ):
        raise _repo_invalid()
    return normalized


def _validate_repo_url(value: str) -> str:
    """Accept credential-free HTTPS, SSH, and SCP-style git remotes."""
    normalized = _normalize_text(value, field="repo_url", maximum=1024)
    if any(character.isspace() for character in normalized):
        raise _repo_invalid()
    if _SCP_REMOTE.fullmatch(normalized):
        return normalized
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        raise _repo_invalid() from None
    if (
        parsed.scheme not in {"https", "ssh"}
        or not hostname
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.strip("/")
    ):
        raise _repo_invalid()
    if parsed.scheme == "https" and parsed.username is not None:
        raise _repo_invalid()
    return normalized


def _normalize_write(body: EvolutionTargetWrite) -> EvolutionTargetWrite:
    """Validate and normalize every editable target field."""
    return EvolutionTargetWrite(
        object_type=body.object_type,
        object_name=_normalize_text(
            body.object_name,
            field="object_name",
            maximum=128,
        ),
        repo_url=_validate_repo_url(body.repo_url),
        sub_dir=_validate_sub_dir(body.sub_dir),
        default_ref=_normalize_text(
            body.default_ref,
            field="default_ref",
            maximum=128,
        ),
        enabled=body.enabled,
    )


def _public(record: EvolutionTargetRecord) -> EvolutionTarget:
    """Map one persistence row to the public model."""
    return EvolutionTarget(
        id=record.id,
        object_type=record.object_type,
        object_name=record.object_name,
        repo_url=record.repo_url,
        sub_dir=record.sub_dir,
        default_ref=record.default_ref,
        enabled=record.enabled,
    )


class EvolutionTargetService:
    """Apply validation and stable error mapping around target persistence."""

    def __init__(self, repository: EvolutionTargetStore, git_remote: GitRemote) -> None:
        """Bind target storage and the sanitized git remote boundary."""
        self._repository = repository
        self._git_remote = git_remote

    async def list(self) -> EvolutionTargetList:
        """Return all configured targets, including disabled rows."""
        rows = await self._repository.list()
        return EvolutionTargetList(items=[_public(row) for row in rows])

    async def create(
        self,
        body: EvolutionTargetWrite,
        *,
        created_by: str | None,
    ) -> EvolutionTarget:
        """Validate and create one target."""
        values = _normalize_write(body)
        if await self._repository.find(values.object_type, values.object_name):
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            )
        await self._validate_remote(values)
        try:
            record = await self._repository.insert(
                {**values.model_dump(), "created_by": created_by},
            )
        except EvolutionTargetConflict:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            ) from None
        return _public(record)

    async def update(
        self,
        target_id: str,
        body: EvolutionTargetWrite,
    ) -> EvolutionTarget:
        """Validate and replace one existing target."""
        if await self._repository.get(target_id) is None:
            raise self._not_found()
        values = _normalize_write(body)
        existing = await self._repository.find(values.object_type, values.object_name)
        if existing is not None and existing.id != target_id:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            )
        await self._validate_remote(values)
        try:
            record = await self._repository.update(target_id, values.model_dump())
        except EvolutionTargetConflict:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            ) from None
        except LookupError:
            raise self._not_found() from None
        return _public(record)

    async def delete(self, target_id: str) -> None:
        """Delete one unused target."""
        try:
            deleted = await self._repository.delete(target_id)
        except EvolutionTargetInUse:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_IN_USE,
                message="target has an active run",
            ) from None
        if not deleted:
            raise self._not_found()

    async def versions(self, target_id: str) -> EvolutionTargetVersions:
        """Return sorted remote tags and the configured default reference."""
        target = await self._repository.get(target_id)
        if target is None:
            raise self._not_found()
        try:
            versions = await self._git_remote.list_tags(target.repo_url)
        except RepoInvalid:
            raise _repo_invalid() from None
        return EvolutionTargetVersions(
            versions=sorted(set(versions)),
            default_ref=target.default_ref,
        )

    async def _validate_remote(self, values: EvolutionTargetWrite) -> None:
        """Run network/ref validation with one sanitized failure type."""
        try:
            await self._git_remote.validate(values.repo_url, values.default_ref)
        except RepoInvalid:
            raise _repo_invalid() from None

    @staticmethod
    def _not_found() -> AppError:
        """Return the stable missing-target response."""
        return AppError(
            status_code=404,
            code=ErrorCode.TARGET_NOT_FOUND,
            message="target not found",
        )
