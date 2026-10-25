"""Dialect-neutral persistence for identity users."""

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.db.base import Database
from app.db.models.users import UserRecord, record_from_row, users
from app.errors import AppError, ErrorCode
from app.utils.ids import new_id
from app.utils.time import now_shanghai


class UserRepository:
    """Read and write user rows through one shared SQLAlchemy expression tree."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to the application database boundary."""
        self._database = database

    async def get_by_id(self, user_id: str) -> UserRecord | None:
        """Return an active or inactive user by stable identifier."""
        async with self._database.session() as session:
            row = (
                (await session.execute(select(users).where(users.c.id == user_id)))
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None

    async def get_by_username(self, username: str) -> UserRecord | None:
        """Return a user by canonical lowercase username."""
        async with self._database.session() as session:
            row = (
                (await session.execute(select(users).where(users.c.username == username.lower())))
                .mappings()
                .one_or_none()
            )
        return record_from_row(row) if row else None

    async def count(self) -> int:
        """Return the total number of users for seed idempotence checks."""
        async with self._database.session() as session:
            return int(
                (await session.execute(select(func.count()).select_from(users))).scalar_one()
            )

    async def list(self) -> list[UserRecord]:
        """Return all users in username order for the admin list endpoint."""
        async with self._database.session() as session:
            rows = (
                (await session.execute(select(users).order_by(users.c.username))).mappings().all()
            )
        return [record_from_row(row) for row in rows]

    async def create(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
    ) -> UserRecord:
        """Create a user whose first password must be changed by its owner."""
        now = now_shanghai()
        user_id = new_id()
        async with self._database.transaction() as session:
            try:
                await session.execute(
                    insert(users).values(
                        id=user_id,
                        username=username.lower(),
                        password_hash=password_hash,
                        display_name=display_name,
                        role=role,
                        is_active=True,
                        must_change_password=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
            except IntegrityError as exc:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.USERNAME_CONFLICT,
                    message="username is already registered",
                ) from exc
        created = await self.get_by_id(user_id)
        if created is None:
            raise RuntimeError("created user disappeared before response")
        return created

    async def update_password(self, user_id: str, password_hash: str) -> None:
        """Store a new hash, clear forced change, and record the password time."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(
                    password_hash=password_hash,
                    must_change_password=False,
                    password_changed_at=now,
                    updated_at=now,
                )
            )

    async def touch_last_login(self, user_id: str) -> None:
        """Record successful authentication without exposing the timestamp value."""
        now = now_shanghai()
        async with self._database.transaction() as session:
            await session.execute(
                update(users).where(users.c.id == user_id).values(last_login_at=now, updated_at=now)
            )
