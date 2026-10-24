"""HTTP behavior for the FastAPI scaffold."""

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.config import ServicePhase, Settings
from app.errors import AppError
from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Create an isolated app client for each test."""
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


async def test_health_returns_scaffold_contract(client: httpx.AsyncClient) -> None:
    """Health is public and reports the current scaffold phase."""
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "harness-evolution",
        "phase": "scaffold",
    }


def test_health_openapi_allows_unavailable_state() -> None:
    """The health schema must be able to represent a database outage."""
    app = create_app(Settings())

    health_schema = app.openapi()["components"]["schemas"]["HealthResponse"]
    ok_schema = health_schema["properties"]["ok"]

    assert ok_schema["type"] == "boolean"
    assert "const" not in ok_schema


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
    monkeypatch.setenv("HE_CORS_ORIGINS", '["https://example.test"]')
    monkeypatch.setenv("HE_DOCS_ENABLED", "false")

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9123
    assert settings.cors_origins == ["https://example.test"]
    assert settings.docs_enabled is False


def test_docs_are_disabled_by_default() -> None:
    """Production-safe defaults do not expose API documentation accidentally."""
    assert Settings().docs_enabled is False


def test_service_phase_matches_the_shared_typescript_contract() -> None:
    """The handwritten cross-language phase contract cannot drift from FastAPI."""
    contract_path = Path(__file__).resolve().parents[3] / "packages/contracts/src/index.ts"
    contract = contract_path.read_text(encoding="utf-8")

    expected = 'export const SERVICE_PHASES = ["scaffold", "demo", "live"] as const;'
    assert expected in contract
    assert [phase.value for phase in ServicePhase] == ["scaffold", "demo", "live"]


async def test_docs_are_available_when_enabled() -> None:
    """Development deployments can expose interactive and machine docs."""
    app = create_app(Settings(docs_enabled=True))
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
    app = create_app(Settings(docs_enabled=False))
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
            code="DEMO_CONFLICT",
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
            "code": "DEMO_CONFLICT",
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
