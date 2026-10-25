"""HTTP adapters for authentication and current-user endpoints."""

from typing import cast

from fastapi import APIRouter, Request, Response, Security, status

from app.api.security import BEARER_AUTH
from app.config import Settings
from app.db.models.users import UserRecord
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    PublicUser,
    RefreshResponse,
)
from app.service.identity.service import IdentityService

REFRESH_COOKIE = "refresh_token"
router = APIRouter(prefix="/api/auth", tags=["auth"])


def identity_from(request: Request) -> IdentityService:
    """Return the application-scoped identity service."""
    return cast(IdentityService, request.app.state.identity)


def public_user(record: UserRecord) -> PublicUser:
    """Convert an internal user record while retaining the public field set."""
    return PublicUser.model_validate(record.public_fields)


def set_refresh_cookie(response: Response, request: Request, token: str) -> None:
    """Apply the restricted refresh cookie contract."""
    settings: Settings = request.app.state.settings
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_ttl_seconds,
        secure=settings.is_production,
        httponly=True,
        samesite="strict",
        path="/api/auth",
    )


@router.post(
    "/login",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid username or password"},
        403: {"model": ErrorResponse, "description": "Account is inactive"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
        429: {"model": ErrorResponse, "description": "Too many login attempts"},
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Exchange a username and password for a short-lived access token."""
    authenticated = await identity_from(request).login(
        username=body.username.lower(),
        password=body.password,
    )
    set_refresh_cookie(response, request, authenticated.refresh_token)
    return LoginResponse(
        access_token=authenticated.access_token,
        expires_in=request.app.state.settings.access_ttl_seconds,
        user=public_user(authenticated.user),
    )


@router.post(
    "/refresh",
    responses={
        401: {"model": ErrorResponse, "description": "Refresh token is invalid or expired"},
        403: {"model": ErrorResponse, "description": "Account is inactive"},
    },
)
async def refresh(request: Request, response: Response) -> RefreshResponse:
    """Rotate the refresh cookie and issue a fresh bearer access token."""
    authenticated = await identity_from(request).refresh(request.cookies.get(REFRESH_COOKIE))
    set_refresh_cookie(response, request, authenticated.refresh_token)
    return RefreshResponse(
        access_token=authenticated.access_token,
        expires_in=request.app.state.settings.access_ttl_seconds,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses={401: {"model": ErrorResponse, "description": "Authentication is required"}},
)
async def logout(request: Request, response: Response) -> Response:
    """Revoke the presented refresh token and clear its restricted cookie."""
    await identity_from(request).logout(request.cookies.get(REFRESH_COOKIE))
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/auth",
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.is_production,
    )
    return response


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
) -> Response:
    """Replace the authenticated user's password and clear forced-change state."""
    principal = request.state.principal
    await identity_from(request).change_password(
        user_id=principal.user_id,
        old_password=body.old_password,
        new_password=body.new_password,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    dependencies=[Security(BEARER_AUTH)],
    responses={401: {"model": ErrorResponse, "description": "Authentication is required"}},
)
async def me(request: Request) -> PublicUser:
    """Return the current identity with its forced-change state."""
    principal = request.state.principal
    user = await identity_from(request).get_user(principal.user_id)
    if user is None:
        raise AppError(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="authentication is required",
        )
    return public_user(user)
