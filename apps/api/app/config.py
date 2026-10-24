"""Environment-backed service configuration."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field
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
