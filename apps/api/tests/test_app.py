"""HTTP behavior for the FastAPI scaffold."""

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

import app.main as main_module
from app.config import DatabaseDialect, ServicePhase, Settings
from app.db.base import Database, DBHealth
from app.db.factory import create_database
from app.errors import AppError, ErrorCode
from app.main import create_app


class HealthyDatabase:
    """Small API test double with deterministic database health."""

    dialect = "sqlite"
    url = "sqlite+aiosqlite:///:memory:"

    @property
    def engine(self) -> object:
        """Expose an engine placeholder for protocol compatibility."""
        return object()

    async def start(self) -> None:
        """No-op test lifecycle."""

    async def dispose(self) -> None:
        """No-op test lifecycle."""

    def session(self) -> object:
        """Return an unused session placeholder."""
        return object()

    def transaction(self) -> object:
        """Return an unused transaction placeholder."""
        return object()

    async def health(self) -> DBHealth:
        """Report a healthy local database."""
        return DBHealth(ok=True, dialect=self.dialect, latency_ms=0.1)


class UnhealthyDatabase(HealthyDatabase):
    """Small API test double that represents an unreachable database."""

    async def health(self) -> DBHealth:
        """Report a sanitized database failure."""
        return DBHealth(
            ok=False,
            dialect=self.dialect,
            latency_ms=0.2,
            error="OperationalError: database is unavailable",
        )


class StartFailingDatabase(HealthyDatabase):
    """Database double whose lifecycle startup fails before migration."""

    async def start(self) -> None:
        """Raise a sensitive startup error for logging and redaction tests."""
        raise RuntimeError("mysql+asyncmy://ops:secret@db.internal/private")


def as_database(database: HealthyDatabase) -> Database:
    """Treat a deterministic health double as the storage protocol in API tests."""
    return cast(Database, database)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Create an isolated app client for each test."""
    app = create_app(
        Settings(db_dialect=DatabaseDialect.SQLITE),
        database=as_database(HealthyDatabase()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


async def test_health_returns_scaffold_contract(client: httpx.AsyncClient) -> None:
    """Health is public and reports the API and database state."""
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "harness-evolution",
        "phase": "scaffold",
        "version": "0.1.0",
        "db": {
            "dialect": "sqlite",
            "ok": True,
            "latencyMs": 0.1,
        },
    }


def test_health_openapi_allows_unavailable_state() -> None:
    """The health schema must be able to represent a database outage."""
    app = create_app(
        Settings(db_dialect=DatabaseDialect.SQLITE),
        database=as_database(HealthyDatabase()),
    )

    health_schema = app.openapi()["components"]["schemas"]["HealthResponse"]
    ok_schema = health_schema["properties"]["ok"]

    assert ok_schema["type"] == "boolean"
    assert "const" not in ok_schema
    assert set(health_schema["required"]) == {"ok", "service", "phase", "version", "db"}


async def test_health_returns_503_when_database_is_unavailable() -> None:
    """A reachable API reports database failure without crashing."""
    app = create_app(
        Settings(db_dialect=DatabaseDialect.SQLITE),
        database=as_database(UnhealthyDatabase()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        response = await test_client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "service": "harness-evolution",
        "phase": "scaffold",
        "version": "0.1.0",
        "db": {
            "dialect": "sqlite",
            "ok": False,
            "latencyMs": 0.2,
            "error": "OperationalError: database is unavailable",
        },
    }


async def test_lifespan_starts_database_and_runs_migrations(tmp_path: Path) -> None:
    """The application lifecycle owns database startup and migration."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client,
    ):
        response = await test_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["db"]["dialect"] == "sqlite"
    assert (tmp_path / "harness.db").exists()


async def test_lifespan_migrates_the_injected_database_not_settings_target(
    tmp_path: Path,
) -> None:
    """Migration follows the exact Database instance owned by the application."""
    injected_path = tmp_path / "injected.db"
    settings_path = tmp_path / "settings.db"
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{settings_path}",
    )
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{injected_path}",
        )
    )
    app = create_app(settings, database=database)
    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client,
    ):
        response = await test_client.get("/api/health")

    assert response.status_code == 200
    assert injected_path.exists()
    assert not settings_path.exists()


