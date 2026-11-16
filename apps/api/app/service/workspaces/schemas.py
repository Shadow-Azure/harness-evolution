"""Public auth/session and workspace management contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.service.identity.schemas import PublicUser
from app.service.workspaces.roles import WorkspaceMemberRole, WorkspaceRole


class WorkspaceModel(BaseModel):
    """Base contract model using the shared camelCase JSON convention."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SessionWorkspace(WorkspaceModel):
    """One workspace visible to the current user with its live aggregates."""

    id: str
    name: str
    mark: str
    role: WorkspaceRole
    quota: int
    used: int
    member_count: int
    space_admin_count: int


class SessionPayload(WorkspaceModel):
    """Current user plus every workspace they can see for this session."""

    user: PublicUser
    workspaces: list[SessionWorkspace]
    truncated: bool


class WorkspaceAdmin(WorkspaceModel):
    """Minimal identity of one workspace administrator on a workspace card."""

    id: str
    display_name: str


class Workspace(WorkspaceModel):
    """Full workspace returned by the management API."""

    id: str
    name: str
    mark: str
    quota: int
    used: int
    member_count: int
    space_admins: list[WorkspaceAdmin]
    knowledge_roots: list[str]
    created_at: datetime


class WorkspaceListResponse(WorkspaceModel):
    """Every workspace visible to the current user, newest first."""

    items: list[Workspace]


class WorkspaceCreateRequest(WorkspaceModel):
    """Administrator-provisioned workspace with at least one initial space admin."""

    name: str = Field(min_length=1, max_length=128)
    mark: str = Field(default="", max_length=255)
    quota: int
    space_admin_ids: list[str]
    knowledge_roots: list[str] = Field(default_factory=list)


class WorkspaceUpdateRequest(WorkspaceModel):
    """Partial workspace update; field-level permission is enforced by the service."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    mark: str | None = Field(default=None, max_length=255)
    quota: int | None = None
    knowledge_roots: list[str] | None = None


class WorkspaceMember(WorkspaceModel):
    """One membership row with the joined user's public identity."""

    workspace_id: str
    user_id: str
    username: str
    display_name: str
    role: WorkspaceMemberRole
    joined_at: datetime
    updated_at: datetime


class WorkspaceMemberListResponse(WorkspaceModel):
    """Members of one workspace ordered by role and join time."""

    items: list[WorkspaceMember]


class WorkspaceMemberCandidate(WorkspaceModel):
    """One non-member user returned by the server-side candidate search."""

    id: str
    username: str
    display_name: str
    active: bool


class WorkspaceMemberCandidateListResponse(WorkspaceModel):
    """Bounded candidate page that never exposes the global user directory."""

    items: list[WorkspaceMemberCandidate]


class WorkspaceMemberCreateRequest(WorkspaceModel):
    """Add one existing user to a workspace at an allowed role."""

    user_id: str = Field(min_length=1, max_length=36)
    role: WorkspaceMemberRole


class WorkspaceMemberUpdateRequest(WorkspaceModel):
    """Change one existing membership's role."""

    role: WorkspaceMemberRole


class WorkspaceCredential(WorkspaceModel):
    """One ingest credential without its one-time plaintext secret."""

    id: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class WorkspaceCredentialListResponse(WorkspaceModel):
    """Every credential row owned by one workspace, newest first."""

    items: list[WorkspaceCredential]


class WorkspaceCredentialCreated(WorkspaceModel):
    """One-time credential creation response; the plaintext is never persisted."""

    credential_id: str
    prefix: str
    credential: str
