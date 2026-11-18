"""Workspace-credential bad-case ingest request, response, and orchestration."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.db.crud.bad_case_ingest import (
    BadCaseIdConflict,
    BadCaseIngestRepository,
    BadCaseIngestRow,
    QuotaExceeded,
    WorkspaceMissing,
)
from app.errors import AppError, ErrorCode
from app.service.workspaces.schemas import WorkspaceModel
from app.service.workspaces.service import WorkspaceCredentialAccess, WorkspaceService

logger = logging.getLogger(__name__)


class BadCaseSessionSource(BaseModel):
    """One report's optional session download contract.

    The template is a plain URL with exactly one ``{sessionId}`` placeholder.
    Credentials are deliberately absent: authorization is the template's own
    short-lived signature, and the report body can never smuggle headers.
    """

    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")

    runtime: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9-]{0,31}$",
    )
    session_url_template: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def _validate_template(self) -> "BadCaseSessionSource":
        """Require one HTTP(S) placeholder and reject embedded credentials."""
        template = self.session_url_template
        if template.count("{sessionId}") != 1:
            raise ValueError("sessionUrlTemplate must contain {sessionId} exactly once")
        parsed = urlsplit(template.replace("{sessionId}", "session"))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("sessionUrlTemplate must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("sessionUrlTemplate must not contain credentials")
        if parsed.fragment:
            raise ValueError("sessionUrlTemplate must not contain a fragment")
        return self


class BadCaseIngest(BaseModel):
    """One camelCase report accepted from a workspace ingest credential.

    Only JSON camelCase aliases are accepted: the body may never carry a
    workspace identity and snake_case input is rejected rather than silently
    accepted, so a caller cannot smuggle server-owned columns.
    """

    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")

    bad_case_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=36)
    bad_case_type: Literal["self", "discovery"]
    object_name: str = Field(min_length=1, max_length=128)
    object_type: Literal["skill", "agent"]
    object_version: str | None = Field(default=None, max_length=64)
    bad_case_agent_id: str | None = Field(default=None, max_length=64)
    trigger_line: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Optional 1-based log line where the report sits in the root Session, using "
            "the same coordinate as the Session tree event line; "
            "absent means the trigger point is unknown."
        ),
    )
    title: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1)
    meta_data: dict[str, Any] | None = None
    source: str | None = Field(default=None, max_length=64)
    session_source: BadCaseSessionSource | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _require_offset(cls, value: datetime) -> datetime:
        """Reject naive timestamps instead of silently reading them as +08:00."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("createdAt must carry a UTC offset, for example +08:00")
        return value


class BadCaseIngestResponse(WorkspaceModel):
    """Stable success payload shared by the 201 insert and 200 upsert paths."""

    bad_case_id: str
    workspace_used: int


@dataclass(frozen=True, slots=True)
class BadCaseIngestOutcome:
    """Response payload plus the HTTP status decision it implies."""

    response: BadCaseIngestResponse
    created: bool


class BadCaseIngestService:
    """Resolve the ingest credential scope and run the quota-checked write."""

    def __init__(
        self,
        repository: BadCaseIngestRepository,
        workspaces: WorkspaceService,
    ) -> None:
        """Bind ingest writes to their transaction and credential boundary."""
        self._repository = repository
        self._workspaces = workspaces

    async def authorize(
        self,
        workspace_id: str,
        credential: str | None,
    ) -> WorkspaceCredentialAccess:
        """Resolve one bearer credential and bind it to the path workspace.

        A missing, unknown, or revoked credential answers 401 before the path is
        inspected, so an unauthenticated caller cannot probe workspace ids. Once
        the credential is valid, a mismatch with an existing workspace answers
        403, while a path that names no workspace answers 404.
        """
        access = await self._workspaces.verify_credential(credential)
        if access.workspace_id != workspace_id:
            if not await self._repository.workspace_exists(workspace_id):
                raise self._not_found()
            raise self._forbidden()
        return access

    async def ingest(
        self,
        access: WorkspaceCredentialAccess,
        body: BadCaseIngest,
    ) -> BadCaseIngestOutcome:
        """Write one report and report the live workspace usage."""
        try:
            write = await self._repository.ingest(access.workspace_id, self._row(body))
        except WorkspaceMissing as exc:
            raise self._not_found() from exc
        except BadCaseIdConflict as exc:
            raise AppError(
                status_code=409,
                code=ErrorCode.BAD_CASE_ID_CONFLICT,
                message="badCaseId belongs to another workspace",
                details={"badCaseId": body.bad_case_id},
            ) from exc
        except QuotaExceeded as exc:
            raise AppError(
                status_code=409,
                code=ErrorCode.QUOTA_EXCEEDED,
                message="workspace bad case quota is exhausted",
                details={"quota": exc.quota, "used": exc.used},
            ) from exc
        await self._workspaces.touch_credential(access.credential_id)
        return BadCaseIngestOutcome(
            response=BadCaseIngestResponse(
                bad_case_id=write.bad_case_id,
                workspace_used=write.workspace_used,
            ),
            created=write.created,
        )

    @staticmethod
    def _row(body: BadCaseIngest) -> BadCaseIngestRow:
        """Map the public camelCase report onto the persistence row."""
        return BadCaseIngestRow(
            bad_case_id=body.bad_case_id,
            session_id=body.session_id,
            bad_case_type=body.bad_case_type,
            object_name=body.object_name,
            object_type=body.object_type,
            object_version=body.object_version,
            bad_case_agent_id=body.bad_case_agent_id,
            trigger_line=body.trigger_line,
            title=body.title,
            reason=body.reason,
            meta_data=body.meta_data,
            source=body.source,
            session_source=(
                body.session_source.model_dump(by_alias=True)
                if body.session_source is not None
                else None
            ),
            created_at=body.created_at,
        )

    @staticmethod
    def _not_found() -> AppError:
        """Return the uniform missing-workspace failure."""
        return AppError(
            status_code=404,
            code=ErrorCode.WORKSPACE_NOT_FOUND,
            message="workspace was not found",
        )

    @staticmethod
    def _forbidden() -> AppError:
        """Return the credential-to-path mismatch failure."""
        return AppError(
            status_code=403,
            code=ErrorCode.WORKSPACE_FORBIDDEN,
            message="workspace credential does not belong to this workspace",
        )
