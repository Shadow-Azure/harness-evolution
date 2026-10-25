"""Authentication, user administration, and event-ticket business rules."""

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import Settings
from app.db.base import Database
from app.db.crud.users import UserRepository
from app.db.models.users import UserRecord
from app.errors import AppError, ErrorCode
from app.service.identity.revocations import RefreshRevocationStore
from app.service.identity.tickets import TicketStore
from app.service.identity.tokens import TokenService


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """One successful login or refresh with its rotating token pair."""

    user: UserRecord
    access_token: str
    refresh_token: str


class IdentityService:
    """Own password verification, token rotation, user records, and tickets."""

    def __init__(self, settings: Settings, database: Database) -> None:
        """Compose identity collaborators around a database transaction boundary."""
        self._settings = settings
        self.tokens = TokenService(settings)
        self.tickets = TicketStore(settings.event_ticket_ttl_seconds)
        self.users = UserRepository(database)
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash("timing-equalization-dummy")
        self.revocations = RefreshRevocationStore()

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
        """Authenticate a canonical username and issue a new token pair."""
        user = await self.users.get_by_username(username)
        stored_hash = user.password_hash if user else self._dummy_hash
        password_matches: bool
        try:
            password_matches = self._hasher.verify(stored_hash, password)
        except VerifyMismatchError:
            password_matches = False
        if user is None or not password_matches:
            raise AppError(
                status_code=401,
                code=ErrorCode.AUTH_INVALID,
                message="username or password is invalid",
            )
        if not user.is_active:
            raise AppError(
                status_code=403,
                code=ErrorCode.FORBIDDEN,
                message="account is disabled",
            )
        await self.users.touch_last_login(user.id)
        return self._issue_tokens(user)

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
        return self._issue_tokens(user)

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
        return await self.users.create(
            username=username.lower(),
            password_hash=self._hasher.hash(password),
            display_name=display_name,
            role=role,
        )

    def _issue_tokens(self, user: UserRecord) -> AuthenticationResult:
        """Issue an access and refresh pair after authentication succeeds."""
        return AuthenticationResult(
            user=user,
            access_token=self.tokens.create_access_token(
                user_id=user.id,
                role=user.role,
                must_change_password=user.must_change_password,
            ),
            refresh_token=self.tokens.create_refresh_token(user_id=user.id),
        )

    def _refresh_error(self) -> AppError:
        """Return the uniform failure used for every unusable refresh token."""
        return AppError(
            status_code=401,
            code=ErrorCode.AUTH_EXPIRED,
            message="refresh token has expired or is invalid",
        )
