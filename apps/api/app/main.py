"""FastAPI application composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config import Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.errors import register_exception_handlers
from app.middleware.auth import AuthBoundaryMiddleware
from app.middleware.request_context import RequestContextMiddleware


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Compose middleware, exception handling, and routes."""
    resolved_settings = settings or Settings()
    resolved_database = database or create_database(resolved_settings)

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI) -> AsyncIterator[None]:
        """Start storage and migrations without turning outages into crashes."""
        try:
            await resolved_database.start()
            await upgrade_database(resolved_database, resolved_settings)
        except Exception as exc:
            lifespan_app.state.database_start_error = f"{type(exc).__name__}: {exc}"
        yield
        await resolved_database.dispose()

    docs_url = "/api/docs" if resolved_settings.docs_enabled else None
    openapi_url = "/api/openapi.json" if resolved_settings.docs_enabled else None
    app = FastAPI(
        title="harness-evolution-api",
        version=resolved_settings.version,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.database_start_error = None

    app.add_middleware(AuthBoundaryMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
