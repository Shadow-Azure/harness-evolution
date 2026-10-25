"""Authenticated request context types."""

from dataclasses import dataclass

from app.errors import AppError, ErrorCode


@dataclass(frozen=True, slots=True)
class Principal:
    """Verified identity claims attached to an API request."""

    user_id: str
    role: str
    must_change_password: bool


def principal_from_claims(claims: dict[str, object]) -> Principal:
    """Convert verified JWT claims into a principal or a stable auth failure."""
    user_id = claims.get("sub")
    role = claims.get("role")
    must_change_password = claims.get("mcp")
    if (
        not isinstance(user_id, str)
        or not isinstance(role, str)
        or not isinstance(must_change_password, bool)
    ):
        raise AppError(
            status_code=401,
            code=ErrorCode.AUTH_REQUIRED,
            message="access token is invalid",
        )
    return Principal(
        user_id=user_id,
        role=role,
        must_change_password=must_change_password,
    )
