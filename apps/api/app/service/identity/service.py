"""Authentication, user administration, and event-ticket business rules."""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import Settings
from app.db.base import Database
from app.db.crud.users import UserRepository
from app.db.models.users import UserRecord
from app.errors import AppError, ErrorCode
from app.service.identity.callback import CallbackService
from app.service.identity.providers import Credentials, ProviderRegistry
from app.service.identity.revocations import RefreshRevocationStore
from app.service.identity.session_bridge import AuthenticationResult, SessionBridge
from app.service.identity.tickets import TicketStore
from app.service.identity.tokens import TokenService

__all__ = ["AuthenticationResult", "IdentityService"]


class IdentityService:
    """Own provider selection, token rotation, user records, and tickets."""

    def __init__(self, settings: Settings, database: Database) -> None:
        """Compose identity collaborators around a database transaction boundary."""
        self._settings = settings
        self.tokens = TokenService(settings)
        self.tickets = TicketStore(settings.event_ticket_ttl_seconds)
        self.users = UserRepository(database)
        self._hasher = PasswordHasher()
        self.revocations = RefreshRevocationStore()
        self.providers = ProviderRegistry.from_settings(settings, self.users)
        self.bridge = SessionBridge(self.users, self.tokens)
        self.callback = CallbackService(settings, self.providers, self.bridge)

    async def seed_admin_if_empty(self) -> None:
        """Create one forced-change administrator only for a brand-new deployment."""
        if await self.users.count() > 0:
            return
        username = self._settings.admin_username
        password = self._settings.admin_password
        if not username or password is None or not password.get_secret_value():
            return
        await self.users.create(
            username=username.lower(),
            password_hash=self._hasher.hash(password.get_secret_value()),
            display_name="Administrator",
            role="admin",
        )

    async def login(self, *, username: str, password: str) -> AuthenticationResult:
        """Authenticate through the password provider and issue a new token pair."""
        identity = await self.providers.password.authenticate(
            Credentials(username=username, password=password),
        )
        if identity is None:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_INVALID,
                message="username or password is invalid",
            )
        user = await self.bridge.resolve(identity)
        return await self.bridge.complete_login(user)

    async def refresh(self, refresh_token: str | None) -> AuthenticationResult:
        """Rotate one valid refresh token and re-read the latest user claims."""
        if not refresh_token:
            raise self._refresh_error()
        grant = self.tokens.decode_refresh_token(refresh_token)
        user = await self.users.get_by_id(grant.user_id)
        if user is None:
            raise self._refresh_error()
        if not user.is_active:
            raise AppError(
                status_code=403,
                code=ErrorCode.FORBIDDEN,
                message="account is disabled",
            )
        if not await self.revocations.consume_once(
            grant.jti,
            expires_at=grant.expires_at.timestamp(),
        ):
            raise self._refresh_error()
        return self.bridge.issue(user)

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke a presented refresh token; logout remains idempotent."""
        if not refresh_token:
            return
        try:
            grant = self.tokens.decode_refresh_token(refresh_token)
        except AppError:
            return
        await self.revocations.revoke(grant.jti, expires_at=grant.expires_at.timestamp())

    async def change_password(self, *, user_id: str, old_password: str, new_password: str) -> None:
        """Replace a user's password only after verifying the current secret."""
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_REQUIRED,
                message="authentication is required",
            )
        password_matches: bool
        try:
            password_matches = self._hasher.verify(user.password_hash, old_password)
        except VerifyMismatchError:
            password_matches = False
        if not password_matches:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_INVALID,
                message="current password is invalid",
            )
        if new_password == old_password:
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="new password must differ from current password",
            )
        await self.users.update_password(user_id, self._hasher.hash(new_password))

    async def get_user(self, user_id: str) -> UserRecord | None:
        """Return the current authenticated user's internal record."""
        return await self.users.get_by_id(user_id)

    async def list_users(self) -> list[UserRecord]:
        """Return every public user record for administrator consumption."""
        return await self.users.list()

    async def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password: str,
        role: str,
    ) -> UserRecord:
        """Create an administrator-provisioned user with forced first change."""
        if role == "admin":
            raise AppError(
                status_code=422,
                code=ErrorCode.ROLE_INVALID,
                message="the seeded administrator is the only account allowed to be admin",
            )
        if role not in {"admin", "member"}:
            raise AppError(
                status_code=422,
                code=ErrorCode.ROLE_INVALID,
                message="role must be member",
            )
        return await self.users.create(
            username=username.lower(),
            password_hash=self._hasher.hash(password),
            display_name=display_name,
            role=role,
        )

    def _refresh_error(self) -> AppError:
        """Return the uniform failure used for every unusable refresh token."""
        return AppError(
            status_code=401,
            code=ErrorCode.AUTH_EXPIRED,
            message="refresh token has expired or is invalid",
        )
