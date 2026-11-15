"""Identity-provider callback orchestration with a cookie-bound state challenge."""

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Literal

import jwt

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.service.identity.providers import (
    AuthProviderError,
    Credentials,
    ProviderRegistry,
)
from app.service.identity.session_bridge import AuthenticationResult, SessionBridge

CALLBACK_STATE_COOKIE = "he_oidc_state"
CALLBACK_STATE_PATH = "/api/auth"
CALLBACK_STATE_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class CallbackStateChallenge:
    """Values a future start endpoint writes into the short-lived state cookie."""

    value: str
    cookie_name: str
    path: str
    max_age: int
    secure: bool
    samesite: Literal["lax"] = "lax"


class CallbackStateStore:
    """Sign a nonce and bind it to the browser through the state cookie."""

    def __init__(
        self,
        secret: str,
        *,
        ttl_seconds: int = CALLBACK_STATE_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create a store bound to a state-specific key and an injectable clock."""
        self._secret = hmac.new(
            secret.encode("utf-8"),
            b"harness-evolution-auth-state-v1",
            hashlib.sha256,
        ).hexdigest()
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    @property
    def ttl_seconds(self) -> int:
        """Return the challenge lifetime used by the cookie writer."""
        return self._ttl_seconds

    def issue(self) -> str:
        """Return a signed state value that expires after the configured TTL."""
        now = int(self._clock())
        return jwt.encode(
            {
                "typ": "state",
                "nonce": secrets.token_urlsafe(24),
                "iat": now,
                "exp": now + self._ttl_seconds,
            },
            self._secret,
            algorithm="HS256",
        )

    def verify(self, *, value: str | None, cookie: str | None) -> None:
        """Require a matching cookie and an unexpired signed state value."""
        if not value or not cookie:
            raise self._invalid()
        if not value.isascii() or not cookie.isascii():
            raise self._invalid()
        if not hmac.compare_digest(value, cookie):
            raise self._invalid()
        try:
            claims = jwt.decode(
                value,
                self._secret,
                algorithms=["HS256"],
                options={"require": ["exp", "typ"]},
            )
        except jwt.PyJWTError as exc:
            raise self._invalid() from exc
        if claims.get("typ") != "state" or not claims.get("nonce"):
            raise self._invalid()

    @staticmethod
    def _invalid() -> AppError:
        """Return the single stable state failure shared by every mismatch case."""
        return AppError(
            status_code=HTTPStatus.BAD_REQUEST,
            code=ErrorCode.AUTH_STATE_INVALID,
            message="authentication state is missing, expired, or does not match",
        )


class CallbackService:
    """Complete an external provider callback without knowing the provider details."""

    def __init__(
        self,
        settings: Settings,
        registry: ProviderRegistry,
        bridge: SessionBridge,
        *,
        state_store: CallbackStateStore | None = None,
    ) -> None:
        """Bind the settings, provider registry, session bridge, and state store."""
        self._settings = settings
        self._registry = registry
        self._bridge = bridge
        self._state = state_store or CallbackStateStore(
            settings.jwt_secret.get_secret_value(),
        )

    @property
    def configured(self) -> bool:
        """Return whether an external provider is registered for callbacks."""
        return self._registry.external is not None

    def state_challenge(self) -> CallbackStateChallenge:
        """Create the state value and cookie attributes for a future start endpoint."""
        return CallbackStateChallenge(
            value=self._state.issue(),
            cookie_name=CALLBACK_STATE_COOKIE,
            path=CALLBACK_STATE_PATH,
            max_age=self._state.ttl_seconds,
            secure=self._settings.is_production,
        )

    async def complete(
        self,
        *,
        code: str | None,
        state: str | None,
        state_cookie: str | None,
    ) -> tuple[AuthenticationResult, str]:
        """Exchange a provider code for the internal token pair and redirect target."""
        provider = self._registry.external
        if provider is None:
            raise AppError(
                status_code=HTTPStatus.NOT_IMPLEMENTED,
                code=ErrorCode.AUTH_PROVIDER_NOT_CONFIGURED,
                message="an external identity provider is not configured",
            )
        self._state.verify(value=state, cookie=state_cookie)
        if not code:
            raise AppError(
                status_code=HTTPStatus.UNAUTHORIZED,
                code=ErrorCode.AUTH_INVALID,
                message="authorization code is missing",
            )
        try:
            identity = await provider.authenticate(Credentials(code=code))
        except AuthProviderError as exc:
            raise AppError(
                status_code=HTTPStatus.BAD_GATEWAY,
                code=ErrorCode.AUTH_PROVIDER_ERROR,
                message="identity provider exchange failed",
            ) from exc
        if identity is None:
            raise AppError(
                status_code=HTTPStatus.UNAUTHORIZED,
                code=ErrorCode.AUTH_INVALID,
                message="identity provider rejected the authorization code",
            )
        user = await self._bridge.resolve(identity)
        return await self._bridge.complete_login(user), self._settings.web_base_url or "/"
