"""Public runtime configuration route."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api", tags=["app-config"])


class AppConfigBrand(BaseModel):
    """Deployment brand name and subtitle exposed to every visitor."""

    model_config = ConfigDict(extra="forbid")

    name: str
    subtitle: str


class AppConfigResponse(BaseModel):
    """Public runtime configuration shared by the login page and the shell."""

    model_config = ConfigDict(extra="forbid")

    brand: AppConfigBrand


@router.get("/app-config")
async def app_config(request: Request) -> AppConfigResponse:
    """Report the brand resolved from the API environment at startup."""
    settings = request.app.state.settings
    return AppConfigResponse(
        brand=AppConfigBrand(
            name=settings.brand_name,
            subtitle=settings.brand_subtitle,
        ),
    )
