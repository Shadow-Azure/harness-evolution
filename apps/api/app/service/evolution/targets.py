"""Evolution target configuration validation, CRUD, and version reads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from app.db.crud.evolution_targets import (
    EvolutionObjectType,
    EvolutionTargetConflict,
    EvolutionTargetInUse,
    EvolutionTargetRecord,
)
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
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

    object_type: EvolutionObjectType
    object_name: str = Field(max_length=128)
    repo_url: str = Field(max_length=1024)
    sub_dir: str = Field(max_length=512)
    default_ref: str = Field(max_length=128)
    validation_project_id: str = Field(max_length=128)
    test_project_id: str = Field(max_length=128)
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def _default_missing_project_ids(cls, data: object) -> object:
        """Keep the schema required while mapping an omitted ID to the service error."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        if "validationProjectId" not in values and "validation_project_id" not in values:
            values["validationProjectId"] = ""
        if "testProjectId" not in values and "test_project_id" not in values:
            values["testProjectId"] = ""
        return values


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

    async def list(
        self,
        *,
        enabled_only: bool = False,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionTargetRecord, ...]:
        """Return configured targets inside the optional workspace scope."""

    async def get(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord | None:
        """Return one target inside the optional workspace scope."""

    async def find(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord | None:
        """Return one object pair inside the optional workspace scope."""

    async def find_all(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionTargetRecord, ...]:
        """Return every matching object pair inside the optional workspace scope."""

    async def insert(self, values: Mapping[str, object]) -> EvolutionTargetRecord:
        """Insert one target."""

    async def update(
        self,
        target_id: str,
        values: Mapping[str, object],
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord:
        """Update one target inside the optional workspace scope."""

    async def delete(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> bool:
        """Delete one target inside the optional workspace scope."""

    async def has_active_runs(self, target_id: str) -> bool:
        """Return whether a target has a non-terminal run."""


def _repo_invalid() -> AppError:
    """Return the one sanitized invalid-target response."""
    return AppError(
        status_code=422,
        code=ErrorCode.REPO_INVALID,
        message="repository or ref is invalid",
    )


def _project_id_invalid(field: str, reason: str) -> AppError:
    """Return the field-level response for an invalid test project ID."""
    return AppError(
        status_code=422,
        code=ErrorCode.PROJECT_ID_INVALID,
        message="test project id is invalid",
        details={"field": field, "reason": reason},
    )


def _validate_project_id(value: str, *, field: str) -> str:
    """Trim one opaque test project ID and reject blank or spaced values."""
    normalized = value.strip()
    if not normalized:
        raise _project_id_invalid(field, "project_id_required")
    if (
        len(normalized) > 128
        or _CONTROL.search(normalized)
        or any(character.isspace() for character in normalized)
    ):
        raise _project_id_invalid(field, "project_id_format")
    return normalized


def _normalize_text(
    value: str,
    *,
    field: str,
    maximum: int,
    revision: bool = False,
) -> str:
    """Trim one input and reject empty, control-bearing, or overlong text.

    Knowledge targets accept normalized ``tag:`` / ``digest:`` / ``provider:``
    revisions as their ``defaultRef``. That form bypasses the git-ref regex but
    still rejects whitespace, traversal markers, and trailing separators.
    """
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or _CONTROL.search(normalized):
        raise _repo_invalid()
    if field == "default_ref":
        if revision:
            if (
                any(character.isspace() for character in normalized)
                or ".." in normalized
                or "@{" in normalized
                or normalized.endswith((".", "/"))
            ):
                raise _repo_invalid()
        elif (
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
            revision=body.object_type == "knowledge",
        ),
        validation_project_id=_validate_project_id(
            body.validation_project_id,
            field="validationProjectId",
        ),
        test_project_id=_validate_project_id(
            body.test_project_id,
            field="testProjectId",
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
        validation_project_id=record.validation_project_id,
        test_project_id=record.test_project_id,
        enabled=record.enabled,
    )


class EvolutionTargetService:
    """Apply validation and stable error mapping around target persistence."""

    def __init__(self, repository: EvolutionTargetStore, git_remote: GitRemote) -> None:
        """Bind target storage and the sanitized git remote boundary."""
        self._repository = repository
        self._git_remote = git_remote

    async def list(
        self,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetList:
        """Return configured targets in one optional workspace scope."""
        if workspace_ids is None:
            rows = await self._repository.list()
        else:
            rows = await self._repository.list(workspace_ids=workspace_ids)
        return EvolutionTargetList(items=[_public(row) for row in rows])

    async def create(
        self,
        body: EvolutionTargetWrite,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        created_by: str | None,
    ) -> EvolutionTarget:
        """Validate and create one target inside the requested workspace."""
        values = _normalize_write(body)
        if await self._repository.find(
            values.object_type,
            values.object_name,
            workspace_ids=(workspace_id,),
        ):
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            )
        await self._validate_remote(values)
        try:
            record = await self._repository.insert(
                {
                    **values.model_dump(),
                    "workspace_id": workspace_id,
                    "created_by": created_by,
                },
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
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTarget:
        """Validate and replace one target inside the optional workspace scope."""
        if workspace_ids is None:
            target = await self._repository.get(target_id)
        else:
            target = await self._repository.get(target_id, workspace_ids=workspace_ids)
        if target is None:
            raise self._not_found()
        values = _normalize_write(body)
        existing = await self._repository.find(
            values.object_type,
            values.object_name,
            workspace_ids=(target.workspace_id,),
        )
        if existing is not None and existing.id != target_id:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            )
        await self._validate_remote(values)
        try:
            record = await self._repository.update(
                target_id,
                values.model_dump(),
                workspace_ids=workspace_ids,
            )
        except EvolutionTargetConflict:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_EXISTS,
                message="target already exists",
            ) from None
        except LookupError:
            raise self._not_found() from None
        return _public(record)

    async def delete(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> None:
        """Delete one unused target inside the optional workspace scope."""
        try:
            deleted = await self._repository.delete(
                target_id,
                workspace_ids=workspace_ids,
            )
        except EvolutionTargetInUse:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_IN_USE,
                message="target has an active run",
            ) from None
        if not deleted:
            raise self._not_found()

    async def versions(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetVersions:
        """Return sorted remote tags and the configured default reference.

        Knowledge targets are document/Provider identities rather than git
        objects, so they return no tag list and keep their configured revision.
        """
        if workspace_ids is None:
            target = await self._repository.get(target_id)
        else:
            target = await self._repository.get(target_id, workspace_ids=workspace_ids)
        if target is None:
            raise self._not_found()
        if target.object_type == "knowledge":
            return EvolutionTargetVersions(versions=[], default_ref=target.default_ref)
        try:
            versions = await self._git_remote.list_tags(target.repo_url)
        except RepoInvalid:
            raise _repo_invalid() from None
        return EvolutionTargetVersions(
            versions=sorted(set(versions)),
            default_ref=target.default_ref,
        )

    async def enabled_config(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord:
        """Return the one enabled configuration for a launch condition.

        Raises:
            AppError: With ``TARGET_NOT_CONFIGURED`` when the pair is missing,
                disabled, or ambiguous across the requested workspaces.
        """
        rows = await self._repository.find_all(
            object_type,
            object_name,
            workspace_ids=workspace_ids,
        )
        enabled = [row for row in rows if row.enabled]
        if not enabled:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_NOT_CONFIGURED,
                message="target is not configured or enabled",
            )
        if len(enabled) > 1:
            default = next(
                (row for row in enabled if row.workspace_id == DEFAULT_WORKSPACE_ID),
                None,
            )
            if default is None:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.TARGET_NOT_CONFIGURED,
                    message="target name is ambiguous across workspaces",
                    details={
                        "workspaces": sorted({row.workspace_id for row in enabled}),
                    },
                )
            return default
        return enabled[0]

    async def _validate_remote(self, values: EvolutionTargetWrite) -> None:
        """Run network/ref validation with one sanitized failure type.

        Knowledge documents are not necessarily git objects, so the git
        ``ls-remote`` check is skipped for that object type.
        """
        if values.object_type == "knowledge":
            return
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
