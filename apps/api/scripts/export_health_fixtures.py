"""Export real FastAPI health responses as deterministic contract fixtures."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

API_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(SCRIPT_ROOT))

from export_openapi import canonical_settings, canonicalize  # noqa: E402

from app.config import DatabaseDialect  # noqa: E402
from app.db.base import DBHealth  # noqa: E402
from app.main import create_app  # noqa: E402


class ContractDatabase:
    """Deterministic storage double used only for executable health fixtures."""

    dialect = DatabaseDialect.SQLITE.value
    url = "sqlite+aiosqlite:///:memory:"

    @property
    def engine(self) -> object:
        """Expose an unused engine placeholder."""
        return object()

    async def start(self) -> None:
        """Avoid starting a real storage engine for response generation."""

    async def dispose(self) -> None:
        """Avoid retaining resources after response generation."""

    def session(self) -> object:
        """Expose an unused session placeholder."""
        return object()

    def transaction(self) -> object:
        """Expose an unused transaction placeholder."""
        return object()

    async def health(self) -> DBHealth:
        """Report deterministic database health."""
        return DBHealth(ok=True, dialect=self.dialect, latency_ms=0.1)


class UnavailableContractDatabase(ContractDatabase):
    """Represent a database outage without leaking connection details."""

    async def health(self) -> DBHealth:
        """Report a sanitized deterministic database failure."""
        return DBHealth(
            ok=False,
            dialect=self.dialect,
            latency_ms=0.2,
            error="OperationalError: database is unavailable",
        )


async def response_json(database: ContractDatabase) -> dict[str, Any]:
    """Return the JSON emitted by the real ASGI health endpoint."""
    app = create_app(canonical_settings(), database=database)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")
    if response.status_code not in {200, 503}:
        raise RuntimeError(f"Unexpected health response status: {response.status_code}")
    return response.json()


async def fixtures() -> dict[str, dict[str, Any]]:
    """Return canonical healthy and unavailable response payloads."""
    return {
        "healthy": await response_json(ContractDatabase()),
        "unavailable": await response_json(UnavailableContractDatabase()),
    }


def main() -> None:
    """Print deterministic health response fixtures."""
    json.dump(canonicalize(asyncio.run(fixtures())), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
