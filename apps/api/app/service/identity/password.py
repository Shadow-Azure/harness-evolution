"""Password provider: the existing username and password behaviour behind the seam."""

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.config import AuthProviderName
from app.db.crud.users import UserRepository
from app.service.identity.providers import Credentials, ProviderIdentity


class PasswordProvider:
    """Verify local credentials and return an internal user subject."""

    name = AuthProviderName.PASSWORD

    def __init__(self, users: UserRepository, hasher: PasswordHasher | None = None) -> None:
        """Bind the repository and one reusable hash verifier."""
        self._users = users
        self._hasher = hasher or PasswordHasher()
        self._dummy_hash = self._hasher.hash("timing-equalization-dummy")

    async def authenticate(self, credentials: Credentials) -> ProviderIdentity | None:
        """Return a verified password identity, or ``None`` for a uniform rejection."""
        username = credentials.username
        password = credentials.password
        if not username or not password:
            return None
        user = await self._users.get_by_username(username)
        stored_hash = user.password_hash if user else self._dummy_hash
        password_matches: bool
        try:
            password_matches = self._hasher.verify(stored_hash, password)
        except VerificationError:
            password_matches = False
        if user is None or not password_matches:
            return None
        if user.auth_provider != self.name.value:
            return None
        return ProviderIdentity(provider=self.name, subject=user.id)
