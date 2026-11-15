"""Public auth/session aggregation contracts."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.service.identity.schemas import PublicUser
from app.service.workspaces.roles import WorkspaceRole


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
