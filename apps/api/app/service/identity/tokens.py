"""Signed access and refresh token services."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.utils.ids import new_id


@dataclass(frozen=True, slots=True)
class RefreshGrant:
    """Verified refresh-token claims used only by authentication endpoints."""

    user_id: str
    jti: str
    expires_at: datetime


class TokenService:
    """Create and verify short-lived access and rotating refresh tokens."""

    def __init__(self, settings: Settings) -> None:
        """Keep the configured signing key outside application response paths."""
        self._settings = settings

    @property
    def secret(self) -> str:
        """Return the process-local signing secret."""
        return self._settings.jwt_secret.get_secret_value()

    def create_access_token(
        self,
        *,
        user_id: str,
        role: str,
        must_change_password: bool,
        expires_in: int | None = None,
    ) -> str:
        """Sign a bearer access token with the forced-password-change claim."""
        now = datetime.now(UTC)
        lifetime = self._settings.access_ttl_seconds if expires_in is None else expires_in
        return self._encode(
            {
                "sub": user_id,
                "role": role,
                "mcp": must_change_password,
                "typ": "access",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(seconds=lifetime)).timestamp()),
            }
        )

    def create_refresh_token(self, *, user_id: str, expires_in: int | None = None) -> str:
        """Sign a rotating refresh token carrying a unique revocation id."""
        now = datetime.now(UTC)
        lifetime = self._settings.refresh_ttl_seconds if expires_in is None else expires_in
        return self._encode(
            {
                "sub": user_id,
                "typ": "refresh",
                "jti": new_id(),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(seconds=lifetime)).timestamp()),
            }
        )

    def decode_access_token(self, token: str) -> dict[str, Any]:
        """Verify an access token and translate expected JWT failures to API codes."""
        try:
            claims = self._decode(token)
        except jwt.ExpiredSignatureError as exc:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_EXPIRED,
                message="access token has expired",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_REQUIRED,
                message="access token is invalid",
            ) from exc
        if claims.get("typ") != "access":
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_REQUIRED,
                message="access token is invalid",
            )
        return claims

    def decode_refresh_token(self, token: str) -> RefreshGrant:
        """Verify a refresh token and return only its stable identity claims."""
        try:
            claims = self._decode(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as exc:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_EXPIRED,
                message="refresh token has expired or is invalid",
            ) from exc
        subject = claims.get("sub")
        token_id = claims.get("jti")
        expires_at = claims.get("exp")
        if (
            claims.get("typ") != "refresh"
            or not isinstance(subject, str)
            or not isinstance(token_id, str)
            or not isinstance(expires_at, int)
        ):
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_EXPIRED,
                message="refresh token has expired or is invalid",
            )
        return RefreshGrant(
            user_id=subject,
            jti=token_id,
            expires_at=datetime.fromtimestamp(expires_at, UTC),
        )

    def _encode(self, claims: dict[str, Any]) -> str:
        """Encode one token with an explicit algorithm allowlist."""
        return jwt.encode(claims, self.secret, algorithm="HS256")

    def _decode(self, token: str) -> dict[str, Any]:
        """Decode and verify one token using the same explicit algorithm allowlist."""
        return jwt.decode(token, self.secret, algorithms=["HS256"])