async def test_lifespan_logs_start_failure_and_keeps_health_sanitized(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A broken database URL is logged while health exposes no infrastructure path."""
    sensitive_path = tmp_path / "missing" / "harness.db"
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{sensitive_path}",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        async with app.router.lifespan_context(app):
            assert app.state.database_start_error is not None
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as test_client:
                response = await test_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert response.json()["db"]["error"] == (
        "DatabaseInitializationError: startup or migration failed"
    )
    assert str(sensitive_path) not in response.text
    assert str(sensitive_path) not in caplog.text
    migration_record = next(record for record in caplog.records if record.name == "app.main")
    assert getattr(migration_record, "phase", None) == "migration"
    assert getattr(migration_record, "dialect", None) == "sqlite"
    assert getattr(migration_record, "error_type", None) == "OperationalError"
    assert migration_record.exc_info is None


async def test_migration_failure_marks_reachable_database_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed migration cannot be hidden by a successful ping."""
    sensitive_error = "migration failed: mysql+asyncmy://ops:secret@db.internal/private"

    async def fail_upgrade(_database: Database) -> None:
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(main_module, "upgrade_database", fail_upgrade)
    app = create_app(
        Settings(db_dialect=DatabaseDialect.SQLITE),
        database=as_database(HealthyDatabase()),
    )
    transport = httpx.ASGITransport(app=app)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as test_client,
        ):
            response = await test_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["db"] == {
        "dialect": "sqlite",
        "ok": False,
        "latencyMs": 0.1,
        "error": "DatabaseInitializationError: startup or migration failed",
    }
    assert sensitive_error not in response.text
    assert sensitive_error not in caplog.text
    assert "super-secret" not in caplog.text
    assert "db.internal" not in caplog.text
    migration_record = next(record for record in caplog.records if record.name == "app.main")
    assert getattr(migration_record, "phase", None) == "migration"
    assert getattr(migration_record, "dialect", None) == "sqlite"
    assert getattr(migration_record, "error_type", None) == "RuntimeError"
    assert migration_record.exc_info is None


async def test_startup_failure_logs_without_exposing_driver_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A start failure is logged while public health keeps only a stable summary."""
    app = create_app(
        Settings(db_dialect=DatabaseDialect.SQLITE),
        database=as_database(StartFailingDatabase()),
    )
    transport = httpx.ASGITransport(app=app)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as test_client,
        ):
            response = await test_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["db"]["error"] == (
        "DatabaseInitializationError: startup or migration failed"
    )
    assert "db.internal" not in response.text
    assert "super-secret" not in response.text
    assert "db.internal" not in caplog.text
    assert "secret" not in caplog.text
    startup_record = next(record for record in caplog.records if record.name == "app.main")
    assert getattr(startup_record, "phase", None) == "startup"
    assert getattr(startup_record, "dialect", None) == "sqlite"
    assert getattr(startup_record, "error_type", None) == "RuntimeError"
    assert startup_record.exc_info is None


async def test_protected_api_path_returns_auth_required_before_routing(
    client: httpx.AsyncClient,
) -> None:
    """Non-public API paths fail closed until identity support is installed."""
    response = await client.get("/api/sessions")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "AUTH_REQUIRED",
            "message": "authentication is required",
            "details": {},
        }
    }


async def test_unknown_route_returns_unified_error(client: httpx.AsyncClient) -> None:
    """Framework 404s use the same response envelope as application errors."""
    response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "route not found",
            "details": {"path": "/missing"},
        }
    }


async def test_method_not_allowed_returns_unified_error(
    client: httpx.AsyncClient,
) -> None:
    """Framework 405s use the same response envelope as application errors."""
    response = await client.post("/api/health")

    assert response.status_code == 405
    assert response.json() == {
        "error": {
            "code": "METHOD_NOT_ALLOWED",
            "message": "method not allowed",
            "details": {"method": "POST", "path": "/api/health"},
        }
    }


async def test_unexpected_error_hides_exception_and_returns_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unhandled exceptions become a safe INTERNAL response that is traceable."""
    app: FastAPI = create_app(Settings())

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("sensitive database details")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client:
            response = await test_client.get(
                "/explode",
                headers={"X-Request-Id": "req-test-123"},
            )

    assert response.status_code == 500
    assert response.headers["X-Request-Id"] == "req-test-123"
    assert response.json() == {
        "error": {
            "code": "INTERNAL",
            "message": "internal server error",
            "details": {"requestId": "req-test-123"},
        }
    }
    assert "sensitive" not in response.text
    error_record = next(record for record in caplog.records if record.name == "app.errors")
    error_fields = vars(error_record)
    assert error_record.exc_info is not None
    assert error_fields["request_id"] == "req-test-123"
    assert error_fields["method"] == "GET"
    assert error_fields["path"] == "/explode"


