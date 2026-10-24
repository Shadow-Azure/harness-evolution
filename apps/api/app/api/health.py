"""Health-check route."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.config import ServicePhase

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """Public health-check contract."""

    model_config = ConfigDict(extra="forbid")

    ok: Literal[True] = True
    service: Literal["harness-evolution"] = "harness-evolution"
    phase: ServicePhase


@router.get("/health")
async def health(request: Request) -> HealthResponse:
    """Report API reachability and the configured delivery phase."""
    phase: ServicePhase = request.app.state.settings.phase
    return HealthResponse(phase=phase)
