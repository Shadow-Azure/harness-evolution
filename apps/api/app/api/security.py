"""OpenAPI security declarations for bearer-authenticated operations."""

from fastapi.security import HTTPBearer

BEARER_AUTH = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Short-lived access JWT returned by POST /api/auth/login.",
)
