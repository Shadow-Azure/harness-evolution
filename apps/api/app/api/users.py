"""Administrator HTTP adapter for the user directory."""

from fastapi import APIRouter, Request, Security, status

from app.api.auth import identity_from, public_user
from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.identity.schemas import CreateUserRequest, PublicUser, UserListResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Administrator role is required"},
    },
)
async def list_users(request: Request) -> UserListResponse:
    """List all users in the single organization."""
    records = await identity_from(request).list_users()
    return UserListResponse(items=[public_user(record) for record in records])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Administrator role is required"},
        409: {"model": ErrorResponse, "description": "Username already exists"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def create_user(body: CreateUserRequest, request: Request) -> PublicUser:
    """Provision a user whose first login must change its temporary password."""
    created = await identity_from(request).create_user(
        username=body.username.lower(),
        display_name=body.display_name,
        password=body.password,
        role=body.role,
    )
    return public_user(created)
