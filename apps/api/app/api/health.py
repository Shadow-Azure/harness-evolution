"""Health-check route."""

from http import HTTPStatus
from typing import Literal, cast

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config import DatabaseDialect, ServicePhase
from app.db.base import Database, DBHealth
from app.errors import ErrorResponse

router = APIRouter(prefix="/api", tags=["health"])


class DatabaseHealthResponse(BaseModel):
    """Sanitized database health included in the public health response."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dialect: DatabaseDialect
    ok: bool
    latency_ms: float = Field(alias="latencyMs")
    error: str | None = None

    @classmethod
    def from_health(cls, health: DBHealth) -> "DatabaseHealthResponse":
        """Translate the internal database health model to the API contract."""
        return cls(
            dialect=DatabaseDialect(health.dialect),
            ok=health.ok,
            latencyMs=health.latency_ms,
            error=health.error,
        )


class HealthResponse(BaseModel):
    """Public health-check contract."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    service: Literal["harness-evolution"] = "harness-evolution"
    phase: ServicePhase
    version: str
    db: DatabaseHealthResponse


@router.get(
    "/health",
    response_model_exclude_none=True,
    responses={
        HTTPStatus.INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
        HTTPStatus.SERVICE_UNAVAILABLE: {"model": HealthResponse},
    },
)
async def health(request: Request, response: Response) -> HealthResponse:
    """Report API reachability, delivery phase, and database health."""
    phase: ServicePhase = request.app.state.settings.phase
    version: str = request.app.state.settings.version
    database = cast(Database, request.app.state.database)
    database_health = await database.health()
    if request.app.state.database_start_error is not None:
        database_health = DBHealth(
            ok=False,
            dialect=database_health.dialect,
            latency_ms=database_health.latency_ms,
            error="DatabaseInitializationError: startup or migration failed",
        )
    if not database_health.ok:
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
    return HealthResponse(
        ok=database_health.ok,
        phase=phase,
        version=version,
        db=DatabaseHealthResponse.from_health(database_health),
    )
