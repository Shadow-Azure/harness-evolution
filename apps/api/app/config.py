"""Environment-backed service configuration."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_upstream_api_major(value: object) -> object:
    """Normalize an environment-backed decimal major version before validation."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip(), 10)
    return value


def _validate_http_url(value: str | None, name: str) -> str | None:
    """Allow only explicit HTTP(S) endpoints without embedded credentials."""
    if value is None or not value.strip():
        return None
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{name} must use http or https")
    if not parsed.hostname:
        raise ValueError(f"{name} must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{name} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain query or fragment")
    return normalized


UpstreamApiMajor = Annotated[Literal[1], BeforeValidator(_parse_upstream_api_major)]


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
    sse_heartbeat_seconds: float = Field(default=15, gt=0)
    sse_queue_capacity: int = Field(default=100, gt=0)
    event_replay_limit: int = Field(default=500, gt=0, le=5_000)
    sync_interval_seconds: int = Field(default=60, ge=0)
    sync_lock_ttl_seconds: int = Field(default=30 * 60, gt=0)
    upstream_base_url: str | None = None
    upstream_token: SecretStr | None = None
    upstream_api_major: UpstreamApiMajor = 1
    upstream_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    upstream_retry_attempts: int = Field(default=3, ge=0, le=3)
    upstream_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=30)
    upstream_max_pages: int = Field(default=100, gt=0, le=1_000)
    session_query_base_url: str | None = None
    session_query_token: SecretStr | None = None
    session_query_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    session_query_retry_attempts: int = Field(default=2, ge=0, le=5)
    session_query_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=30)
    bad_case_sync_interval_seconds: int = Field(default=300, ge=0)
    bad_case_sync_batch_size: int = Field(default=20, ge=1, le=1_000)
    bad_case_sync_time_budget_seconds: float = Field(default=600.0, gt=0, le=3_600)
    bad_case_sync_max_agents: int = Field(default=200, ge=1, le=10_000)
    bad_case_sync_max_depth: int = Field(default=10, ge=0, le=100)
    bad_case_sync_lease_seconds: int = Field(default=900, ge=30, le=86_400)
    bad_case_query_base_url: str | None = None
    bad_case_query_token: SecretStr | None = None
    bad_case_query_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    bad_case_query_retry_attempts: int = Field(default=2, ge=0, le=5)
    bad_case_query_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=30)
    bad_case_catalog_sync_interval_seconds: int = Field(default=300, ge=0)
    bad_case_catalog_sync_page_size: int = Field(default=200, ge=1, le=200)
    bad_case_catalog_sync_time_budget_seconds: float = Field(default=300.0, gt=0, le=3_600)
    bad_case_catalog_sync_max_pages: int = Field(default=100, ge=1, le=1_000)
    git_push: bool = True
    eval_scan_seconds: float = Field(default=30.0, gt=0, le=300)
    eval_poll_seconds: int = Field(default=300, gt=0)
    eval_timeout_seconds: int = Field(default=7_200, gt=0)
    blocked_sweep_seconds: float = Field(default=30.0, ge=1)
    web_base_url: str | None = None
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

    @field_validator("upstream_base_url")
    @classmethod
    def validate_upstream_url(cls, value: str | None) -> str | None:
        """Allow only explicit HTTP(S) endpoints without embedded credentials."""
        return _validate_http_url(value, "HE_UPSTREAM_BASE_URL")

    @field_validator("bad_case_query_base_url")
    @classmethod
    def validate_bad_case_query_url(cls, value: str | None) -> str | None:
        """Allow only explicit HTTP(S) endpoints without embedded credentials."""
        return _validate_http_url(value, "HE_BAD_CASE_QUERY_BASE_URL")

    @field_validator("web_base_url")
    @classmethod
    def validate_web_base_url(cls, value: str | None) -> str | None:
        """Allow only credential-free HTTP(S) links in generated commit messages."""
        if value is None or not value.strip():
            return None
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("HE_WEB_BASE_URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("HE_WEB_BASE_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("HE_WEB_BASE_URL must not contain query or fragment")
        return normalized

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

    @property
    def upstream_configured(self) -> bool:
        """Return whether both upstream endpoint and bearer token are configured."""
        return bool(
            self.upstream_base_url
            and self.upstream_token
            and self.upstream_token.get_secret_value(),
        )

    @property
    def session_query_configured(self) -> bool:
        """Return whether the bad-case query service is usable."""
        return bool(
            self.session_query_base_url
            and self.session_query_token
            and self.session_query_token.get_secret_value(),
        )

    @property
    def bad_case_query_configured(self) -> bool:
        """Return whether the catalog query service is usable."""
        return bool(
            self.bad_case_query_base_url
            and self.bad_case_query_token
            and self.bad_case_query_token.get_secret_value(),
        )
