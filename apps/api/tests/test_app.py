"""HTTP behavior for the FastAPI scaffold."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.config import Settings
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


async def test_unexpected_error_hides_exception_and_returns_request_id() -> None:
    """Unhandled exceptions become a safe INTERNAL response that is traceable."""
    app: FastAPI = create_app(Settings())

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("sensitive database details")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
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


def test_config_reads_he_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment settings come from the HE_ environment namespace."""
    monkeypatch.setenv("HE_HOST", "127.0.0.1")
    monkeypatch.setenv("HE_PORT", "9123")
    monkeypatch.setenv("HE_CORS_ORIGINS", '["https://example.test"]')

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9123
    assert settings.cors_origins == ["https://example.test"]


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
        response = await test_client.get("/teapot")

    assert response.status_code == 418
    assert response.json() == {
        "error": {
            "code": "INTERNAL",
            "message": "request failed",
            "details": {"path": "/teapot", "status": 418},
        },
    }
