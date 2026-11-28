"""Evolution target configuration validation, CRUD, and version reads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.db.crud.evolution_targets import (
    EvolutionObjectType,
    EvolutionTargetConflict,
    EvolutionTargetInUse,
    EvolutionTargetMemberConflict,
    EvolutionTargetRecord,
)
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.errors import AppError, ErrorCode
from app.service.evolution.candidate_policy import CandidatePolicy
from app.service.evolution.target_definition import TargetDefinitions
from app.service.identity.schemas import IdentityModel
from app.third_party_api.git.remote import GitRemote, RepoFailureReason, RepoInvalid
from app.utils.redaction import redact_command_output

type TargetField = Literal["objectName", "repoUrl", "subDir", "defaultRef"]
type TargetReason = (
    Literal[
        "object_name_invalid",
        "repo_url_format",
        "repo_url_credentials",
        "sub_dir_format",
        "ref_format",
    ]
    | RepoFailureReason
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+@-]{0,127}$")
_SCP_REMOTE = re.compile(
    r"^[A-Za-z0-9._-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?:"
    r"[^\s:][^\s]*$",
)


class EvolutionTargetMemberWrite(IdentityModel):
    """One skill or agent member of a target configuration."""

    object_type: EvolutionObjectType
    object_name: str
    sub_dir: str
    match_by_name: bool = False


class EvolutionTargetWrite(IdentityModel):
    """Mutable target configuration accepted by create and update."""

    repo_url: str
    default_ref: str
    validation_project_id: str = Field(max_length=128)
    test_project_id: str = Field(max_length=128)
    primary_metric_key: str = Field(max_length=128)
    attribution_package_id: str | None = Field(default=None, min_length=1, max_length=64)
    candidate_policy: CandidatePolicy | None = None
    enabled: bool = True
    members: list[EvolutionTargetMemberWrite] = Field(default_factory=list, min_length=1)
    object_type: EvolutionObjectType | None = None
    object_name: str | None = None
    sub_dir: str | None = None
    legacy_single: SkipJsonSchema[bool] = Field(default=False, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_single_object(cls, data: object) -> object:
        """Map the pre-member single-object body onto one member.

        The field-level defaults below keep an omitted project ID mapping to the
        service error instead of a Pydantic 422, as before the member model.
        """
        if not isinstance(data, dict):
            return data
        values = dict(data)
        if "validationProjectId" not in values and "validation_project_id" not in values:
            values["validationProjectId"] = ""
        if "testProjectId" not in values and "test_project_id" not in values:
            values["testProjectId"] = ""
        if "primaryMetricKey" not in values and "primary_metric_key" not in values:
            values["primaryMetricKey"] = ""
        if not values.get("members"):
            object_type = values.get("objectType", values.get("object_type"))
            object_name = values.get("objectName", values.get("object_name"))
            sub_dir = values.get("subDir", values.get("sub_dir"))
            if object_type is not None and object_name is not None and sub_dir is not None:
                values["members"] = [
                    {
                        "objectType": object_type,
                        "objectName": object_name,
                        "subDir": sub_dir,
                    },
                ]
                values["legacy_single"] = True
        elif isinstance(values.get("members"), list) and len(values["members"]) == 1:
            legacy = values["members"][0]
            if isinstance(legacy, dict):
                object_type = values.get("objectType", values.get("object_type"))
                object_name = values.get("objectName", values.get("object_name"))
                sub_dir = values.get("subDir", values.get("sub_dir"))
                if object_type is not None and object_name is not None and sub_dir is not None:
                    values["members"] = [
                        {
                            "objectType": object_type,
                            "objectName": object_name,
                            "subDir": sub_dir,
                            "matchByName": legacy.get(
                                "matchByName", legacy.get("match_by_name", False)
                            ),
                        },
                    ]
        return values


class BindingFailure(IdentityModel):
    """Last failed background analysis of the current binding."""

    attempts: int
    reason: str
    will_retry: bool


class TargetDefinitionPreview(IdentityModel):
    """Source pinned to this target binding."""

    commit: str
    path: str
    preview: str


class EvolutionTargetMember(IdentityModel):
    """Persisted member with its frozen definition preview."""

    object_type: EvolutionObjectType
    object_name: str
    sub_dir: str
    match_by_name: bool = False
    definition: TargetDefinitionPreview | None = None


class EvolutionTarget(IdentityModel):
    """Persisted target returned to clients."""

    id: str
    repo_url: str
    default_ref: str
    validation_project_id: str
    test_project_id: str
    primary_metric_key: str
    attribution_package_id: str | None = None
    attribution_skill_name: str | None = None
    attribution_failure: BindingFailure | None = None
    enabled: bool
    members: list[EvolutionTargetMember]
    candidate_policy: CandidatePolicy | None = None
    object_type: EvolutionObjectType | None = None
    object_name: str | None = None
    sub_dir: str | None = None
    definition: TargetDefinitionPreview | None = None


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


def _repo_invalid(
    field: TargetField | None = None,
    reason: TargetReason | None = None,
    *,
    command: Mapping[str, object] | None = None,
    output: str | None = None,
) -> AppError:
    """Return the stable invalid-target response with optional diagnostics.

    Field and reason values form a closed set owned by this module. Callers
    that serve administrator writes pass both so validation failures point at
    one form field; the member-readable versions endpoint passes neither and
    keeps the legacy details-free response.
    """
    details: dict[str, object] = {}
    if field is not None and reason is not None:
        details = {"field": field, "reason": reason}
        if command is not None:
            details["command"] = dict(command)
        if output:
            details["output"] = output
    return AppError(
        status_code=422,
        code=ErrorCode.REPO_INVALID,
        message="repository or ref is invalid",
        details=details,
    )


def _remote_invalid(error: RepoInvalid) -> AppError:
    """Map one classified git failure to a field-anchored diagnostic."""
    field: TargetField = "defaultRef" if error.reason == "ref_not_found" else "repoUrl"
    command: dict[str, object] = {"name": "git ls-remote"}
    if error.exit_code is not None:
        command["exitCode"] = error.exit_code
    output = redact_command_output(error.stderr) if error.stderr else ""
    return _repo_invalid(field, error.reason, command=command, output=output)


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


def _validate_primary_metric_key(value: str) -> str:
    """Trim one opaque metric key and reject blank or spaced values."""
    normalized = value.strip()
    if not normalized:
        raise AppError(
            status_code=422,
            code=ErrorCode.PRIMARY_METRIC_KEY_INVALID,
            message="primary metric key is required",
            details={"field": "primaryMetricKey", "reason": "metric_key_required"},
        )
    if (
        len(normalized) > 128
        or _CONTROL.search(normalized)
        or any(character.isspace() for character in normalized)
    ):
        raise AppError(
            status_code=422,
            code=ErrorCode.PRIMARY_METRIC_KEY_INVALID,
            message="primary metric key is invalid",
            details={"field": "primaryMetricKey", "reason": "metric_key_format"},
        )
    return normalized


def _normalize_text(
    value: str,
    *,
    field: TargetField,
    reason: TargetReason,
    maximum: int,
) -> str:
    """Trim one input and reject empty, control-bearing, or overlong text."""
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or _CONTROL.search(normalized):
        raise _repo_invalid(field, reason)
    return normalized


def _normalize_object_name(value: str) -> str:
    """Validate the human-readable skill or agent object name."""
    return _normalize_text(
        value,
        field="objectName",
        reason="object_name_invalid",
        maximum=128,
    )


def _normalize_default_ref(value: str, *, revision: bool) -> str:
    """Validate one git ref or a normalized knowledge revision.

    Knowledge targets accept normalized ``tag:`` / ``digest:`` / ``provider:``
    revisions as their ``defaultRef``. That form bypasses the git-ref regex but
    still rejects whitespace, traversal markers, and trailing separators.
    """
    normalized = _normalize_text(
        value,
        field="defaultRef",
        reason="ref_format",
        maximum=128,
    )
    if revision:
        if (
            any(character.isspace() for character in normalized)
            or ".." in normalized
            or "@{" in normalized
            or normalized.endswith((".", "/"))
        ):
            raise _repo_invalid("defaultRef", "ref_format")
    elif (
        not _REF.fullmatch(normalized)
        or ".." in normalized
        or "@{" in normalized
        or normalized.endswith((".", "/"))
    ):
        raise _repo_invalid("defaultRef", "ref_format")
    return normalized


def _validate_sub_dir(value: str) -> str:
    """Normalize a non-empty POSIX repository-relative directory."""
    normalized = _normalize_text(
        value,
        field="subDir",
        reason="sub_dir_format",
        maximum=512,
    )
    path = PurePosixPath(normalized)
    if (
        "\\" in normalized
        or path.is_absolute()
        or str(path) == "."
        or any(part == ".." for part in path.parts)
    ):
        raise _repo_invalid("subDir", "sub_dir_format")
    return normalized


def _validate_repo_url(value: str) -> str:
    """Accept credential-free HTTPS, SSH, and SCP-style git remotes."""
    normalized = _normalize_text(
        value,
        field="repoUrl",
        reason="repo_url_format",
        maximum=1024,
    )
    if any(character.isspace() for character in normalized):
        raise _repo_invalid("repoUrl", "repo_url_format")
    if _SCP_REMOTE.fullmatch(normalized):
        return normalized
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        raise _repo_invalid("repoUrl", "repo_url_format") from None
    if parsed.password is not None:
        raise _repo_invalid("repoUrl", "repo_url_credentials")
    try:
        _ = parsed.port
    except ValueError:
        raise _repo_invalid("repoUrl", "repo_url_format") from None
    if (
        parsed.scheme not in {"https", "ssh"}
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or not parsed.path.strip("/")
    ):
        raise _repo_invalid("repoUrl", "repo_url_format")
    if parsed.scheme == "https" and parsed.username is not None:
        raise _repo_invalid("repoUrl", "repo_url_credentials")
    return normalized


def _normalize_member(
    member: EvolutionTargetMemberWrite,
    *,
    index: int,
    legacy_single: bool,
) -> EvolutionTargetMemberWrite:
    """Validate one member and anchor errors to its request path.

    The pre-member single-object body keeps its top-level field names so old
    clients keep receiving the same diagnostics; member bodies always point at
    ``members[i]``.
    """
    prefix = "" if legacy_single and index == 0 else f"members[{index}]."
    if not member.object_name.strip():
        raise AppError(
            status_code=422,
            code=ErrorCode.REPO_INVALID,
            message="member object name is invalid",
            details={"field": f"{prefix}objectName", "reason": "object_name_invalid"},
        )
    try:
        return EvolutionTargetMemberWrite(
            object_type=member.object_type,
            object_name=_normalize_object_name(member.object_name),
            sub_dir=_validate_sub_dir(member.sub_dir),
            # Knowledge matches document revisions only; no member switch applies.
            match_by_name=member.match_by_name and member.object_type != "knowledge",
        )
    except AppError as error:
        field = (error.details or {}).get("field", "objectName")
        raise AppError(
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            details={**error.details, "field": f"{prefix}{field}"},
        ) from None


def _normalize_write(body: EvolutionTargetWrite) -> EvolutionTargetWrite:
    """Validate and normalize every editable target and member field."""
    members = [
        _normalize_member(
            member,
            index=index,
            legacy_single=body.legacy_single,
        )
        for index, member in enumerate(body.members)
    ]
    if not members:
        raise AppError(
            status_code=422,
            code=ErrorCode.REPO_INVALID,
            message="at least one target member is required",
            details={"field": "members", "reason": "object_name_invalid"},
        )
    seen: set[tuple[str, str]] = set()
    for index, member in enumerate(members):
        key = (member.object_type, member.object_name)
        if key in seen:
            prefix = "" if body.legacy_single and index == 0 else f"members[{index}]."
            raise AppError(
                status_code=422,
                code=ErrorCode.REPO_INVALID,
                message="member is duplicated inside the configuration",
                details={
                    "field": f"{prefix}objectName",
                    "reason": "member_duplicated",
                },
            )
        seen.add(key)
    first = members[0]
    return EvolutionTargetWrite(
        repo_url=_validate_repo_url(body.repo_url),
        default_ref=_normalize_default_ref(
            body.default_ref,
            revision=first.object_type == "knowledge",
        ),
        validation_project_id=_validate_project_id(
            body.validation_project_id,
            field="validationProjectId",
        ),
        test_project_id=_validate_project_id(
            body.test_project_id,
            field="testProjectId",
        ),
        primary_metric_key=_validate_primary_metric_key(body.primary_metric_key),
        candidate_policy=body.candidate_policy,
        enabled=body.enabled,
        attribution_package_id=body.attribution_package_id,
        members=members,
        object_type=first.object_type,
        object_name=first.object_name,
        sub_dir=first.sub_dir,
    )


def _preview(definition: Mapping[str, object] | None) -> TargetDefinitionPreview | None:
    """Map one persisted frozen definition to its public preview."""
    if not definition:
        return None
    return TargetDefinitionPreview(
        commit=str(definition["commit"]),
        path=str(definition["path"]),
        preview=str(definition["preview"]),
    )


def _public(record: EvolutionTargetRecord) -> EvolutionTarget:
    """Map one persistence row to the public model."""
    members = record.member_objects
    return EvolutionTarget(
        id=record.id,
        candidate_policy=CandidatePolicy.model_validate(record.candidate_policy or {}),
        attribution_package_id=record.attribution_package_id,
        attribution_skill_name=record.attribution_skill_name,
        definition=_preview(record.definition),
        attribution_failure=BindingFailure(
            attempts=record.attribution_failures,
            reason=record.attribution_error,
            will_retry=record.attribution_will_retry,
        )
        if record.attribution_error
        else None,
        object_type=record.object_type,
        object_name=record.object_name,
        repo_url=record.repo_url,
        sub_dir=record.sub_dir,
        default_ref=record.default_ref,
        validation_project_id=record.validation_project_id,
        test_project_id=record.test_project_id,
        primary_metric_key=record.primary_metric_key,
        enabled=record.enabled,
        members=[
            EvolutionTargetMember(
                object_type=member.object_type,
                object_name=member.object_name,
                sub_dir=member.sub_dir,
                match_by_name=member.match_by_name,
                definition=_preview(member.definition),
            )
            for member in members
        ],
    )


class EvolutionTargetService:
    """Apply validation and stable error mapping around target persistence."""

    def __init__(
        self,
        repository: EvolutionTargetStore,
        git_remote: GitRemote,
        definitions: TargetDefinitions | None = None,
        *,
        default_package_id: str | None = None,
    ) -> None:
        """Bind target storage and the sanitized git remote boundary."""
        self._repository = repository
        self._git_remote = git_remote
        self._definitions = definitions
        self._default_package_id = default_package_id

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
        await self._ensure_members_free(values, workspace_id, target_id=None)
        package = values.attribution_package_id or self._default_package_id
        values = values.model_copy(update={"attribution_package_id": package})
        write = await self._prepare_write(
            workspace_id, values, freeze_definition=package is not None
        )
        try:
            record = await self._repository.insert(
                {
                    **write,
                    "workspace_id": workspace_id,
                    "created_by": created_by,
                },
            )
        except EvolutionTargetMemberConflict:
            raise self._member_conflict() from None
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
        await self._ensure_members_free(values, target.workspace_id, target_id=target_id)
        write = await self._prepare_write(
            target.workspace_id,
            values,
            freeze_definition=bool(values.attribution_package_id or target.attribution_package_id),
        )
        try:
            record = await self._repository.update(
                target_id,
                write,
                workspace_ids=workspace_ids,
            )
        except EvolutionTargetMemberConflict:
            raise self._member_conflict() from None
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

    async def enabled_config_by_id(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord:
        """Return one enabled configuration by id for a member-list launch."""
        if workspace_ids is None:
            target = await self._repository.get(target_id)
        else:
            target = await self._repository.get(target_id, workspace_ids=workspace_ids)
        if target is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.TARGET_NOT_FOUND,
                message="target not found",
            )
        if not target.enabled:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_NOT_CONFIGURED,
                message="target is not configured or enabled",
            )
        return target

    async def _ensure_members_free(
        self,
        values: EvolutionTargetWrite,
        workspace_id: str,
        *,
        target_id: str | None,
    ) -> None:
        """Reject members already owned by another configuration in the workspace."""
        for index, member in enumerate(values.members):
            rows = await self._repository.find_all(
                member.object_type,
                member.object_name,
                workspace_ids=(workspace_id,),
            )
            for row in rows:
                if row.id != target_id:
                    raise AppError(
                        status_code=409,
                        code=ErrorCode.MEMBER_ALREADY_CONFIGURED,
                        message="member is already configured by another target",
                        details={
                            "field": f"members[{index}].objectName",
                            "member": {
                                "objectType": member.object_type,
                                "objectName": member.object_name,
                            },
                            "targetId": row.id,
                        },
                    )

    @staticmethod
    def _member_conflict() -> AppError:
        """Return the stable duplicate-member response for a raced write."""
        return AppError(
            status_code=409,
            code=ErrorCode.MEMBER_ALREADY_CONFIGURED,
            message="member is already configured by another target",
            details={"field": "members", "reason": "member_already_configured"},
        )

    async def _prepare_write(
        self, workspace: str, values: EvolutionTargetWrite, *, freeze_definition: bool
    ) -> dict[str, object]:
        await self._validate_remote(values)
        members: list[dict[str, object]] = []
        for member in values.members:
            definition = None
            if self._definitions and freeze_definition and member.object_type != "knowledge":
                definition = await self._definitions.freeze(
                    workspace,
                    member.object_type,
                    values.repo_url,
                    member.sub_dir,
                    values.default_ref,
                )
            members.append(
                {
                    "object_type": member.object_type,
                    "object_name": member.object_name,
                    "sub_dir": member.sub_dir,
                    "match_by_name": member.match_by_name,
                    "definition": definition,
                },
            )
        first = members[0]
        return {
            "repo_url": values.repo_url,
            "default_ref": values.default_ref,
            "validation_project_id": values.validation_project_id,
            "test_project_id": values.test_project_id,
            "primary_metric_key": values.primary_metric_key,
            "enabled": values.enabled,
            "attribution_package_id": values.attribution_package_id,
            "candidate_policy": values.candidate_policy.model_dump()
            if values.candidate_policy
            else None,
            "object_type": first["object_type"],
            "object_name": first["object_name"],
            "sub_dir": first["sub_dir"],
            "match_by_name": first["match_by_name"],
            "definition": first["definition"],
            "members": members,
        }

    async def _validate_remote(self, values: EvolutionTargetWrite) -> None:
        """Run network/ref validation with one sanitized failure type.

        Knowledge documents are not necessarily git objects, so the git
        ``ls-remote`` check is skipped when every member is knowledge.
        """
        if all(member.object_type == "knowledge" for member in values.members):
            return
        try:
            await self._git_remote.validate(values.repo_url, values.default_ref)
        except RepoInvalid as error:
            raise _remote_invalid(error) from None

    @staticmethod
    def _not_found() -> AppError:
        """Return the stable missing-target response."""
        return AppError(
            status_code=404,
            code=ErrorCode.TARGET_NOT_FOUND,
            message="target not found",
        )
