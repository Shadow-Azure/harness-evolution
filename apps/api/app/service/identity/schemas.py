"""Public request and response contracts for identity APIs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class IdentityModel(BaseModel):
    """Base contract model using the shared camelCase JSON convention."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class LoginRequest(IdentityModel):
    """Credentials exchanged for a bearer token and refresh cookie."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PublicUser(IdentityModel):
    """User fields safe for browser and API clients."""

    id: str
    username: str
    display_name: str
    role: Literal["admin", "member"]
    must_change_password: bool


class LoginResponse(IdentityModel):
    """Successful authentication result."""

    access_token: str
    expires_in: int
    user: PublicUser


class RefreshResponse(IdentityModel):
    """Successful refresh result; callers reload `/api/auth/me` for user fields."""

    access_token: str
    expires_in: int


class ChangePasswordRequest(IdentityModel):
    """Owner-supplied current and replacement passwords."""

    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class CreateUserRequest(IdentityModel):
    """Administrator-provisioned account with a temporary password."""

    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "member"] = "member"


class UserListResponse(IdentityModel):
    """Small unpaginated administrator user list."""

    items: list[PublicUser]


class TicketRequest(IdentityModel):
    """Run topics and optional replay cursor bound to an event ticket."""

    topics: list[str] = Field(min_length=1, max_length=1)
    last_event_id: int = Field(default=0, ge=0)


class EventTicketResponse(IdentityModel):
    """Opaque single-use grant for one SSE connection."""

    ticket: str
    expires_in: int
    topics: list[str]