def test_config_reads_he_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment settings come from the HE_ environment namespace."""
    monkeypatch.setenv("HE_HOST", "127.0.0.1")
    monkeypatch.setenv("HE_PORT", "9123")
    monkeypatch.setenv("HE_JWT_SECRET", "configured-signing-secret")
    monkeypatch.setenv("HE_CORS_ORIGINS", '["https://example.test"]')
    monkeypatch.setenv("HE_DOCS_ENABLED", "false")
    monkeypatch.setenv("HE_DB_DIALECT", "sqlite")
    monkeypatch.setenv("HE_DB_URL", "sqlite+aiosqlite:////tmp/example.db")
    monkeypatch.setenv("HE_DB_POOL_SIZE", "4")
    monkeypatch.setenv("HE_DB_MAX_OVERFLOW", "2")

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9123
    assert settings.cors_origins == ["https://example.test"]
    assert settings.docs_enabled is False
    assert settings.db_dialect == "sqlite"
    assert settings.db_url == "sqlite+aiosqlite:////tmp/example.db"
    assert settings.db_pool_size == 4
    assert settings.db_max_overflow == 2


def test_jwt_secret_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production identity configuration cannot silently fall back to a default key."""
    monkeypatch.delenv("HE_JWT_SECRET")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_docs_are_disabled_by_default() -> None:
    """Production-safe defaults do not expose API documentation accidentally."""
    assert Settings().docs_enabled is False


def test_generated_contract_exports_match_the_fastapi_schema() -> None:
    """The TypeScript entry point aliases generated API schemas instead of duplicating them."""
    contract_path = Path(__file__).resolve().parents[3] / "packages/contracts/src/index.ts"
    contract = contract_path.read_text(encoding="utf-8")

    expected = (
        'export const SERVICE_PHASES = ["scaffold", "demo", "live"] as const '
        "satisfies readonly ServicePhase[];"
    )
    assert expected in contract
    assert (
        'export const DATABASE_DIALECTS = ["sqlite", "mysql"] as const '
        "satisfies readonly DatabaseDialect[];"
    ) in contract
    assert 'export type ServicePhase = components["schemas"]["ServicePhase"];' in contract
    assert 'export type HealthResponse = components["schemas"]["HealthResponse"];' in contract
    assert 'export type ErrorResponse = components["schemas"]["ErrorResponse"];' in contract
    assert 'export type ErrorCode = components["schemas"]["ErrorCode"];' in contract
    assert [phase.value for phase in ServicePhase] == ["scaffold", "demo", "live"]


async def test_docs_are_available_when_enabled() -> None:
    """Development deployments can expose interactive and machine docs."""
    app = create_app(
        Settings(docs_enabled=True, db_dialect=DatabaseDialect.SQLITE),
        database=as_database(HealthyDatabase()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        docs_response = await test_client.get("/api/docs")
        schema_response = await test_client.get("/api/openapi.json")

    assert docs_response.status_code == 200
    assert schema_response.status_code == 200


async def test_docs_are_closed_when_disabled() -> None:
    """Production deployments can remove both interactive and machine docs."""
    app = create_app(
        Settings(docs_enabled=False, db_dialect=DatabaseDialect.SQLITE),
        database=as_database(HealthyDatabase()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        docs_response = await test_client.get("/api/docs")
        schema_response = await test_client.get("/api/openapi.json")

    assert docs_response.status_code == 404
    assert docs_response.json()["error"]["code"] == "NOT_FOUND"
    assert schema_response.status_code == 404
    assert schema_response.json()["error"]["code"] == "NOT_FOUND"


async def test_validation_error_uses_unified_error() -> None:
    """FastAPI validation failures preserve the common error envelope."""
    app = create_app(Settings())

    @app.get("/needs-number")
    async def needs_number(number: int) -> dict[str, int]:
        return {"number": number}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        response = await test_client.get("/needs-number")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_INVALID"
    assert payload["error"]["message"] == "request validation failed"
    assert payload["error"]["details"]["errors"][0]["loc"] == ["query", "number"]


async def test_application_error_preserves_status_and_code() -> None:
    """Expected business failures keep their domain code and details."""
    app = create_app(Settings())

    @app.get("/conflict")
    async def conflict() -> None:
        raise AppError(
            code=ErrorCode.USERNAME_CONFLICT,
            message="demo conflict",
            status_code=409,
            details={"resource": "demo"},
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        response = await test_client.get("/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "USERNAME_CONFLICT",
            "message": "demo conflict",
            "details": {"resource": "demo"},
        },
    }


async def test_other_http_error_uses_unified_error() -> None:
    """Non-routing HTTP failures are normalized instead of leaking framework JSON."""
    app = create_app(Settings())

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail="teapot")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        response = await test_client.get(
            "/teapot",
            headers={"X-Request-Id": "req-http-error"},
        )

    assert response.status_code == 500
    assert response.headers["X-Request-Id"] == "req-http-error"
    assert response.json() == {
        "error": {
            "code": "INTERNAL",
            "message": "internal server error",
            "details": {"requestId": "req-http-error"},
        },
    }
