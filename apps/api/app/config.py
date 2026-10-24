"""Environment-backed service configuration."""

from enum import StrEnum
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServicePhase(StrEnum):
    """Delivery phase exposed by the health endpoint."""

    SCAFFOLD = "scaffold"
    DEMO = "demo"
    LIVE = "live"


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
    phase: ServicePhase = ServicePhase.SCAFFOLD
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    docs_enabled: bool = False
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
