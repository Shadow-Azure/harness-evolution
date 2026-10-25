"""Dialect-neutral user table and internal row representation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table, true

from app.utils.time import as_shanghai

IDENTITY_METADATA = MetaData()

users = Table(
    "users",
    IDENTITY_METADATA,
    Column("id", String(36), primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("display_name", String(128), nullable=False),
    Column("role", String(16), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("must_change_password", Boolean, nullable=False, server_default=true()),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("password_changed_at", DateTime(timezone=True), nullable=True),
)


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Internal user row; password material never leaves the service boundary."""

    id: str
    username: str
    password_hash: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    password_changed_at: datetime | None

    @property
    def public_fields(self) -> dict[str, object]:
        """Return the only user fields permitted outside identity services."""
        return {
            "id": self.id,
            "username": self.username,
            "displayName": self.display_name,
            "role": self.role,
            "mustChangePassword": self.must_change_password,
        }


def record_from_row(row: Any) -> UserRecord:
    """Translate one database row mapping into the internal record."""
    last_login_at = row["last_login_at"]
    password_changed_at = row["password_changed_at"]
    return UserRecord(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        display_name=row["display_name"],
        role=row["role"],
        is_active=row["is_active"],
        must_change_password=row["must_change_password"],
        created_at=as_shanghai(row["created_at"]),
        updated_at=as_shanghai(row["updated_at"]),
        last_login_at=as_shanghai(last_login_at) if last_login_at is not None else None,
        password_changed_at=(
            as_shanghai(password_changed_at) if password_changed_at is not None else None
        ),
    )
