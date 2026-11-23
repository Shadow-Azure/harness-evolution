"""Environment-backed service configuration."""

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AliasChoices,
    BeforeValidator,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[1]
# Sources run under <checkout>/apps/api or <release>/api.
_ASSET_ROOT = _API_DIR.parents[1] if _API_DIR.parent.name == "apps" else _API_DIR / "release-assets"
DEFAULT_ATTRIBUTION_GOLDEN_SET = _ASSET_ROOT / "fixtures" / "attribution-golden" / "cases.json"

_COOKIE_TOKEN_CHARS = set(
    "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _parse_upstream_api_major(value: object) -> object:
    """Normalize an environment-backed decimal major version before validation."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip(), 10)
    return value


def _parse_optional_bool(value: object) -> object:
    """Treat an empty environment value as an unset cookie-security switch."""
    if isinstance(value, str) and not value.strip():
        return None
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
CookieSecure = Annotated[bool | None, BeforeValidator(_parse_optional_bool)]


class ServicePhase(StrEnum):
    """Delivery phase exposed by the health endpoint."""

    SCAFFOLD = "scaffold"
    DEMO = "demo"
    LIVE = "live"


class DatabaseDialect(StrEnum):
    """Supported SQLAlchemy database dialects."""

    SQLITE = "sqlite"
    MYSQL = "mysql"


class AuthProviderName(StrEnum):
    """Selectable identity sources for the authentication seam."""

    PASSWORD = "password"  # noqa: S105 - provider name, not a secret
    COOKIE = "cookie"
    OIDC = "oidc"


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
    login_rate_limit: int = Field(default=10, ge=1, le=10_000)
    refresh_token_ttl_days: int = Field(default=14, gt=0)
    event_ticket_ttl_seconds: int = Field(default=60, gt=0)
    sse_heartbeat_seconds: float = Field(default=15, gt=0)
    sse_queue_capacity: int = Field(default=100, gt=0)
    event_replay_limit: int = Field(default=500, gt=0, le=5_000)
    sync_interval_seconds: int = Field(default=60, ge=0)
    sync_lock_ttl_seconds: int = Field(default=30 * 60, gt=0)
    job_lease_seconds: int = Field(default=90, ge=10, le=86_400)
    job_heartbeat_seconds: float = Field(default=15.0, gt=0, le=3_600)
    job_drain_timeout_seconds: float = Field(default=25.0, ge=0, le=600)
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
    external_contract_check_interval_seconds: float = Field(
        default=300.0,
        ge=30,
        le=86_400,
    )
    git_push: bool = True
    git_push_provider: Literal["github", "gitlab"] = "github"
    git_push_token: SecretStr | None = None
    git_push_url: str | None = None
    git_proxy: str | None = None
    git_proxy_probe_interval_seconds: float = Field(default=60.0, ge=5, le=3_600)
    git_proxy_probe_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    attribution_engine: str = Field(default="rule-v1", min_length=1, max_length=64)
    attribution_case_concurrency: int = Field(default=4, ge=1, le=32)
    attribution_batch_concurrency: int = Field(default=2, ge=1, le=8)
    eval_scan_seconds: float = Field(default=30.0, gt=0, le=300)
    eval_poll_seconds: int = Field(default=300, gt=0)
    eval_timeout_seconds: int = Field(default=7_200, gt=0)
    eval_mode: str = "fake"
    eval_base_url: str | None = None
    eval_api_key: SecretStr | None = None
    patch_source_mode: str = "placeholder"
    ai_agent_provider: str = Field(
        default="claude-code",
        validation_alias=AliasChoices("AI_AGENT_PROVIDER", "HE_AI_AGENT_PROVIDER"),
    )
    ai_agent_claude_bin: str = "~/.local/bin/claude"
    ai_agent_claude_settings: str | None = None
    ai_agent_failure_policy: Literal["strict", "degrade"] | None = None
    blocked_sweep_seconds: float = Field(default=30.0, ge=1)
    web_base_url: str | None = None
    auth_provider: AuthProviderName = AuthProviderName.PASSWORD
    session_cookie_name: str = Field(default="he_session", min_length=1, max_length=64)
    session_ttl_hours: int = Field(default=12, gt=0, le=24 * 30)
    cookie_secure: CookieSecure = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret_env: str | None = None
    admin_username: str | None = None
    admin_password: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    docs_enabled: bool = False
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
    data_dir: Path = Path("data")
    attribution_package_dir: Path = Field(
        default_factory=lambda data: (
            (data["data_dir"] if data["production"] else _ASSET_ROOT) / "attribute"
        ),
    )
    attribution_default_skill_path: Path = _ASSET_ROOT / "attribute-badcases" / "SKILL.md"
    attribution_golden_set_path: Path = DEFAULT_ATTRIBUTION_GOLDEN_SET
    attribution_llm: str = "agent-native"
    attribution_timeout_seconds: int = Field(default=600, ge=1, le=3600)
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

    @model_validator(mode="after")
    def require_valid_job_timing(self) -> "Settings":
        """Keep at least one heartbeat renewal inside every lease window."""
        if self.job_heartbeat_seconds >= self.job_lease_seconds:
            raise ValueError("HE_JOB_HEARTBEAT_SECONDS must be less than HE_JOB_LEASE_SECONDS")
        return self

    @model_validator(mode="after")
    def require_production_data_dir(self) -> "Settings":
        """Refuse a relative data directory where the process cwd is a release."""
        if self.production and not self.data_dir.expanduser().is_absolute():
            raise ValueError(
                f"HE_DATA_DIR must be an absolute path in production (got {self.data_dir})",
            )
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

    @field_validator("git_push_url")
    @classmethod
    def validate_git_push_url(cls, value: str | None) -> str | None:
        """Accept a credential-free HTTP(S)/SSH push URL or one scp-like remote."""
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if any(character.isspace() or ord(character) < 0x20 for character in normalized):
            raise ValueError("HE_GIT_PUSH_URL must not contain whitespace or controls")
        if "://" in normalized:
            parsed = urlsplit(normalized)
            if parsed.scheme not in {"http", "https", "ssh", "git"} or not parsed.hostname:
                raise ValueError("HE_GIT_PUSH_URL must be an HTTP(S) or SSH URL")
            if parsed.password is not None:
                raise ValueError("HE_GIT_PUSH_URL must not contain a password")
            if parsed.scheme in {"http", "https"} and parsed.username is not None:
                raise ValueError("HE_GIT_PUSH_URL must not embed credentials")
            if parsed.query or parsed.fragment:
                raise ValueError("HE_GIT_PUSH_URL must not contain query or fragment")
            return normalized
        if not re.fullmatch(r"[^@\s/]+@[^:\s/]+:[^\s]+", normalized):
            raise ValueError("HE_GIT_PUSH_URL must be an HTTP(S)/SSH URL or scp-like remote")
        return normalized

    @field_validator("git_proxy")
    @classmethod
    def validate_git_proxy(cls, value: str | None) -> str | None:
        """Accept only a credential-free local HTTP proxy address."""
        normalized = _validate_http_url(value, "HE_GIT_PROXY")
        if normalized is None:
            return None
        parsed = urlsplit(normalized)
        if parsed.scheme != "http":
            raise ValueError("HE_GIT_PROXY must use http")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HE_GIT_PROXY must point to loopback")
        if parsed.path not in {"", "/"}:
            raise ValueError("HE_GIT_PROXY must not include a path")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("HE_GIT_PROXY must include a valid port") from None
        if port is None:
            raise ValueError("HE_GIT_PROXY must include a port")
        return normalized

    @field_validator("session_cookie_name")
    @classmethod
    def validate_session_cookie_name(cls, value: str) -> str:
        """Keep the opaque session cookie a single RFC 6265 token."""
        if not value or any(character not in _COOKIE_TOKEN_CHARS for character in value):
            raise ValueError("HE_SESSION_COOKIE_NAME must be a cookie token")
        return value

    @field_validator("oidc_issuer")
    @classmethod
    def validate_oidc_issuer(cls, value: str | None) -> str | None:
        """Allow only an explicit HTTP(S) issuer without embedded credentials."""
        return _validate_http_url(value, "HE_OIDC_ISSUER")

    @field_validator("eval_mode")
    @classmethod
    def validate_eval_mode(cls, value: str) -> str:
        """Accept only registered evaluation gateway modes."""
        if value not in {"fake", "http"}:
            raise ValueError("HE_EVAL_MODE must be fake or http")
        return value

    @field_validator("eval_base_url")
    @classmethod
    def validate_eval_base_url(cls, value: str | None) -> str | None:
        """Allow only explicit HTTP(S) evaluation endpoints without credentials."""
        return _validate_http_url(value, "HE_EVAL_BASE_URL")

    @field_validator("patch_source_mode")
    @classmethod
    def validate_patch_source_mode(cls, value: str) -> str:
        """Accept only modes registered by the patch source factory."""
        from app.service.evolution.patch_source import PATCH_SOURCE_MODES

        if value not in PATCH_SOURCE_MODES:
            choices = ", ".join(PATCH_SOURCE_MODES)
            raise ValueError(f"HE_PATCH_SOURCE_MODE must be one of: {choices}")
        return value

    @field_validator("ai_agent_provider")
    @classmethod
    def validate_ai_agent_provider(cls, value: str) -> str:
        """Accept only registered AI Agent providers; unknown values fail startup."""
        normalized = value.strip().lower()
        from app.third_party_api.ai_agent.factory import registered_provider_ids

        legal = registered_provider_ids()
        if normalized not in legal:
            choices = ", ".join(sorted(legal))
            raise ValueError(
                f"unknown AI agent provider: {normalized!r}; expected one of: {choices}",
            )
        return normalized

    @field_validator("ai_agent_claude_bin")
    @classmethod
    def validate_ai_agent_claude_bin(cls, value: str) -> str:
        """Keep the CLI path a non-empty deployment value."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("AI_AGENT_CLAUDE_BIN must not be empty")
        return normalized

    @field_validator("ai_agent_failure_policy", mode="before")
    @classmethod
    def treat_blank_failure_policy_as_unset(cls, value: object) -> object:
        """Treat an empty template value as unset so the provider default applies."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("ai_agent_claude_settings")
    @classmethod
    def validate_ai_agent_claude_settings(cls, value: str | None) -> str | None:
        """Treat a blank settings path as unset; otherwise keep the explicit path."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def derive_ai_agent_failure_policy(self) -> "Settings":
        """Default the policy from the provider: fake degrades, real providers are strict."""
        if self.ai_agent_failure_policy is None:
            self.ai_agent_failure_policy = (
                "degrade" if self.ai_agent_provider == "fake" else "strict"
            )
        return self

    @property
    def effective_ai_agent_failure_policy(self) -> Literal["strict", "degrade"]:
        """Return the resolved policy, failing loudly on an unresolved settings object."""
        if self.ai_agent_failure_policy is None:
            raise RuntimeError("ai_agent_failure_policy was not resolved")
        return self.ai_agent_failure_policy

    @field_validator("oidc_client_secret_env")
    @classmethod
    def validate_oidc_client_secret_env(cls, value: str | None) -> str | None:
        """Store only the name of the environment variable holding the client secret."""
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if not _ENV_NAME.fullmatch(normalized):
            raise ValueError("HE_OIDC_CLIENT_SECRET_ENV must be an environment variable name")
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
    def oidc_configured(self) -> bool:
        """Return whether every OIDC switch is present for a future adapter."""
        return bool(
            self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret_env,
        )

    @property
    def bad_case_query_configured(self) -> bool:
        """Return whether the catalog query service is usable."""
        return bool(
            self.bad_case_query_base_url
            and self.bad_case_query_token
            and self.bad_case_query_token.get_secret_value(),
        )
