"""Session bridge: map a verified provider identity onto an existing internal user."""

from dataclasses import dataclass
from http import HTTPStatus

from app.config import AuthProviderName
from app.db.crud.users import UserRepository
from app.db.models.users import UserRecord
from app.errors import AppError, ErrorCode
from app.service.identity.providers import ProviderIdentity
from app.service.identity.tokens import TokenService


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """One successful login or callback with its rotating token pair."""

    user: UserRecord
    access_token: str
    refresh_token: str


class SessionBridge:
    """Exchange a verified identity for the same internal session contract as login."""

    def __init__(self, users: UserRepository, tokens: TokenService) -> None:
        """Bind the only two collaborators the bridge needs."""
        self._users = users
        self._tokens = tokens

    async def resolve(self, identity: ProviderIdentity) -> UserRecord:
        """Map an identity to an existing active user without ever creating one."""
        if identity.provider is AuthProviderName.PASSWORD:
            user = await self._users.get_by_id(identity.subject)
            if user is None or user.auth_provider != AuthProviderName.PASSWORD.value:
                raise AppError(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    code=ErrorCode.AUTH_INVALID,
                    message="username or password is invalid",
                )
        else:
            user = await self._users.get_by_provider_subject(
                provider=identity.provider.value,
                subject=identity.subject,
            )
            if user is None:
                raise AppError(
                    status_code=HTTPStatus.FORBIDDEN,
                    code=ErrorCode.AUTH_NO_MAPPING,
                    message="no local user is mapped to this identity",
                )
        if not user.is_active:
            raise AppError(
                status_code=HTTPStatus.FORBIDDEN,
                code=ErrorCode.FORBIDDEN,
                message="account is disabled",
            )
        return user

    async def complete_login(self, user: UserRecord) -> AuthenticationResult:
        """Record a successful login and issue the shared token pair."""
        await self._users.touch_last_login(user.id)
        return self.issue(user)

    def issue(self, user: UserRecord) -> AuthenticationResult:
        """Issue an access and refresh pair for an already resolved user."""
        return AuthenticationResult(
            user=user,
            access_token=self._tokens.create_access_token(
                user_id=user.id,
                role=user.role,
                must_change_password=user.must_change_password,
            ),
            refresh_token=self._tokens.create_refresh_token(user_id=user.id),
        )
