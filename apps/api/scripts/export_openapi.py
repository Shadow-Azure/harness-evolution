"""Export the deterministic FastAPI OpenAPI document to standard output."""

import json
import os
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.config import DatabaseDialect, Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def canonicalize(value: Any) -> Any:
    """Return JSON-like data with deterministic object key ordering."""
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def canonical_settings() -> Settings:
    """Return settings that cannot be changed by the host environment."""
    environment_keys = [key for key in os.environ if key.startswith("HE_")]
    saved_environment = {key: os.environ.pop(key) for key in environment_keys}
    try:
        return Settings(
            db_dialect=DatabaseDialect.SQLITE,
            jwt_secret="canonical-openapi-signing-secret",
            _env_file=None,
        )
    finally:
        os.environ.update(saved_environment)


def main() -> None:
    """Print the OpenAPI snapshot for the currently implemented API."""
    app = create_app(canonical_settings())
    document = canonicalize(app.openapi())
    encoded = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
