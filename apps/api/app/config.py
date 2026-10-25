"""Environment-backed service configuration."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServicePhase(StrEnum):
    """Delivery phase exposed by the health endpoint."""

    SCAFFOLD = "scaffold"
    DEMO = "demo"
    LIVE = "live"


class DatabaseDialect(StrEnum):
    """Supported SQLAlchemy database dialects."""

    SQLITE = "sqlite"
    MYSQL = "mysql"


class Settings(BaseSettings):
    """Runtime settings loaded from the ``HE_`` environment namespace."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="HE_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8787
    version: str = "0.1.0"
    phase: ServicePhase = ServicePhase.SCAFFOLD
    production: bool = False
    jwt_secret: SecretStr = SecretStr("")
    access_token_ttl_min: int = Field(default=30, gt=0)
    refresh_token_ttl_days: int = Field(default=14, gt=0)
    event_ticket_ttl_seconds: int = Field(default=60, gt=0)
    admin_username: str | None = None
    admin_password: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    docs_enabled: bool = False
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
    data_dir: Path = Path("data")
    db_dialect: DatabaseDialect = DatabaseDialect.MYSQL
    db_url: str | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    @property
    def effective_db_url(self) -> str:
        """Return the configured URL or a credential-free dialect default."""
        if self.db_url:
            return self.db_url
        if self.db_dialect is DatabaseDialect.SQLITE:
            return f"sqlite+aiosqlite:///{self.data_dir / 'harness.db'}"
        return "mysql+asyncmy://127.0.0.1:3306/harness_evolution?charset=utf8mb4"

    @model_validator(mode="after")
    def require_jwt_secret(self) -> "Settings":
        """Reject configuration that would sign JWTs with an empty key."""
        if not self.jwt_secret.get_secret_value():
            raise ValueError("HE_JWT_SECRET must not be empty")
        return self

    @property
    def access_ttl_seconds(self) -> int:
        """Return the configured bearer-token lifetime in seconds."""
        return self.access_token_ttl_min * 60

    @property
    def refresh_ttl_seconds(self) -> int:
        """Return the configured refresh-cookie lifetime in seconds."""
        return self.refresh_token_ttl_days * 24 * 60 * 60

    @property
    def is_production(self) -> bool:
        """Return whether transport and operational safeguards are production grade."""
        return self.production
