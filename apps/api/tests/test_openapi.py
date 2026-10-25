"""OpenAPI snapshot and public schema contracts."""

import json
from pathlib import Path
from typing import Any

from app.config import DatabaseDialect, Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "packages" / "contracts" / "openapi.json"


def canonicalize(value: Any) -> Any:
    """Return JSON-like data with object keys in a deterministic order."""
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def test_openapi_exposes_health_and_shared_error_contract() -> None:
    """Only the implemented health endpoint and shared error models are exported."""
    schema = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()
    components = schema["components"]["schemas"]

    assert set(schema["paths"]) == {"/api/health"}
    assert {"HealthResponse", "DatabaseHealthResponse", "ErrorResponse", "ErrorBody"} <= set(
        components
    )


def test_checked_in_openapi_snapshot_is_current() -> None:
    """FastAPI schema drift fails until the deterministic snapshot is regenerated."""
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()

    assert canonicalize(actual) == expected
