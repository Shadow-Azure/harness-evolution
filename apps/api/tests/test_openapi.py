"""OpenAPI snapshot and public schema contracts."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.config import DatabaseDialect, Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "packages" / "contracts" / "openapi.json"
API_ROOT = ROOT / "apps" / "api"


def canonicalize(value: Any) -> Any:
    """Return JSON-like data with object keys in a deterministic order."""
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def test_openapi_exposes_implemented_identity_and_error_contracts() -> None:
    """Only implemented health, identity, user, and ticket endpoints are exported."""
    schema = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()
    components = schema["components"]["schemas"]

    assert set(schema["paths"]) == {
        "/api/health",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/auth/change-password",
        "/api/auth/me",
        "/api/users",
        "/api/events/ticket",
        "/api/events",
        "/api/jobs/{jobId}",
    }
    assert {
        "HealthResponse",
        "DatabaseHealthResponse",
        "ErrorCode",
        "ErrorResponse",
        "ErrorBody",
        "LoginRequest",
        "LoginResponse",
        "ChangePasswordRequest",
        "CreateUserRequest",
        "PublicUser",
        "UserListResponse",
        "TicketRequest",
        "EventTicketResponse",
        "JobResponse",
    } <= set(components)
    error_body = components["ErrorBody"]
    assert error_body["properties"]["code"]["$ref"] == "#/components/schemas/ErrorCode"
    paths = schema["paths"]
    assert {"200", "401", "403", "422", "429"} <= set(paths["/api/auth/login"]["post"]["responses"])
    assert {"200", "401", "403"} <= set(paths["/api/auth/refresh"]["post"]["responses"])
    assert {"201", "401", "403", "409", "422"} <= set(paths["/api/users"]["post"]["responses"])
    assert {"200", "401", "403", "422"} <= set(paths["/api/events/ticket"]["post"]["responses"])
    login_401 = paths["/api/auth/login"]["post"]["responses"]["401"]
    assert login_401["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    bearer = schema["components"]["securitySchemes"]["BearerAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"
    protected_operations = [
        ("/api/auth/logout", "post"),
        ("/api/auth/change-password", "post"),
        ("/api/auth/me", "get"),
        ("/api/users", "get"),
        ("/api/users", "post"),
        ("/api/events/ticket", "post"),
        ("/api/jobs/{jobId}", "get"),
    ]
    for path, method in protected_operations:
        assert paths[path][method]["security"] == [{"BearerAuth": []}]
    for path, method in [
        ("/api/health", "get"),
        ("/api/auth/login", "post"),
        ("/api/auth/refresh", "post"),
    ]:
        assert "security" not in paths[path][method]


def test_checked_in_openapi_snapshot_is_current() -> None:
    """FastAPI schema drift fails until the deterministic snapshot is regenerated."""
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()

    assert canonicalize(actual) == expected


def test_identity_time_and_secret_configuration_matches_design() -> None:
    """Deployment names and defaults preserve the authoritative auth contract."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, _env_file=None)  # type: ignore[call-arg]

    assert settings.access_token_ttl_min == 30
    assert settings.refresh_token_ttl_days == 14
    assert settings.access_ttl_seconds == 1_800
    assert settings.refresh_ttl_seconds == 1_209_600
    assert settings.event_ticket_ttl_seconds == 60
    assert settings.sse_heartbeat_seconds == 15
    assert settings.sse_queue_capacity == 100
    assert settings.event_replay_limit == 500


def test_openapi_export_ignores_service_environment() -> None:
    """Canonical snapshots cannot drift because of local HE_* overrides."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("HE_")}
    environment.update(
        {
            "HE_VERSION": "environment-drift",
            "HE_PHASE": "live",
            "HE_DOCS_ENABLED": "true",
            "PATH": os.environ["PATH"],
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py"],
        cwd=API_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout)["info"]["version"] == "0.1.0"
