"""Identity-provider protocol, registry, and provider-neutral credential types."""

from dataclasses import dataclass
from typing import Protocol

from app.config import AuthProviderName, Settings
from app.db.crud.users import UserRepository


class AuthProviderConfigurationError(ValueError):
    """Raised at startup when the selected provider is missing or unusable."""


class AuthProviderError(RuntimeError):
    """Raised when an external identity provider cannot complete a grant."""


@dataclass(frozen=True, slots=True)
class Credentials:
    """Provider-neutral input; each provider consumes the fields it understands."""

    username: str | None = None
    password: str | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """A verified external or password identity before it is mapped to a user row."""

    provider: AuthProviderName
    subject: str
    email: str | None = None


class AuthProvider(Protocol):
    """The only surface the business layer uses to verify an identity source."""

    name: AuthProviderName

    async def authenticate(self, credentials: Credentials) -> ProviderIdentity | None:
        """Return a verified identity, or ``None`` when the credentials are rejected."""
        ...


class ProviderRegistry:
    """Resolve the configured provider set once at startup and fail fast otherwise."""

    def __init__(
        self,
        *,
        password: AuthProvider | None = None,
        external: AuthProvider | None = None,
    ) -> None:
        """Store the active providers; construction is the only wiring point."""
        self._password = password
        self._external = external

    @classmethod
    def from_settings(cls, settings: Settings, users: UserRepository) -> "ProviderRegistry":
        """Build the registry for ``HE_AUTH_PROVIDER`` and reject reserved values."""
        if settings.auth_provider is AuthProviderName.PASSWORD:
            from app.service.identity.password import PasswordProvider

            return cls(password=PasswordProvider(users))
        raise AuthProviderConfigurationError(
            f"HE_AUTH_PROVIDER={settings.auth_provider.value} is reserved and not "
            "implemented; only 'password' is available in this release",
        )

    @property
    def password(self) -> AuthProvider:
        """Return the password provider; the password flow always needs it."""
        if self._password is None:
            raise AuthProviderConfigurationError("the password provider is not configured")
        return self._password

    @property
    def external(self) -> AuthProvider | None:
        """Return the callback provider, if one is configured."""
        return self._external
