"""Workspace role vocabulary and ordering shared by authorization paths."""

from typing import Literal, cast

WorkspaceRole = Literal["global_admin", "space_admin", "member", "viewer"]
"""Effective role of the current user inside one workspace."""

WorkspaceMemberRole = Literal["viewer", "member", "space_admin"]
"""Role stored on a membership row; global admins are never stored."""

WORKSPACE_ROLE_RANK: dict[str, int] = {
    "viewer": 1,
    "member": 2,
    "space_admin": 3,
}

_WORKSPACE_ROLES: tuple[str, ...] = (
    "global_admin",
    "space_admin",
    "member",
    "viewer",
)


def role_at_least(role: str, minimum: WorkspaceMemberRole) -> bool:
    """Return whether a stored member role satisfies the minimum requirement."""
    rank = WORKSPACE_ROLE_RANK.get(role)
    if rank is None:
        return False
    return rank >= WORKSPACE_ROLE_RANK[minimum]


def effective_role(role: str) -> WorkspaceRole:
    """Validate and narrow one stored or derived role to the public union."""
    if role not in _WORKSPACE_ROLES:
        raise RuntimeError(f"workspace role {role!r} is not part of the contract")
    return cast(WorkspaceRole, role)
